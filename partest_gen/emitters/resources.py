"""Orchestrate G2–G3 emission: paths, collections, payloads, validations, tests."""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import stat
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from partest_gen._fsguard import inside as _inside
from partest_gen._fsguard import is_link as _is_link
from partest_gen._fsguard import safe_target
from partest_gen._text import md_code, md_text, visible
from partest_gen.emitters.collections import (
    build_collection_module,
    build_collections_init,
    build_collections_manager,
)
from partest_gen.emitters.paths import build_paths_module
from partest_gen.emitters.payloads import build_payload_files, payload_wiring
from partest_gen.emitters.tests_default import build_test_files
from partest_gen.emitters.tests_p1 import build_p1_test_files
from partest_gen.emitters.util import (
    GENERATED_BANNER,
    _is_generated,
    _is_skeleton_placeholder,
    _unwritable,
    is_snake,
)
from partest_gen.emitters.validations import (
    build_validation_files,
    validation_wiring,
)
from partest_gen.ir import SuiteIR
from partest_gen.skeleton import WriteResult

# depth: resources=G2, default=G3, p1=G4 full P1 stubs
DEPTH_RESOURCES = "resources"
DEPTH_DEFAULT = "default"
DEPTH_P1 = "p1"


def _filter_tags(suite: SuiteIR, tags_filter: Optional[Sequence[str]]) -> List[str]:
    all_tags = suite.tags()
    if not tags_filter:
        return list(all_tags)
    allow = {is_snake(t) for t in tags_filter}
    return [t for t in all_tags if is_snake(t) in allow]


def _depth_flags(depth: Optional[str]) -> Tuple[str, bool, bool]:
    """``(depth, include_g3, include_g4)`` for a ``--depth`` value."""
    depth = (depth or DEPTH_DEFAULT).lower()
    return (
        depth,
        depth in {DEPTH_DEFAULT, DEPTH_P1, "g3", "full"},
        depth in {DEPTH_P1, "full", "g4"},
    )


def _wired_modules(
    wiring: Dict[str, List[Tuple[str, str, str]]],
    keep,
) -> Dict[str, List[Tuple[str, str, str]]]:
    """``wiring`` limited to entries whose module ``keep(rel_path)`` accepts."""
    out: Dict[str, List[Tuple[str, str, str]]] = {}
    for tag, entries in wiring.items():
        kept = [e for e in entries if keep(e[0].replace(".", "/") + ".py")]
        if kept:
            out[tag] = kept
    return out


def _plan(
    suite: SuiteIR,
    tags: Sequence[str],
    shared_tags: Sequence[str],
    depth: str,
    exists=lambda rel: False,
) -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    """Files for ``tags``, plus the modules every tag shares — paths, collection facades,
    manager and package init — for ``shared_tags``. A facade of a tag outside ``tags`` imports
    only payload and validation modules this plan writes or ``exists(rel)`` confirms. Returns
    the plan and the per-tag path attributes.
    """
    if not tags and suite.tags():
        # The emitters read an empty filter as "no filter": never hand them one.
        raise ValueError("no tag selected; every tag would be rewritten")
    files: Dict[str, str] = {}
    _, include_g3, include_g4 = _depth_flags(depth)

    paths_src, tag_attrs = build_paths_module(suite, tags_filter=shared_tags)
    files["src/api/resources/endpoints/paths.py"] = paths_src

    files["src/api/resources/endpoints/__init__.py"] = (
        GENERATED_BANNER
        + '"""Endpoints package."""\n\n'
        + "from src.api.resources.endpoints.paths import paths\n"
        + "from src.api.resources.endpoints import configs\n\n"
        + '__all__ = ["paths", "configs"]\n'
    )

    if include_g3:
        files.update(build_payload_files(suite, tags_filter=tags))
        files.update(build_validation_files(suite, tags_filter=tags))
    # Wiring is computed at every depth and limited to modules that exist or are planned, so
    # a shallow run that rebuilds another tag's facade keeps that tag's payloads and validators.
    p_wire = _wired_modules(
        payload_wiring(suite, tags_filter=shared_tags), lambda r: r in files or exists(r)
    )
    v_wire = _wired_modules(
        validation_wiring(suite, tags_filter=shared_tags), lambda r: r in files or exists(r)
    )

    for tag in shared_tags:
        path_attrs = tag_attrs.get(is_snake(tag), {})
        ops = [o for o in suite.operations if is_snake(o.tag) == is_snake(tag)]
        ops_summary = [
            (
                f"{o.method} {o.path}  [{o.subtype}]  p1={','.join(o.required_p1[:4])}…"
                if len(o.required_p1) > 4
                else f"{o.method} {o.path}  [{o.subtype}]  p1={','.join(o.required_p1) or '—'}"
            )
            for o in ops
        ]
        files[f"src/api/resources/collections/collection_{is_snake(tag)}.py"] = (
            build_collection_module(
                tag,
                path_attrs,
                ops_summary=ops_summary,
                payload_wiring=p_wire.get(is_snake(tag)),
                validation_wiring=v_wire.get(is_snake(tag)),
            )
        )

    files["src/api/resources/collections/collections_manager.py"] = (
        build_collections_manager(shared_tags)
    )
    files["src/api/resources/collections/__init__.py"] = build_collections_init(shared_tags)

    files["src/api/resources/collections/factory.py"] = (
        GENERATED_BANNER
        + '"""Factory for CollectionsManager (import in tests conftest)."""\n\n'
        + "from src.api.resources.collections import CollectionsManager\n\n\n"
        + "def build_models(token: str | None = None) -> CollectionsManager:\n"
        + "    return CollectionsManager(token=token)\n"
    )

    if include_g3:
        files.update(build_test_files(suite, tag_attrs, tags_filter=tags))

    if include_g4:
        files.update(build_p1_test_files(suite, tag_attrs, tags_filter=tags))

    return files, tag_attrs


