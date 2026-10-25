"""CLI: ``partest-gen`` — scaffold and re-sync a partest suite from OpenAPI."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from partest_gen import __version__
from partest_gen._text import visible


def _parse_entities(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return [p for p in parts if p]


def _resolve_openapi(args: argparse.Namespace) -> Optional[str]:
    if getattr(args, "openapi", None):
        return args.openapi
    if getattr(args, "file", None):
        return args.file
    if getattr(args, "url", None):
        return args.url
    return None


def _shown_source(source: str) -> str:
    """*source* as a message may show it: a URL without credentials, query or fragment."""
    from partest_gen._text import redact_source

    return visible(redact_source(source))


def _yaml_problem(exc: BaseException) -> str:
    mark = getattr(exc, "problem_mark", None)
    what = getattr(exc, "problem", None) or (str(exc).splitlines() or [type(exc).__name__])[0]
    if mark is not None:
        return f"{what} (line {mark.line + 1}, column {mark.column + 1})"
    return str(what)


def _causes(exc: BaseException) -> List[BaseException]:
    """*exc* and what it wraps: ``__cause__``, ``__context__``, urllib3's ``reason`` and
    exceptions passed as arguments — requests and urllib3 use all four."""
    out: List[BaseException] = []
    seen = set()
    queue: List[object] = [exc]
    while queue:
        cur = queue.pop(0)
        if not isinstance(cur, BaseException) or id(cur) in seen:
            continue
        seen.add(id(cur))
        out.append(cur)
        queue.extend([getattr(cur, "reason", None), cur.__cause__, cur.__context__])
        queue.extend(cur.args)
    return out


#: Where a failed download comes from. urllib3 raises some of its own through requests
#: unwrapped (``LocationParseError`` for an empty or overlong host label).
_FETCH_MODULES = ("requests", "urllib3")


def _fetch_problem(exc: BaseException, file_hint: str) -> str:
    """Why a ``--url`` download failed, by class names only: requests puts the full URL —
    credentials and query string included — into its messages."""
    import ssl

    chain = _causes(exc)
    rejected = next((e for e in chain if isinstance(e, ssl.SSLCertVerificationError)), None)
    if rejected is not None:
        # verify_message is OpenSSL's reason ("self-signed certificate", "Hostname mismatch,
        # certificate is not valid for 'host'"): it names at most the host, never the URL
        why = getattr(rejected, "verify_message", None)
        return (
            f"TLS certificate verification failed{f' ({visible(why)})' if why else ''}. "
            "Trust your CA with REQUESTS_CA_BUNDLE=/path/to/ca.pem, or download the "
            f"specification and pass it with {file_hint}. PARTEST_TLS_VERIFY does not apply "
            "to this download"
        )
    import requests

    response = getattr(exc, "response", None)
    if isinstance(exc, requests.HTTPError) and response is not None:
        return f"HTTP {response.status_code} — download it and pass it with {file_hint}"
    cause = next(
        (
            e
            for e in chain[1:]
            # the wrappers say nothing: requests' own classes, urllib3's retry and protocol
            if not (
                type(e).__module__.split(".")[0] == "requests"
                or type(e).__name__ in {"MaxRetryError", "ProtocolError"}
            )
        ),
        None,
    )
    reason = type(exc).__name__ if cause is None else f"{type(exc).__name__} ({type(cause).__name__})"
    if response is not None:
        # the server answered (a redirect loop, say): the file can still be fetched by hand
        reason += f" — download it and pass it with {file_hint}"
    return reason


def _spec_read_problem(exc: BaseException, source: str, *, file_hint: str) -> Optional[str]:
    """One line on why *source* could not be read as a document, or ``None`` when *exc* is
    not about the input at all — then the caller re-raises it."""
    import yaml

    from partest_gen.openapi_load import SpecReadError

    shown = _shown_source(source)
    if isinstance(exc, FileNotFoundError):
        if Path(source).is_dir():
            return f"error: OpenAPI specification {shown} is a directory, not a file"
        return f"error: OpenAPI specification not found: {shown}"
    if isinstance(exc, UnicodeDecodeError):  # a local file; a download is a SpecReadError
        if bytes(exc.object[:2]) in (b"\xff\xfe", b"\xfe\xff"):
            return (
                f"error: cannot read OpenAPI specification {shown}: it is UTF-16 text "
                "— re-save it as UTF-8"
            )
        return (
            f"error: cannot read OpenAPI specification {shown}: not UTF-8 text "
            f"(byte 0x{exc.object[exc.start]:02x} at offset {exc.start})"
        )
    if isinstance(exc, json.JSONDecodeError):
        # A YAML file that failed falls back to JSON; the YAML error is the one that
        # describes the file. json's own StopIteration sits between the two.
        context = exc.__context__
        while context is not None and not isinstance(context, yaml.YAMLError):
            context = context.__context__
        if context is not None:
            return f"error: {shown} is not valid YAML: {_yaml_problem(context)}"
        return f"error: {shown} is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
    if isinstance(exc, yaml.YAMLError):
        return f"error: {shown} is not valid YAML: {_yaml_problem(exc)}"
    if type(exc).__module__.split(".")[0] in _FETCH_MODULES:
        return f"error: cannot fetch OpenAPI specification {shown}: {_fetch_problem(exc, file_hint)}"
    if isinstance(exc, OSError):
        return f"error: cannot read OpenAPI specification {shown}: {exc.strerror or type(exc).__name__}"
    if isinstance(exc, SpecReadError):
        advice = f" — download it and pass it with {file_hint}" if exc.downloaded else ""
        where = {
            "fetch": f"cannot fetch OpenAPI specification {shown}",
            "read": f"cannot read OpenAPI specification {shown}",
        }.get(exc.stage, f"{shown} is not an OpenAPI document")
        return f"error: {where}: {visible(exc)}{advice}"
    return None


def _load_spec(source: str, *, file_hint: str):
    """The specification as ``SuiteIR``, or ``None`` after one line on stderr.

    Reading failures arrive as their own types (see :class:`~partest_gen.openapi_load.
    SpecReadError`) and become a line: the input is the user's, and a traceback says nothing
    a line cannot. Anything else — an exception while building the IR above all — is a
    generator bug and propagates. *file_hint* is how this command takes a local file, for the
    advice after a failed download.
    """
    from partest_gen.openapi_load import load_openapi

    try:
        return load_openapi(source)
    except Exception as exc:
        problem = _spec_read_problem(exc, source, file_hint=file_hint)
        if problem is None:
            raise
        print(problem, file=sys.stderr)
        return None


def _file_hint(args: argparse.Namespace) -> str:
    """How ``init`` / ``from-openapi`` take a local specification."""
    return "--file <path>" if args.command == "from-openapi" else "--openapi <path>"


def _print_result(result, *, verbose: bool) -> None:
    print(f"Project root: {result.root}")
    print(f"Created/updated: {len(result.created)}  Skipped: {len(result.skipped)}")
    if verbose:
        for p in result.created:
            print(f"  + {p}")
        for p in result.skipped:
            print(f"  = {p}")


_SHARED_MODULES = (
    "src/api/resources/endpoints/__init__.py",
    "src/api/resources/endpoints/paths.py",
    "src/api/resources/collections/__init__.py",
    "src/api/resources/collections/collections_manager.py",
)


def _print_skip_hints(root: Path, result) -> None:
    """Explain the skipped files a user most likely wants back, and the refused ones."""
    from partest_gen.emitters.util import _is_legacy_checklist

    for rel in result.skipped:
        if rel in _SHARED_MODULES:
            print(
                f"Kept {rel}: it carries no banner and is not an untouched skeleton "
                "placeholder, so it is treated as yours — and the generated modules import it. "
                "Delete it and run sync again to get the generated one."
            )
            continue
        if not rel.endswith("P1_CHECKLIST.md"):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        if _is_legacy_checklist(text):
            print(
                f"Kept {rel}: an older checklist is yours to mark. "
                "Delete it to get one that sync keeps up to date."
            )


def _print_refused(refused: List[str]) -> None:
    if refused:
        print(f"Not written — a link (symlink, junction) on the way: {len(refused)}")
        for p in refused:
            print(f"  x {p}")


def _copy_spec(root: Path, openapi: str, *, when, refused: List[str]) -> bool:
    """Copy a local specification to ``docs/openapi.yaml`` if ``when(dest)``; never through a
    link. Returns whether it was written."""
    from partest_gen._fsguard import safe_target

    from partest_gen.openapi_load import _is_url

    if _is_url(str(openapi)):
        return False
    src = Path(openapi)
    if not src.is_file():
        return False
    dest = safe_target(root.resolve(), "docs/openapi.yaml")
    if dest is None:
        refused.append("docs/openapi.yaml")
        return False
    if not when(dest):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def _print_placeholder_hint(root: Path, openapi: str) -> None:
    """Say so when a downloaded specification left ``docs/openapi.yaml`` the placeholder.

    A download is not saved in the project, and the placeholder is what ``confpartest.py``
    points the coverage report at and what a ``sync-openapi`` without a source reads.
    """
    from partest_gen.openapi_load import _is_url
    from partest_gen.skeleton import _is_placeholder_openapi

    if _is_url(str(openapi)) and _is_placeholder_openapi(root / "docs" / "openapi.yaml"):
        print(
            "Not saved: the specification was downloaded, and docs/openapi.yaml is still the "
            "/health placeholder that confpartest.py points the coverage report at and that "
            "sync-openapi without --file or --url reads. Save the specification as "
            "docs/openapi.yaml before the first run."
        )


_PATH_CLASS = re.compile(r"^class (Paths\w+)\(PathsBase\):$")
_PATH_CONST = re.compile(r'^        self\.(\w+) = (".*")$')


def _path_constants(root: Path) -> Dict[str, Dict[str, str]]:
    """``{PathsClass: {attr: path}}`` from the project's ``paths.py``; empty when unreadable."""
    try:
        text = (root / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    except OSError:
        return {}
    out: Dict[str, Dict[str, str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        m = _PATH_CLASS.match(line)
        if m:
            current = m.group(1)
            out[current] = {}
            continue
        m = _PATH_CONST.match(line)
        if m and current:
            try:
                out[current][m.group(1)] = json.loads(m.group(2))
            except ValueError:
                pass
    return out


def _refuse_unwritable(suite) -> bool:
    """Print why the generation would fail halfway, before anything is written."""
    from partest_gen.emitters.util import _unwritable

    problems = _unwritable(suite)
    for p in problems:
        print(f"error: the specification cannot be generated as it is: {p}", file=sys.stderr)
    return bool(problems)


def _entities_error(suite, entities: Optional[List[str]]) -> Optional[str]:
    """An error message when ``--entities`` matches no tag of the specification."""
    if not entities:
        return None
    from partest_gen.emitters.util import is_snake

    wanted = {is_snake(e) for e in entities}
    if any(is_snake(t) in wanted for t in suite.tags()):
        return None
    return (
        f"error: --entities {','.join(entities)} matches no tag of the specification. "
        f"Tags: {visible(', '.join(suite.tags())) or '(none)'}"
    )


def _cmd_init(args: argparse.Namespace) -> int:
    from partest_gen.skeleton import init_skeleton

    suite_ir = None
    openapi = _resolve_openapi(args)

    if openapi:
        suite_ir = _load_spec(openapi, file_hint=_file_hint(args))
        if suite_ir is None:
            return 2
        if getattr(args, "banner", None):
            # from-openapi announces itself only once the specification has been read
            print(args.banner)
        print(
            f"Loaded OpenAPI: {visible(suite_ir.title)} "
            f"({len(suite_ir.operations)} ops, tags={suite_ir.tags()})"
        )
        problem = _entities_error(suite_ir, _parse_entities(getattr(args, "entities", None)))
        if problem:
            print(problem, file=sys.stderr)
            return 2
        if _refuse_unwritable(suite_ir):
            return 2

    result = init_skeleton(
        args.path,
        name=args.name or Path(args.path).name or "api-suite",
        with_ui=bool(getattr(args, "with_ui", False)),
        force=bool(args.force),
        openapi_source=None,
        suite_ir=suite_ir,
    )

    # copy local openapi into docs/
    if openapi and _copy_spec(
        Path(result.root),
        openapi,
        when=lambda dest: args.force or not dest.exists() or dest.stat().st_size < 500,
        refused=result.refused,
    ):
        rel = "docs/openapi.yaml (from --openapi)"
        if rel not in result.created:
            result.created.append(rel)

    # G2/G3: emit paths + collections (+ payloads/tests)
    if suite_ir is not None:
        from partest_gen.emitters.resources import emit_resources

        entities = _parse_entities(getattr(args, "entities", None))
        depth = getattr(args, "depth", None) or "default"
        r2 = emit_resources(
            result.root,
            suite_ir,
            force=bool(args.force),
            tags_filter=entities,
            write_ir=True,
            depth=depth,
        )
        _print_skip_hints(Path(result.root), r2)
        result.created.extend(r2.created)
        result.skipped.extend(r2.skipped)
        result.refused.extend(r2.refused)
        print(
            f"Resources (depth={depth}): {len(r2.created)} files "
            f"(tags={entities or suite_ir.tags()})"
        )

    _print_result(result, verbose=bool(args.verbose))
    _print_refused(result.refused)
    if openapi:
        _print_placeholder_hint(Path(result.root), openapi)
    print("Next: pip install -r requirements/api.txt && cp env.example .env")
    if suite_ir is not None:
        print("See .partest/openapi_summary.md for paths registry + P1 matrix")
    return 0


def _write_atomically(out: Path, text: str) -> None:
    """Write *text* to *out* through a temporary file beside it and ``os.replace``: a failed
    or interrupted write leaves the previous file whole and no partial one behind."""
    import os
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix=f".{out.name}.", suffix=".tmp", dir=str(out.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        # mkstemp creates the file 0600; give it the mode a plain write would have
        try:
            mode = out.stat().st_mode & 0o777
        except OSError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp, mode)
        os.replace(tmp, out)
    except BaseException:
        try:
            # the mode copied from a read-only target makes the temporary file read-only too,
            # and Windows refuses to delete a read-only file
            os.chmod(tmp, 0o600)
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _cmd_dump_ir(args: argparse.Namespace) -> int:
    ir = _load_spec(args.openapi, file_hint="its path instead of the URL")
    if ir is None:
        return 2
    from partest_gen.emitters.util import _unwritable

    # A lone surrogate (an escape such as "\ud800" in the specification) cannot be encoded
    # into a file or onto stdout: said before anything is written, as by the other commands.
    problems = _unwritable(ir, windows=False)
    if problems:
        print(f"error: the IR cannot be written as UTF-8: {problems[0]}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else None
    payload = ir.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            _write_atomically(out, text)
        except OSError as exc:
            # the output path is the user's, like the input: a line, not a traceback
            why = exc.strerror or type(exc).__name__
            print(f"error: cannot write IR to {visible(str(out))}: {why}", file=sys.stderr)
            return 2
        print(f"Wrote IR: {out} ({len(ir.operations)} operations)")
    else:
        try:
            print(text)
        except UnicodeEncodeError as exc:
            # stdout redirected under a legacy code page cannot hold every character
            print(
                f"error: cannot print the IR in {exc.encoding}: it holds "
                f"{visible(exc.object[exc.start:exc.end])!r} — write it with -o <path>",
                file=sys.stderr,
            )
            return 2
    return 0


def _cmd_from_openapi(args: argparse.Namespace) -> int:
    """Skeleton (if needed) + G2/G3 resources from OpenAPI."""
    openapi = _resolve_openapi(args)
    if not openapi:
        print("error: provide --file or --url", file=sys.stderr)
        return 2

    args.openapi = openapi
    if not getattr(args, "name", None):
        args.name = Path(args.path).name or "api-suite"
    depth = getattr(args, "depth", None) or "default"
    args.banner = f"from-openapi: skeleton + IR + resources (depth={depth})"
    return _cmd_init(args)


def _cmd_init_ui(args: argparse.Namespace) -> int:
    """Add / refresh G5 UI tree on an existing project."""
    from partest_gen.skeleton import apply_ui_layout

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"error: project path not found: {root}", file=sys.stderr)
        return 2
    name = args.name or root.name or "api-suite"
    result = apply_ui_layout(root, name=name, force=bool(args.force))
    print(f"G5 UI layout → {result.root}")
    _print_result(result, verbose=bool(args.verbose))
    _print_refused(result.refused)
    print("Next: pip install -r requirements/ui.txt && playwright install chromium")
    print("Docs: docs/UI_GUIDE.md")
    return 0


def _cmd_init_package_exports(args: argparse.Namespace) -> int:
    """Generate recursive ``__init__.py`` re-exports (L1.11)."""
    from partest.tools.generate_init import generate_init_for_directory

    root = Path(args.directory).resolve()
    try:
        written = generate_init_for_directory(
            root,
            recursive=not bool(getattr(args, "no_recursive", False)),
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"init-package-exports: wrote {len(written)} file(s) under {root}")
    if args.verbose:
        for p in written:
            print(f"  + {p}")
    return 0


def _cmd_sync_openapi(args: argparse.Namespace) -> int:
    """Refresh paths/collections/IR for an existing project (no full re-init)."""
    from partest_gen.emitters.resources import emit_resources, find_orphans, remove_orphans

    openapi = _resolve_openapi(args)
    root = Path(args.path).resolve()
    from_docs = not openapi
    if not openapi:
        # try project docs
        candidate = root / "docs" / "openapi.yaml"
        if candidate.is_file():
            openapi = str(candidate)
        else:
            print(
                "error: provide --file/--url or place docs/openapi.yaml in project",
                file=sys.stderr,
            )
            return 2

    if not root.is_dir():
        print(f"error: project path not found: {root}", file=sys.stderr)
        return 2

    suite = _load_spec(openapi, file_hint="--file <path>")
    if suite is None:
        return 2
    print(
        f"Sync OpenAPI: {visible(suite.title)} ({len(suite.operations)} ops) → {root}"
    )
    if getattr(args, "prune", False) and not suite.operations:
        # Against an empty specification every generated file looks orphaned — that is a
        # wrong file or a failed fetch far more often than an API with nothing left in it.
        print(
            "error: --prune refused: the specification has no operations, so every "
            "generated file would be deleted. Check --file/--url.",
            file=sys.stderr,
        )
        return 2

    entities = _parse_entities(getattr(args, "entities", None))
    problem = _entities_error(suite, entities)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    if _refuse_unwritable(suite):
        return 2

    from partest_gen.emitters.util import is_snake

    # The tags that already have a collection in the project.
    have = {
        p.stem[len("collection_"):]
        for p in (root / "src/api/resources/collections").glob("collection_*.py")
    }
    if from_docs:
        from partest_gen.skeleton import _is_placeholder_openapi

        lost = sorted(have - {is_snake(t) for t in suite.tags()})
        if lost and _is_placeholder_openapi(root / "docs" / "openapi.yaml"):
            # A warning, not a refusal: the files it rewrites carry the banner and are in git.
            print(
                "Warning: docs/openapi.yaml is still the skeleton's /health placeholder, and "
                f"this project has generated tags it does not declare ({', '.join(lost)}). "
                "This sync rewrites paths.py and the facades from the placeholder; pass the "
                "real specification with --file or --url."
            )

    if getattr(args, "prune", False):
        # Against the wrong specification most of the tree looks orphaned. The cheapest sign of
        # it: not one tag that already has a collection in the project is still in the spec.
        if have and not have & {is_snake(t) for t in suite.tags()}:
            print(
                "error: --prune refused: none of the tags already generated here "
                f"({', '.join(sorted(have))}) is in this specification "
                f"({visible(', '.join(suite.tags())) or 'no tags'}). It looks like a different API — "
                "check --file/--url. If the tags really were renamed, prune in two steps: run "
                "sync-openapi without --prune (it generates the new tags), then again with "
                "--prune.",
                file=sys.stderr,
            )
            return 2

    # copy local openapi into docs if different
    copy_refused: List[str] = []
    _copy_spec(
        root,
        openapi,
        when=lambda dest: args.force
        or not dest.exists()
        or Path(openapi).resolve() != dest.resolve(),
        refused=copy_refused,
    )
    before = _path_constants(root) if entities else {}

    depth = getattr(args, "depth", None) or "default"
    result = emit_resources(
        root,
        suite,
        force=bool(args.force),
        tags_filter=entities,
        write_ir=True,
        depth=depth,
    )
    # mark copy
    if (root / "docs" / "openapi.yaml").is_file():
        if "docs/openapi.yaml" not in result.created:
            # only note if we may have written
            pass

    _print_result(result, verbose=bool(args.verbose))
    _print_skip_hints(root, result)
    _print_refused(copy_refused + result.refused)
    _print_placeholder_hint(root, openapi)
    if entities:
        from partest_gen.emitters.util import class_name, is_snake

        wanted = {is_snake(e) for e in entities}
        after = _path_constants(root)
        moved = [
            t
            for t in suite.tags()
            if is_snake(t) not in wanted
            and class_name(t, "Paths") in before
            and before[class_name(t, "Paths")] != after.get(class_name(t, "Paths"))
        ]
        if moved:
            print(
                f"Paths changed for tags outside --entities: {visible(', '.join(moved))}. "
                "Their tests were not regenerated and may name old constants — "
                "run a full sync-openapi."
            )
    print("Updated .partest/suite_ir.json and openapi_summary.md")

    # Generated files no operation produces any more: listed on every sync, deleted only with
    # --prune (docs/wiki/decisions/banner-overwrite.md).
    links: List[str] = []
    orphans = find_orphans(root, suite, tags_filter=entities, links=links)
    if links:
        print(f"Links not traversed (symlink, junction): {len(links)}")
        for p in links:
            print(f"  ~ {p}")
    if orphans and getattr(args, "prune", False):
        failed: List[str] = []
        rechecked: List[str] = []
        removed = remove_orphans(root, orphans, failed=failed, skipped=rechecked)
        print(f"Removed orphaned generated files: {len(removed)}")
        for p in removed:
            print(f"  - {p}")
        if rechecked:
            print(f"Skipped on recheck (changed or no longer the generator's): {len(rechecked)}")
            for p in rechecked:
                print(f"  = {p}")
        if failed:
            print(f"Could not delete: {len(failed)}")
            for p in failed:
                print(f"  ? {p}")
            return 1
    elif orphans:
        print(f"Orphaned generated files (no operation in the specification): {len(orphans)}")
        for p in orphans:
            print(f"  ! {p}")
        print("Delete them with --prune (only files the generator owns are listed).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="partest-gen",
        description="Scaffold partest API suites (monorepo layout).",
    )
    # Asked for in bug reports before anything else: generated trees look alike, and the
    # only way to tell which emitter produced one is the version that ran.
    parser.add_argument("--version", action="version", version=f"partest-gen {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument(
            "--entities",
            default=None,
            help="Comma-separated tags to emit (default: all)",
        )
        p.add_argument(
            "--depth",
            default="default",
            choices=["resources", "default", "p1"],
            help=(
                "resources=G2 only; default=G3 payloads+Default/NotAllowed; "
                "p1=G4 full P1 matrix stubs"
            ),
        )
        p.add_argument("--force", action="store_true", help="Overwrite non-generated files too")
        p.add_argument("-v", "--verbose", action="store_true")

    p_init = sub.add_parser("init", help="Create monorepo skeleton (+ G2 if --openapi)")
    p_init.add_argument("path", help="Target directory")
    p_init.add_argument("--name", default="api-suite", help="Project / service name")
    p_init.add_argument(
        "--openapi",
        default=None,
        help="Optional OpenAPI file or URL — IR + G2 resources",
    )
    p_init.add_argument("--with-ui", action="store_true", help="Include src/ui skeleton")
    add_common(p_init)
    p_init.set_defaults(func=_cmd_init)

    p_ir = sub.add_parser("dump-ir", help="Parse OpenAPI to SuiteIR JSON")
    p_ir.add_argument("openapi", help="OpenAPI file path or URL")
    p_ir.add_argument("-o", "--out", default=None, help="Output JSON path")
    p_ir.set_defaults(func=_cmd_dump_ir)

    p_fo = sub.add_parser(
        "from-openapi",
        help="Skeleton + IR + G2 paths/collections from OpenAPI",
    )
    p_fo.add_argument("path", help="Target project directory")
    p_fo.add_argument("--name", default=None, help="Project name (default: dir name)")
    p_fo.add_argument("--file", default=None, help="Local OpenAPI path")
    p_fo.add_argument("--url", default=None, help="OpenAPI URL")
    p_fo.add_argument("--with-ui", action="store_true")
    add_common(p_fo)
    p_fo.set_defaults(func=_cmd_from_openapi)

    p_ui = sub.add_parser(
        "init-ui",
        help="G5: add deep UI monorepo tree (isolated from API session)",
    )
    p_ui.add_argument("path", help="Existing project directory")
    p_ui.add_argument("--name", default=None, help="Project name for docs")
    p_ui.add_argument("--force", action="store_true")
    p_ui.add_argument("-v", "--verbose", action="store_true")
    p_ui.set_defaults(func=_cmd_init_ui)

    p_sync = sub.add_parser(
        "sync-openapi",
        help="Refresh paths/collections/IR in existing project (G2)",
    )
    p_sync.add_argument("path", help="Existing project directory")
    p_sync.add_argument("--file", default=None, help="Local OpenAPI path")
    p_sync.add_argument("--url", default=None, help="OpenAPI URL")
    p_sync.add_argument(
        "--openapi",
        default=None,
        help="Alias for --file/--url",
    )
    p_sync.add_argument(
        "--prune",
        action="store_true",
        help=(
            "Delete generated files (banner on the first line) whose operation is gone "
            "from the spec; without it they are only listed"
        ),
    )
    add_common(p_sync)
    p_sync.set_defaults(func=_cmd_sync_openapi)

    p_init_pkg = sub.add_parser(
        "init-package-exports",
        help="Generate recursive __init__.py re-exports (from .mod import *)",
    )
    p_init_pkg.add_argument(
        "directory",
        help=(
            "Root of a package you wrote by hand (e.g. your own helpers package). The "
            "__init__.py of every directory under it that holds modules is rewritten whole, "
            "recursively — commit first. Never a directory the generator writes, such as "
            "src/api/resources: sync-openapi then keeps those files as yours and stops "
            "refreshing them"
        ),
    )
    p_init_pkg.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only top-level directory",
    )
    p_init_pkg.add_argument("-v", "--verbose", action="store_true")
    p_init_pkg.set_defaults(func=_cmd_init_package_exports)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