def _plan_resources(
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
    depth: str = DEPTH_DEFAULT,
) -> Dict[str, str]:
    """Every file a generation of ``suite`` writes: ``rel_path -> source``, in write order.
    Touches no filesystem."""
    tags = _filter_tags(suite, tags_filter)
    files, _ = _plan(suite, tags, tags, depth)
    return files


def emit_resources(
    project_root: Union[str, Path],
    suite: SuiteIR,
    *,
    force: bool = False,
    tags_filter: Optional[Sequence[str]] = None,
    write_ir: bool = True,
    depth: str = DEPTH_DEFAULT,
) -> WriteResult:
    """Write G2 (+ G3 when depth is default/p1) artifacts.

    A path is written when it is missing, the generator owns it, or it holds an untouched
    skeleton placeholder; anything else is skipped unless ``force``. A path that crosses a
    link or leaves the project is never written (``result.refused``). The modules every tag
    shares — paths, collection facades, manager, package init — cover the filtered tags plus
    every tag whose collection module already exists, so ``--entities`` keeps the rest
    importable. Raises ``ValueError`` when ``tags_filter`` matches no tag or the suite
    cannot be written (a lone surrogate; on Windows, a tag named like a device) — before
    any write.
    """
    problems = _unwritable(suite)
    if problems:
        raise ValueError("; ".join(problems))
    root = Path(project_root).resolve()
    result = WriteResult(root=str(root))
    tags = _filter_tags(suite, tags_filter)
    depth, include_g3, include_g4 = _depth_flags(depth)
    present = {
        t
        for t in suite.tags()
        if (root / f"src/api/resources/collections/collection_{is_snake(t)}.py").is_file()
    }
    shared_tags = [t for t in suite.tags() if t in tags or t in present]

    files, tag_attrs = _plan(
        suite, tags, shared_tags, depth, exists=lambda rel: (root / rel).is_file()
    )
    for rel, src in files.items():
        _emit_generated(root, rel, src, force=force, result=result)

    if write_ir:
        _write_ir_summary(
            root,
            suite,
            tags,
            tag_attrs,
            result,
            include_g3=include_g3,
            include_g4=include_g4,
            depth=depth,
        )

    return result


# Where the generator writes per-operation and per-tag files. The orphan scan looks here and
# nowhere else, and never removes these directories themselves.
_GENERATED_ROOTS = (
    "src/api/resources/endpoints",
    "src/api/resources/payloads",
    "src/api/resources/validations",
    "src/api/resources/collections",
    "src/api/tests",
)


def _safe_rel(root: Path, rel: str) -> Optional[Path]:
    """:func:`safe_target`, further limited to paths under a generated root."""
    norm = rel.replace("\\", "/")
    if not any(norm.startswith(base + "/") for base in _GENERATED_ROOTS):
        return None
    return safe_target(root, norm)


def _walk_files(root: Path, base: Path, links: List[Path]) -> Iterable[Path]:
    """Regular files under ``base``, never entering links, junctions or ``__pycache__``.
    Links met on the way — ``base`` itself included — are appended to ``links``."""
    if not os.path.lexists(base):
        return
    if _is_link(base) or not _inside(root, base):
        links.append(base)
        return
    if not base.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        here = Path(dirpath)
        links.extend(here / d for d in dirnames if _is_link(here / d))
        dirnames[:] = sorted(
            d for d in dirnames if d != "__pycache__" and not _is_link(here / d)
        )
        for name in sorted(filenames):
            path = here / name
            if _is_link(path) or not _inside(root, path):
                links.append(path)
                continue
            if stat.S_ISREG(os.lstat(path).st_mode):
                yield path


def _file_tag(rel: str) -> Optional[str]:
    """The tag a generated file belongs to, or ``None`` for a shared one."""
    parts = rel.split("/")
    if rel.startswith(("src/api/resources/payloads/", "src/api/resources/validations/")):
        if len(parts) > 5 and parts[4] != "common":
            return parts[4]
        return None
    if rel.startswith("src/api/resources/collections/collection_"):
        return parts[-1][len("collection_"):-len(".py")]
    if rel.startswith("src/api/tests/") and len(parts) > 4:
        return parts[3]
    return None


def _read_generated(path: Path, rel: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return _is_generated(rel, text, first_line=True)


def find_orphans(
    project_root: Union[str, Path],
    suite: SuiteIR,
    *,
    tags_filter: Optional[Sequence[str]] = None,
    links: Optional[List[str]] = None,
) -> List[str]:
    """Generated files that no operation of ``suite`` produces any more, sorted.

    Measured against the full plan — every tag, deepest depth, deprecated operations
    included — so a narrower ``--depth`` or ``--entities`` never makes the rest of the tree
    look abandoned. With ``tags_filter`` only files of those tags are reported. A Python file
    counts only when its *first* line is the banner, a checklist only in its current form.
    Links and junctions are not entered; pass a list as ``links`` to receive the ones met.
    A package ``__init__.py`` is kept while its directory holds anything that is not an orphan.
    """
    root = Path(project_root).resolve()
    every_op = copy.copy(suite)
    every_op.operations = [dataclasses.replace(op, deprecated=False) for op in suite.operations]
    expected = set(_plan_resources(every_op, depth=DEPTH_P1))
    allow = {is_snake(t) for t in tags_filter} if tags_filter else None

    files_by_rel: Dict[str, Path] = {}
    met: List[Path] = []
    orphans: Set[str] = set()
    for base in _GENERATED_ROOTS:
        for path in _walk_files(root, root / base, met):
            rel = path.relative_to(root).as_posix()
            files_by_rel[rel] = path
            if path.suffix not in {".py", ".md"} or rel in expected:
                continue
            if allow is not None and _file_tag(rel) not in allow:
                continue
            if _read_generated(path, rel):
                orphans.add(rel)
    met_rel = [p.relative_to(root).as_posix() for p in met]
    if links is not None:
        links.extend(met_rel)

    # a link inside a package is somebody's content too: it keeps the package's __init__.py
    others = set(files_by_rel) | set(met_rel)
    changed = True
    while changed:
        changed = False
        for rel in sorted(orphans, key=lambda r: -r.count("/")):
            if not rel.endswith("/__init__.py"):
                continue
            prefix = rel[: -len("__init__.py")]
            if any(r.startswith(prefix) and r not in orphans for r in others):
                orphans.discard(rel)
                changed = True
    return sorted(orphans)


def _drop_empty_dirs(root: Path, start: Path) -> None:
    """Remove ``start`` and its parents while empty — a lone ``__pycache__`` of ``.pyc`` files
    counts as empty — stopping at the generated roots."""
    stops = {root} | {root / base for base in _GENERATED_ROOTS}
    current = start
    while current not in stops and current.is_dir() and not _is_link(current):
        if not any(str(current).startswith(str(root / base) + os.sep) for base in _GENERATED_ROOTS):
            return
        entries = list(current.iterdir())
        if len(entries) == 1 and entries[0].name == "__pycache__":
            cache = entries[0]
            if _is_link(cache) or not cache.is_dir():
                return
            cached = list(cache.iterdir())
            if not all(
                p.suffix == ".pyc" and not _is_link(p) and stat.S_ISREG(os.lstat(p).st_mode)
                for p in cached
            ):
                return
            for p in cached:
                p.unlink()
            cache.rmdir()
            entries = []
        if entries:
            return
        current.rmdir()
        current = current.parent


def remove_orphans(
    project_root: Union[str, Path],
    orphans: Iterable[str],
    *,
    failed: Optional[List[str]] = None,
    skipped: Optional[List[str]] = None,
) -> List[str]:
    """Delete ``orphans``, then each directory they leave empty. Returns what was deleted.

    Every path is checked again right before deletion: relative, under a generated root, no
    link on the way, inside the project, a regular file, still generated. A path that fails
    the check is left in place and goes into ``skipped``; a path the operating system refuses
    to delete goes into ``failed`` and does not stop the rest.
    """
    root = Path(project_root).resolve()
    removed: List[str] = []
    for rel in orphans:
        path = _safe_rel(root, rel)
        ok = path is not None
        if ok:
            try:
                ok = stat.S_ISREG(os.lstat(path).st_mode)
            except OSError:
                ok = False
        if ok:
            norm = path.relative_to(root).as_posix()
            ok = _read_generated(path, norm)
        if not ok:
            if skipped is not None:
                skipped.append(rel)
            continue
        try:
            path.unlink()
        except OSError:
            if failed is not None:
                failed.append(norm)
            continue
        removed.append(norm)
        try:
            _drop_empty_dirs(root, path.parent)
        except OSError:
            pass
    return removed


def _write_ir_summary(
    root, suite, tags, tag_attrs, result, *, include_g3: bool, include_g4: bool = False, depth: str = "default"
):
    rel = ".partest/suite_ir.json"
    ir_path = safe_target(root, rel)
    if ir_path is None:
        result.refused.append(rel)
    else:
        ir_path.parent.mkdir(parents=True, exist_ok=True)
        ir_path.write_text(
            json.dumps(suite.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if rel not in result.created:
            result.created.append(rel)

    summary_lines = [
        f"# OpenAPI IR summary — {md_text(suite.title)}",
        "",
        f"- version: {md_code(suite.version)}",
        f"- openapi: {md_code(suite.openapi_version)}",
        f"- source: {md_code(suite.source)}",
        f"- operations: **{len(suite.operations)}**",
        f"- tags emitted: {md_text(', '.join(tags)) or '—'}",
        f"- depth: `{depth}` "
        f"({'G4 P1' if include_g4 else 'G3 default' if include_g3 else 'G2 resources'})",
        "",
        "## Paths registry",
        "",
        "```text",
    ]
    for tag in tags:
        summary_lines.append(f"paths.paths_{is_snake(tag)}")
        for path, attr in sorted(
            tag_attrs.get(is_snake(tag), {}).items(), key=lambda x: x[1]
        ):
            summary_lines.append(f"  .{attr} = {visible(path).replace('`', chr(39))}")
    summary_lines.extend(
        [
            "```",
            "",
            "## Operations",
            "",
            "| Method | Path | Tag | Subtype | P1 TC | Body |",
            "|--------|------|-----|---------|-------|------|",
        ]
    )
    for op in suite.operations:
        if tags and is_snake(op.tag) not in {is_snake(t) for t in tags}:
            continue
        p1 = ", ".join(op.required_p1) if op.required_p1 else "—"
        body = "yes" if op.has_request_body else "—"
        summary_lines.append(
            f"| {op.method} | {md_code(op.path)} | {md_text(op.tag)} | `{op.subtype}` | {p1} | {body} |"
        )
    summary_lines.extend(["", "## Collections", ""])
    for tag in tags:
        summary_lines.append(
            f"- `src/api/resources/collections/collection_{is_snake(tag)}.py`"
        )
    if include_g3:
        summary_lines.extend(
            [
                "",
                "## G3 artifacts",
                "",
                "- payloads: `src/api/resources/payloads/<tag>/`",
                "- validations: `src/api/resources/validations/<tag>/`",
                "- tests: `test_*_default.py`, `test_*_not_allowed.py`",
                "",
            ]
        )
    if include_g4:
        summary_lines.extend(
            [
                "## G4 P1 stubs",
                "",
                "- per-TC files: permissions, new_object, update_object, incorrect_body,",
                "  elements, extra_data, not_found, benchmark, params, …",
                "- checklist: `src/api/tests/<tag>/P1_CHECKLIST.md`",
                "",
                "Next: fill skips, roles, seeds; run zorro for missing P1.",
                "",
            ]
        )
    elif include_g3:
        summary_lines.extend(
            [
                "Next: `partest-gen sync-openapi … --depth p1` for full P1 stubs.",
                "",
            ]
        )
    else:
        summary_lines.extend(
            [
                "",
                "Next: `partest-gen sync-openapi … --depth default` for G3.",
                "",
            ]
        )
    rel_s = ".partest/openapi_summary.md"
    summary_path = safe_target(root, rel_s)
    if summary_path is None:
        result.refused.append(rel_s)
        return
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    if rel_s not in result.created:
        result.created.append(rel_s)


def _emit_generated(
    root: Path,
    rel: str,
    content: str,
    *,
    force: bool,
    result: WriteResult,
) -> None:
    rel_n = rel.replace("\\", "/")
    path = _safe_rel(root, rel_n)
    if path is None:
        # a link (junction, symlink) on the way, or a path that leaves the project
        result.refused.append(rel_n)
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not force:
        try:
            data = path.read_bytes()
        except OSError:
            data = b""
        existing = data.decode("utf-8", errors="replace")
        if not (_is_generated(rel_n, existing) or _is_skeleton_placeholder(rel_n, data)):
            result.skipped.append(rel_n)
            return

    path.write_text(content, encoding="utf-8", newline="\n")
    if rel_n not in result.created:
        result.created.append(rel_n)
