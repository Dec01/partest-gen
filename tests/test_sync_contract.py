"""What a first generation and a later sync leave behind in a real directory.

The golden suite generates with ``--force``; these tests run the commands the way a user
does — without it, into a fresh directory, over an older tree, then again after the
specification changed — and check that the tree still works, not only that files exist.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from partest_gen.cli import main as cli_main
from partest_gen.emitters import find_orphans, remove_orphans
from partest_gen.emitters.resources import _GENERATED_ROOTS, _file_tag, _plan_resources
from partest_gen.emitters.util import (
    GENERATED_BANNER,
    _BANNER_LINE,
    _CHECKLIST_SYNC_NOTE,
    _LEGACY_CHECKLIST_NOTE,
    _MD_BANNER_LINE,
    _RELEASED_PLACEHOLDERS,
    _is_generated,
    _is_legacy_checklist,
    _is_skeleton_placeholder,
    is_snake,
)
from partest_gen.openapi_load import load_openapi
from partest_gen.root_files import RootFilesContainer
from partest_gen.skeleton import _skeleton_files, init_skeleton

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"
LIB_ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = sorted(_RELEASED_PLACEHOLDERS)


def _generate(dest: Path, *extra: str) -> None:
    rc = cli_main(
        ["from-openapi", str(dest), "--file", str(FIXTURE), "--depth", "p1", *extra]
    )
    assert rc == 0


def _sync(dest: Path, spec: Path, *extra: str) -> int:
    return cli_main(["sync-openapi", str(dest), "--file", str(spec), "--depth", "p1", *extra])


def _tree(root: Path) -> dict:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def _build_models(dest: Path) -> subprocess.CompletedProcess:
    code = (
        "import sys; sys.path.insert(0, '.')\n"
        "from src.api.resources.collections.factory import build_models\n"
        "m = build_models()\n"
        "print('ok', type(m).__name__, type(m.items).__name__)\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=dest,
        env={**os.environ, "PYTHONPATH": str(LIB_ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assert_models_build(dest: Path) -> None:
    r = _build_models(dest)
    assert r.returncode == 0, f"build_models() failed:\n{r.stdout}\n{r.stderr}"
    assert "ok CollectionsManager ItemsCollection" in r.stdout


def _isolated_python(code: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run like a console script: the project directory is *not* on sys.path by itself."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


# --- skeleton placeholders ----------------------------------------------------------------


def test_released_placeholders_match_the_current_skeleton():
    """The frozen texts are the ones the skeleton writes today; a change to either is a
    decision, not drift — add the new text, keep the old one."""
    current = _skeleton_files("api-suite", "docs/openapi.yaml", False)
    for rel in PLACEHOLDERS:
        assert current[rel] in _RELEASED_PLACEHOLDERS[rel], rel


def test_placeholder_is_recognised_byte_for_byte():
    rel = "src/api/resources/collections/collections_manager.py"
    text = _RELEASED_PLACEHOLDERS[rel][0]
    assert _is_skeleton_placeholder(rel, text.encode("utf-8"))
    assert _is_skeleton_placeholder(rel, text.replace("\n", "\r\n").encode("utf-8"))
    assert not _is_skeleton_placeholder(rel, (text + "# mine\n").encode("utf-8"))
    assert not _is_skeleton_placeholder("src/api/tests/conftest.py", b'"""Package."""\n')


def test_from_openapi_without_force_writes_the_same_tree_as_with_force(tmp_path: Path):
    # same directory name: the project name is taken from it and lands in several files
    plain, forced = tmp_path / "plain" / "suite", tmp_path / "forced" / "suite"
    _generate(plain)
    _generate(forced, "--force")

    a, b = _tree(plain), _tree(forced)
    assert sorted(a) == sorted(b)
    differ = [rel for rel in a if a[rel] != b[rel]]
    assert not differ, f"a fresh directory differs from --force in: {differ}"
    _assert_models_build(plain)


def test_init_then_from_openapi_builds_models(tmp_path: Path):
    dest = tmp_path / "suite"
    assert cli_main(["init", str(dest)]) == 0
    _generate(dest)
    _assert_models_build(dest)


def test_init_then_sync_builds_models(tmp_path: Path):
    """Also the shape of a 1.1.0 tree generated without --force: placeholders left in place."""
    dest = tmp_path / "suite"
    assert cli_main(["init", str(dest)]) == 0
    assert _sync(dest, FIXTURE) == 0
    _assert_models_build(dest)


def test_rerun_after_an_interrupted_from_openapi_builds_models(tmp_path: Path):
    """The skeleton got written, the emitters never ran — then the user runs it again."""
    dest = tmp_path / "suite"
    init_skeleton(dest, name="suite", suite_ir=load_openapi(FIXTURE))
    _generate(dest)
    _assert_models_build(dest)


def test_an_edited_placeholder_is_left_alone(tmp_path: Path):
    dest = tmp_path / "suite"
    assert cli_main(["init", str(dest)]) == 0
    mine = dest / "src/api/resources/collections/collections_manager.py"
    edited = mine.read_text(encoding="utf-8") + "# mine\n"
    mine.write_text(edited, encoding="utf-8")

    assert _sync(dest, FIXTURE) == 0

    assert mine.read_text(encoding="utf-8") == edited


def test_from_openapi_without_force_keeps_an_existing_bannerless_file(tmp_path: Path):
    dest = tmp_path / "suite"
    mine = dest / "src/api/resources/endpoints/paths.py"
    mine.parent.mkdir(parents=True)
    mine.write_text("# mine\npaths = None\n", encoding="utf-8")

    _generate(dest)

    assert mine.read_text(encoding="utf-8") == "# mine\npaths = None\n"


# --- the banner and the checklist ---------------------------------------------------------


def test_python_banner_is_the_full_line():
    assert _is_generated("x.py", GENERATED_BANNER + "x = 1\n")
    assert not _is_generated("x.py", "# AUTO-GENERATED by partest-gen\nx = 1\n")
    assert not _is_generated("x.py", "AUTO-GENERATED by partest-gen — do not edit by hand.\n")
    # the strict form wants it first: a file that only quotes it further down is not owned
    assert not _is_generated("x.py", "# notes\n" + GENERATED_BANNER, first_line=True)
    assert _is_generated("x.py", GENERATED_BANNER, first_line=True)


def _checklist(dest: Path) -> Path:
    return dest / "src/api/tests/items/P1_CHECKLIST.md"


def test_sync_rewrites_a_current_checklist(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    checklist = _checklist(dest)
    fresh = checklist.read_text(encoding="utf-8")
    assert _is_generated(checklist.name, fresh)
    banner, rest = fresh.split("# P1 coverage checklist", 1)
    checklist.write_text(banner + "# P1 coverage checklist" + rest + "| stale | row |\n",
                         encoding="utf-8")

    assert _sync(dest, FIXTURE) == 0

    assert checklist.read_text(encoding="utf-8") == fresh


def test_sync_keeps_a_legacy_checklist_and_says_how_to_refresh_it(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    checklist = _checklist(dest)
    legacy = (
        GENERATED_BANNER.replace("# ", "")
        + "\n# P1 coverage checklist — `items`\n\n"
        + "Generated from methodology matrix. " + _LEGACY_CHECKLIST_NOTE + "\n\n- [x] done\n"
    )
    checklist.write_text(legacy, encoding="utf-8")
    capsys.readouterr()

    assert _sync(dest, FIXTURE) == 0

    assert checklist.read_text(encoding="utf-8") == legacy
    out = capsys.readouterr().out
    assert "Kept src/api/tests/items/P1_CHECKLIST.md" in out
    assert "Delete it" in out


def test_sync_leaves_a_checklist_without_banner_alone(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    checklist = _checklist(dest)
    checklist.write_text("# my own checklist\n- [x] done\n", encoding="utf-8")

    assert _sync(dest, FIXTURE) == 0

    assert checklist.read_text(encoding="utf-8") == "# my own checklist\n- [x] done\n"


# --- pytest.ini and the coverage session -----------------------------------------------


_PYTHONPATH_LINE = re.compile(r"^pythonpath\s*=\s*\.\s*$", re.MULTILINE)


def test_pytest_ini_puts_the_project_root_on_sys_path(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    assert _PYTHONPATH_LINE.search((dest / "pytest.ini").read_text(encoding="utf-8"))


def test_flat_scaffold_pytest_ini_puts_the_project_root_on_sys_path():
    ini = RootFilesContainer().get_file_by_name("pytest.ini")
    assert ini is not None
    assert _PYTHONPATH_LINE.search(ini.content)


def test_bare_pytest_run_loads_the_specification(tmp_path: Path):
    """A console ``pytest`` must see confpartest when the partest plugin loads it.

    ``python -m pytest`` would put the working directory on sys.path and hide the defect, so
    pytest is started from an isolated interpreter instead — the same sys.path a console
    script gets. The probe asks partest through ``get_paths_info()`` where it exists (it
    triggers a lazy load too) and falls back to the module attribute of older releases.
    """
    pytest.importorskip("partest.coverage")
    dest = tmp_path / "suite"
    _generate(dest)
    probe = dest / "src/api/tests/test_probe_coverage.py"
    probe.write_text(
        "def test_probe():\n"
        "    import partest.coverage as c\n"
        "    getter = getattr(c, 'get_paths_info', None)\n"
        "    found = getter() if getter else getattr(c, 'paths_info', [])\n"
        "    print('PATHS', len(found))\n",
        encoding="utf-8",
    )
    r = _isolated_python(
        "import sys, pytest\n"
        "sys.exit(pytest.main(['src/api/tests/test_probe_coverage.py', '-q', '-s',"
        " '-p', 'no:cacheprovider']))\n",
        dest,
    )
    assert r.returncode == 0, f"probe run failed:\n{r.stdout}\n{r.stderr}"
    found = re.search(r"PATHS (\d+)", r.stdout)
    assert found, r.stdout
    assert int(found.group(1)) > 0, "partest loaded no paths — confpartest was not importable"


# --- operations removed from the specification -----------------------------------------


def _spec(tmp_path: Path, name: str, edit) -> Path:
    spec = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    edit(spec)
    out = tmp_path / name
    out.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return out


def _shrunk_spec(tmp_path: Path) -> Path:
    """The fixture without the `health` tag and without `POST /items`."""

    def edit(spec):
        del spec["paths"]["/health"]
        del spec["paths"]["/items"]["post"]

    return _spec(tmp_path, "shrunk.yaml", edit)


def test_sync_lists_orphans_without_deleting_them(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    shrunk = _shrunk_spec(tmp_path)
    capsys.readouterr()

    assert _sync(dest, shrunk) == 0

    out = capsys.readouterr().out
    assert "Orphaned generated files" in out
    for rel in (
        "src/api/resources/collections/collection_health.py",
        "src/api/tests/health/test_health_default.py",
        "src/api/tests/health/P1_CHECKLIST.md",
        "src/api/resources/payloads/items/post_items_payload.py",
    ):
        assert f"! {rel}" in out
        assert (dest / rel).is_file(), f"{rel} deleted without --prune"


def test_sync_prune_deletes_orphans_and_nothing_else(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    shrunk = _shrunk_spec(tmp_path)
    # a user's file next to the generated ones, and one that only quotes the banner
    mine = dest / "src/api/tests/health/test_health_mine.py"
    mine.write_text("def test_mine():\n    pass\n", encoding="utf-8")
    quoting = dest / "src/api/resources/payloads/items/notes.py"
    quoting.write_text('"""Copied once."""\n' + GENERATED_BANNER, encoding="utf-8")
    capsys.readouterr()

    assert _sync(dest, shrunk, "--prune") == 0

    out = capsys.readouterr().out
    assert "Removed orphaned generated files" in out
    assert not (dest / "src/api/resources/collections/collection_health.py").exists()
    assert not (dest / "src/api/tests/health/test_health_default.py").exists()
    assert not (dest / "src/api/resources/payloads/items/post_items_payload.py").exists()
    assert mine.is_file()
    # the package holding the user's test stays a package
    assert (dest / "src/api/tests/health/__init__.py").is_file()
    assert quoting.is_file()
    assert (dest / "src/api/tests/items/test_items_default.py").is_file()
    manager = (dest / "src/api/resources/collections/collections_manager.py").read_text(
        encoding="utf-8"
    )
    assert "collection_health" not in manager


def test_prune_removes_the_directory_of_a_vanished_tag(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    # a directory that holds only bytecode is empty for this purpose
    cache = dest / "src/api/tests/health/__pycache__"
    cache.mkdir()
    (cache / "test_health_default.cpython-310.pyc").write_bytes(b"\x00")

    assert _sync(dest, _shrunk_spec(tmp_path), "--prune") == 0

    assert not (dest / "src/api/tests/health").exists()
    assert (dest / "src/api/tests").is_dir()


def test_prune_stops_at_the_generated_roots(tmp_path: Path):
    root = tmp_path / "suite"
    orphan = root / "src/api/tests/gone/test_gone.py"
    orphan.parent.mkdir(parents=True)
    orphan.write_text(GENERATED_BANNER, encoding="utf-8")

    assert remove_orphans(root, ["src/api/tests/gone/test_gone.py"]) == [
        "src/api/tests/gone/test_gone.py"
    ]

    assert not (root / "src/api/tests/gone").exists()
    assert (root / "src/api/tests").is_dir()


def test_remove_orphans_rejects_paths_outside_the_project(tmp_path: Path):
    root = tmp_path / "suite"
    (root / "src/api/tests").mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text(GENERATED_BANNER, encoding="utf-8")
    elsewhere = root / "conftest.py"
    elsewhere.write_text(GENERATED_BANNER, encoding="utf-8")

    removed = remove_orphans(
        root,
        [
            "src/api/tests/../../../../outside.py",
            str(outside),
            "conftest.py",
            "/etc/passwd",
        ],
    )

    assert removed == []
    assert outside.is_file()
    assert elsewhere.is_file()


def _link_dir(link: Path, target: Path) -> None:
    if os.name == "nt":
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            pytest.skip(f"cannot create a junction here: {r.stdout}{r.stderr}")
    else:
        os.symlink(target, link, target_is_directory=True)


def test_prune_does_not_follow_a_junction_out_of_the_project(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "test_victim_default.py"
    victim.write_text(GENERATED_BANNER + "x = 1\n", encoding="utf-8")
    link = dest / "src/api/tests/linked"
    _link_dir(link, outside)

    try:
        assert find_orphans(dest, load_openapi(FIXTURE)) == []
        assert _sync(dest, _shrunk_spec(tmp_path), "--prune") == 0
        assert remove_orphans(dest, ["src/api/tests/linked/test_victim_default.py"]) == []
        assert victim.is_file(), "a file outside the project was deleted through a link"
    finally:
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()


def test_prune_refuses_a_specification_without_operations(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    before = _tree(dest)
    empty = _spec(tmp_path, "empty.yaml", lambda spec: spec.__setitem__("paths", {}))

    rc = _sync(dest, empty, "--prune")

    assert rc != 0
    assert "no operations" in capsys.readouterr().err
    assert _tree(dest) == before


def test_deprecated_operations_are_not_orphans(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)

    def edit(spec):
        spec["paths"]["/health"]["get"]["deprecated"] = True

    deprecated = _spec(tmp_path, "deprecated.yaml", edit)
    capsys.readouterr()

    assert _sync(dest, deprecated, "--prune") == 0

    assert "health" not in capsys.readouterr().out.split("Updated .partest")[-1]
    assert (dest / "src/api/tests/health/test_health_default.py").is_file()


def test_a_shallower_sync_does_not_report_deeper_files(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    capsys.readouterr()

    rc = cli_main(["sync-openapi", str(dest), "--file", str(FIXTURE), "--depth", "resources"])

    assert rc == 0
    assert "Orphaned" not in capsys.readouterr().out


def test_entities_limit_what_prune_may_touch(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    shrunk = _shrunk_spec(tmp_path)

    assert _sync(dest, shrunk, "--prune", "--entities", "items") == 0

    # the items orphan is in scope, the vanished health tag is not
    assert not (dest / "src/api/resources/payloads/items/post_items_payload.py").exists()
    assert (dest / "src/api/resources/collections/collection_health.py").is_file()


# --- shared modules under --entities ------------------------------------------------------


def test_sync_with_entities_keeps_the_other_collections_wired(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)

    assert _sync(dest, FIXTURE, "--entities", "items") == 0

    manager = (dest / "src/api/resources/collections/collections_manager.py").read_text(
        encoding="utf-8"
    )
    assert "collection_health" in manager
    paths = (dest / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    assert "PathsHealth" in paths
    _assert_models_build(dest)


# --- the floor seeded into a project ---------------------------------------------------


def test_seeded_partest_floor_matches_our_own(tmp_path: Path):
    setup_py = (LIB_ROOT / "setup.py").read_text(encoding="utf-8")
    own = re.search(r'"partest>=([0-9.]+)"', setup_py)
    assert own, "setup.py no longer declares a partest floor"
    dest = tmp_path / "suite"
    _generate(dest, "--with-ui")
    api = (dest / "requirements/api.txt").read_text(encoding="utf-8")
    ui = (dest / "requirements/ui.txt").read_text(encoding="utf-8")
    assert f"partest>={own.group(1)}\n" in api
    assert f"partest[ui]>={own.group(1)}\n" in ui
    flat = RootFilesContainer().get_file_by_name("requirements.txt")
    assert f"partest>={own.group(1)}\n" in flat.content


def test_banner_line_is_unchanged_since_the_last_release():
    """Every tree generated so far carries exactly this line; changing it orphans them all."""
    assert _BANNER_LINE == "# AUTO-GENERATED by partest-gen — do not edit by hand."


# --- links, wrong specifications, --entities, deprecated operations, failed deletes -------


def test_sync_does_not_write_through_a_junction(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "test_health_default.py"
    victim.write_text(GENERATED_BANNER + "x = 1\n", encoding="utf-8")
    health = dest / "src/api/tests/health"
    for p in sorted(health.rglob("*"), reverse=True):
        p.rmdir() if p.is_dir() else p.unlink()
    health.rmdir()
    _link_dir(health, outside)
    capsys.readouterr()

    try:
        assert _sync(dest, FIXTURE) == 0
        out = capsys.readouterr().out
        assert victim.read_text(encoding="utf-8") == GENERATED_BANNER + "x = 1\n"
        assert "Not written — a link" in out
        assert "x src/api/tests/health/test_health_default.py" in out
        assert "Links not traversed" in out
    finally:
        os.rmdir(health) if os.name == "nt" else health.unlink()


def test_prune_refuses_a_specification_of_another_api(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    before = _tree(dest)

    def edit(spec):
        spec["paths"] = {"/orders": {"get": {"tags": ["orders"], "responses": {"200": {
            "description": "OK"}}}}}

    other = _spec(tmp_path, "other.yaml", edit)

    rc = _sync(dest, other, "--prune")

    assert rc == 2
    err = capsys.readouterr().err
    assert "--prune refused" in err and "health" in err and "orders" in err
    assert _tree(dest) == before


def test_entities_after_another_tag_changed_keep_every_model_importable(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)

    def edit(spec):
        spec["paths"]["/healthz"] = spec["paths"].pop("/health")

    changed = _spec(tmp_path, "changed.yaml", edit)

    assert _sync(dest, changed, "--entities", "items") == 0

    _assert_models_build(dest)
    facade = (dest / "src/api/resources/collections/collection_health.py").read_text(
        encoding="utf-8"
    )
    assert "/healthz" in facade


@pytest.mark.parametrize("command", ["sync-openapi", "from-openapi"])
def test_entities_matching_no_tag_are_refused(tmp_path: Path, capsys, command):
    dest = tmp_path / "suite"
    _generate(dest)
    before = _tree(dest)
    capsys.readouterr()

    rc = cli_main([command, str(dest), "--file", str(FIXTURE), "--entities", "nosuchtag"])

    assert rc == 2
    err = capsys.readouterr().err
    assert "matches no tag" in err and "health" in err and "items" in err
    assert _tree(dest) == before


def test_plan_never_runs_with_an_empty_tag_selection():
    with pytest.raises(ValueError):
        _plan_resources(load_openapi(FIXTURE), tags_filter=["nosuchtag"])


def test_a_tag_left_with_only_deprecated_operations_keeps_working(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)

    def edit(spec):
        spec["paths"]["/health"]["get"]["deprecated"] = True

    assert _sync(dest, _spec(tmp_path, "deprecated.yaml", edit), "--prune") == 0

    test_file = dest / "src/api/tests/health/test_health_default.py"
    attrs = sorted(set(re.findall(r"models\.health\.paths\.(\w+)", test_file.read_text(
        encoding="utf-8"))))
    assert attrs, "the kept test no longer names a path"
    code = (
        "import sys, importlib; sys.path.insert(0, '.')\n"
        "importlib.import_module('src.api.tests.health.test_health_default')\n"
        "from src.api.resources.collections.factory import build_models\n"
        "m = build_models()\n"
        f"print('ok', [getattr(m.health.paths, a) for a in {attrs!r}])\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=dest,
        env={**os.environ, "PYTHONPATH": str(LIB_ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "ok ['/health']" in r.stdout


def test_prune_reports_what_it_could_not_delete(tmp_path: Path, monkeypatch, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    stuck = "test_health_default.py"
    real_unlink = Path.unlink

    def unlink(self, *a, **k):
        if self.name == stuck:
            raise PermissionError("locked")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", unlink)
    capsys.readouterr()

    rc = _sync(dest, _shrunk_spec(tmp_path), "--prune")

    out = capsys.readouterr().out
    assert rc == 1
    assert "- src/api/resources/collections/collection_health.py" in out
    assert f"? src/api/tests/health/{stuck}" in out
    assert (dest / "src/api/tests/health" / stuck).is_file()


def test_an_edited_shared_module_is_named_with_a_way_back(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    assert cli_main(["init", str(dest)]) == 0
    manager = dest / "src/api/resources/collections/collections_manager.py"
    manager.write_text(manager.read_text(encoding="utf-8") + "# mine\n", encoding="utf-8")
    capsys.readouterr()

    assert _sync(dest, FIXTURE) == 0

    out = capsys.readouterr().out
    assert "Kept src/api/resources/collections/collections_manager.py" in out
    assert "Delete it and run sync again" in out


# --- ownership marks pinned -----------------------------------------------------------------


def test_checklist_marks_are_pinned():
    """Every checklist written so far carries these strings; changing one silently moves
    checklists between the generator and the user."""
    assert _MD_BANNER_LINE == "AUTO-GENERATED by partest-gen — do not edit by hand."
    assert _CHECKLIST_SYNC_NOTE == "Rewritten on every sync."
    assert _LEGACY_CHECKLIST_NOTE == "Mark when implemented for real."


def test_the_sync_note_is_a_paragraph_of_its_own(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    lines = _checklist(dest).read_text(encoding="utf-8").splitlines()
    i = lines.index(_CHECKLIST_SYNC_NOTE)
    assert lines[i - 1] == "" and lines[i + 1] == ""


def test_markdown_ownership_predicate():
    banner = GENERATED_BANNER.replace("# ", "")
    current = banner + "\n# P1\n\n" + _CHECKLIST_SYNC_NOTE + "\n\n| a |\n"
    assert _is_generated("P1_CHECKLIST.md", current)
    assert _is_generated("P1_CHECKLIST.md", "\ufeff" + current)
    # banner not first
    assert not _is_generated("P1_CHECKLIST.md", "# mine\n" + current)
    # no sync note, or the note only inside a sentence
    assert not _is_generated("P1_CHECKLIST.md", banner + "\n# P1\n")
    assert not _is_generated(
        "P1_CHECKLIST.md", banner + "\nIt is " + _CHECKLIST_SYNC_NOTE + " Really.\n"
    )
    # the legacy phrase makes it the user's even with the note
    legacy = current + _LEGACY_CHECKLIST_NOTE + "\n"
    assert not _is_generated("P1_CHECKLIST.md", legacy)
    assert _is_legacy_checklist(legacy)
    assert not _is_legacy_checklist(current)


def test_from_openapi_names_a_legacy_checklist(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    checklist = _checklist(dest)
    checklist.write_text(
        GENERATED_BANNER.replace("# ", "") + "\n" + _LEGACY_CHECKLIST_NOTE + "\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    _generate(dest)

    assert "Kept src/api/tests/items/P1_CHECKLIST.md" in capsys.readouterr().out


def test_bom_prefixed_placeholder_is_still_a_placeholder():
    rel = "src/api/resources/endpoints/paths.py"
    text = _RELEASED_PLACEHOLDERS[rel][0].encode("utf-8")
    assert _is_skeleton_placeholder(rel, b"\xef\xbb\xbf" + text)


def test_write_file_follows_the_same_ownership_rules(tmp_path: Path):
    from partest_gen.emitters.util import write_file
    from partest_gen.skeleton import WriteResult

    root = tmp_path
    owned = root / "a.py"
    owned.write_text(GENERATED_BANNER + "old\n", encoding="utf-8")
    mine = root / "b.py"
    mine.write_text("# AUTO-GENERATED by partest-gen\nmine\n", encoding="utf-8")
    result = WriteResult()

    write_file(root, "a.py", GENERATED_BANNER + "new\n", force=False, result=result, always=True)
    write_file(root, "b.py", GENERATED_BANNER + "new\n", force=False, result=result, always=True)

    assert owned.read_text(encoding="utf-8").endswith("new\n")
    assert mine.read_text(encoding="utf-8").endswith("mine\n")


# --- remove_orphans re-checks ---------------------------------------------------------------


def test_remove_orphans_rechecks_each_path_before_deleting(tmp_path: Path):
    root = tmp_path / "suite"
    base = root / "src/api/tests/gone"
    base.mkdir(parents=True)
    unbannered = base / "test_edited.py"
    unbannered.write_text("# mine now\n", encoding="utf-8")
    quoted = base / "test_quoted.py"
    quoted.write_text("x = 1\n" + GENERATED_BANNER, encoding="utf-8")
    a_dir = base / "test_dir.py"
    a_dir.mkdir()

    removed = remove_orphans(
        root,
        [
            "src/api/tests/gone/test_edited.py",
            "src/api/tests/gone/test_quoted.py",
            "src/api/tests/gone/test_dir.py",
        ],
    )

    assert removed == []
    assert unbannered.is_file() and quoted.is_file() and a_dir.is_dir()


def test_a_pycache_with_other_files_keeps_its_directory(tmp_path: Path):
    root = tmp_path / "suite"
    orphan = root / "src/api/tests/gone/test_gone.py"
    orphan.parent.mkdir(parents=True)
    orphan.write_text(GENERATED_BANNER, encoding="utf-8")
    cache = orphan.parent / "__pycache__"
    cache.mkdir()
    (cache / "notes.txt").write_text("keep", encoding="utf-8")

    assert remove_orphans(root, ["src/api/tests/gone/test_gone.py"]) == [
        "src/api/tests/gone/test_gone.py"
    ]

    assert (cache / "notes.txt").is_file()


def test_a_link_inside_a_package_keeps_its_init(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    target = dest / "src/api/tests/items"
    link = dest / "src/api/tests/health/shared"
    _link_dir(link, target)

    try:
        assert _sync(dest, _shrunk_spec(tmp_path), "--prune") == 0
        assert (dest / "src/api/tests/health/__init__.py").is_file()
        assert not (dest / "src/api/tests/health/test_health_default.py").exists()
        assert (target / "test_items_default.py").is_file()
    finally:
        os.rmdir(link) if os.name == "nt" else link.unlink()


# --- layout ---------------------------------------------------------------------------------


def test_every_planned_file_lies_under_a_generated_root_with_its_tag():
    suite = load_openapi(FIXTURE)
    full = _plan_resources(suite, depth="p1")
    for rel in full:
        assert any(rel.startswith(base + "/") for base in _GENERATED_ROOTS), rel
    per_tag = {t: set(_plan_resources(suite, tags_filter=[t], depth="p1")) for t in suite.tags()}
    shared = set.intersection(*per_tag.values())
    for tag, rels in per_tag.items():
        for rel in rels - shared:
            assert _file_tag(rel) == is_snake(tag), rel
    for rel in shared:
        assert _file_tag(rel) is None, rel


# --- names, hostile specifications, shallow runs -------------------------------------------


def _minimal_spec(tmp_path: Path, name: str, paths: dict) -> Path:
    spec = {"openapi": "3.0.3", "info": {"title": "T", "version": "1"}, "paths": paths}
    out = tmp_path / name
    out.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out


def test_a_live_operation_keeps_its_name_next_to_a_deprecated_twin(tmp_path: Path):
    ok = {"200": {"description": "OK"}}
    spec = _minimal_spec(
        tmp_path,
        "twins.yaml",
        {
            # sorts first, collides on `items_by_item_id`, and is deprecated
            "/items/{itemId}": {"get": {"tags": ["items"], "deprecated": True, "responses": ok}},
            "/items/{item_id}": {"get": {"tags": ["items"], "responses": ok}},
        },
    )
    dest = tmp_path / "suite"
    assert cli_main(["from-openapi", str(dest), "--file", str(spec), "--depth", "resources"]) == 0

    paths = (dest / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    assert 'self.items_by_item_id = "/items/{item_id}"' in paths
    assert 'self.items_by_item_id_2 = "/items/{itemId}"' in paths


_CANARY = "PWNED"


def test_hostile_strings_in_the_specification_stay_strings(tmp_path: Path):
    """Paths, operationIds, summaries, property and parameter names come from outside. Every
    emitted module must compile, and importing it must not run anything they carry."""
    payload = f'open("{_CANARY}", "w").close()'
    hostile_path = '/ev"; ' + payload + '; x = "'
    ok = {"200": {"description": "OK", "content": {"application/json": {"schema": {
        "type": "object",
        "properties": {
            f'x: int = 1\n{payload}\ny': {"type": "string"},
            "first-name": {"type": "string"},
            "class": {"type": "integer"},
        },
        "required": ["first-name"],
    }}}}}
    spec = _minimal_spec(
        tmp_path,
        "hostile.yaml",
        {
            hostile_path: {
                "post": {
                    "tags": ["evil"],
                    "operationId": f"op\n{payload}\n#",
                    "summary": f'""" + {payload} + """',
                    "parameters": [
                        {"name": f'q"\n{payload}\n', "in": "query", "schema": {"type": "string"}}
                    ],
                    "requestBody": {"content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {f'n"\n{payload}\n#': {"type": "string"}},
                    }}}},
                    "responses": ok,
                },
                "get": {"tags": ["evil"], "parameters": [
                    {"name": f'q"\n{payload}\n', "in": "query", "schema": {"type": "string"}}
                ], "responses": ok},
            }
        },
    )
    dest = tmp_path / "suite"
    assert cli_main(["from-openapi", str(dest), "--file", str(spec), "--depth", "p1"]) == 0

    for path in (dest / "src").rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

    modules = sorted(
        ".".join(p.relative_to(dest).with_suffix("").parts)
        for p in (dest / "src/api").rglob("*.py")
        if p.name != "conftest.py"
    )
    code = (
        "import importlib, sys; sys.path.insert(0, '.')\n"
        f"for m in {modules!r}:\n"
        "    importlib.import_module(m)\n"
        "print('imported')\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=dest,
        env={**os.environ, "PYTHONPATH": str(LIB_ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert not (dest / _CANARY).exists(), "a string from the specification ran as code"
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    paths = (dest / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    assert '"/ev\\"; open(\\"PWNED' in paths


def test_a_shallow_entities_run_keeps_other_facades_wired(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    wired = (dest / "src/api/resources/collections/collection_items.py").read_text(
        encoding="utf-8"
    )
    assert "_payload import" in wired

    def edit(spec):
        spec["paths"]["/health"]["get"]["summary"] = "changed"

    changed = _spec(tmp_path, "changed.yaml", edit)
    rc = cli_main(
        ["sync-openapi", str(dest), "--file", str(changed), "--entities", "health",
         "--depth", "resources"]
    )

    assert rc == 0
    after = (dest / "src/api/resources/collections/collection_items.py").read_text(
        encoding="utf-8"
    )
    assert "_payload import" in after and "_validation import" in after
    _assert_models_build(dest)


def test_renamed_tags_are_pruned_in_the_two_steps_the_refusal_names(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)

    def edit(spec):
        for item in spec["paths"].values():
            for op in item.values():
                if isinstance(op, dict) and "tags" in op:
                    op["tags"] = ["goods" if t == "items" else "status" for t in op["tags"]]

    renamed = _spec(tmp_path, "renamed.yaml", edit)
    capsys.readouterr()

    assert _sync(dest, renamed, "--prune") == 2
    err = capsys.readouterr().err
    assert "without --prune" in err and "then again with --prune" in err

    assert _sync(dest, renamed) == 0
    assert _sync(dest, renamed, "--prune") == 0
    assert not (dest / "src/api/resources/collections/collection_items.py").exists()
    assert (dest / "src/api/resources/collections/collection_goods.py").is_file()
    r = _build_models_script(dest, "print('ok', type(build_models().goods).__name__)")
    assert "ok GoodsCollection" in r.stdout, r.stderr


def _build_models_script(dest: Path, line: str) -> subprocess.CompletedProcess:
    code = (
        "import sys; sys.path.insert(0, '.')\n"
        "from src.api.resources.collections.factory import build_models\n" + line + "\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=dest,
        env={**os.environ, "PYTHONPATH": str(LIB_ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_prune_names_what_it_skipped_on_recheck(tmp_path: Path, monkeypatch, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    import partest_gen.emitters.resources as res

    real = res._read_generated
    edited = "src/api/tests/health/test_health_default.py"

    def read_generated(path, rel):
        # the user edits the file between the scan and the deletion
        if rel == edited:
            return False
        return real(path, rel)

    monkeypatch.setattr(res, "_read_generated", read_generated)
    monkeypatch.setattr(res, "find_orphans", lambda *a, **k: [edited])
    import partest_gen.emitters as em

    monkeypatch.setattr(em, "find_orphans", res.find_orphans)
    capsys.readouterr()

    rc = _sync(dest, _shrunk_spec(tmp_path), "--prune")

    out = capsys.readouterr().out
    assert rc == 0
    assert "Skipped on recheck" in out and f"= {edited}" in out
    assert (dest / edited).is_file()


def test_entities_name_other_tags_whose_paths_changed(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)

    def edit(spec):
        spec["paths"]["/healthz"] = spec["paths"].pop("/health")

    capsys.readouterr()
    assert _sync(dest, _spec(tmp_path, "changed.yaml", edit), "--entities", "items") == 0

    out = capsys.readouterr().out
    assert "Paths changed for tags outside --entities: health" in out


# --- links everywhere the generator writes -------------------------------------------------


def test_a_junction_inside_the_project_is_not_written_through(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    items_before = _tree(dest / "src/api/tests/items")
    health = dest / "src/api/tests/health"
    for p in sorted(health.rglob("*"), reverse=True):
        p.rmdir() if p.is_dir() else p.unlink()
    health.rmdir()
    _link_dir(health, dest / "src/api/tests/items")
    capsys.readouterr()

    try:
        assert _sync(dest, FIXTURE) == 0
        out = capsys.readouterr().out
        assert "x src/api/tests/health/test_health_default.py" in out
        assert _tree(dest / "src/api/tests/items") == items_before
    finally:
        os.rmdir(health) if os.name == "nt" else health.unlink()


def test_the_orphan_scan_does_not_enter_a_link_inside_the_project(tmp_path: Path):
    dest = tmp_path / "suite"
    _generate(dest)
    scratch = dest / "scratch"
    scratch.mkdir()
    (scratch / "test_gone_default.py").write_text(GENERATED_BANNER, encoding="utf-8")
    link = dest / "src/api/tests/linked"
    _link_dir(link, scratch)

    try:
        links: list = []
        found = find_orphans(dest, load_openapi(FIXTURE), links=links)
        assert not any(r.startswith("src/api/tests/linked/") for r in found)
        assert "src/api/tests/linked" in links
    finally:
        os.rmdir(link) if os.name == "nt" else link.unlink()


def test_init_does_not_write_through_a_junction(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    dest.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _link_dir(dest / "src", outside)
    capsys.readouterr()

    try:
        assert cli_main(["from-openapi", str(dest), "--file", str(FIXTURE)]) == 0
        out = capsys.readouterr().out
        assert list(outside.iterdir()) == [], "init wrote outside the project"
        assert "x src/api/tests/conftest.py" in out
    finally:
        os.rmdir(dest / "src") if os.name == "nt" else (dest / "src").unlink()


def test_sync_does_not_write_ir_or_spec_through_a_junction(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    for name in (".partest", "docs"):
        outside = tmp_path / f"outside_{name}"
        outside.mkdir()
        for p in sorted((dest / name).rglob("*"), reverse=True):
            p.rmdir() if p.is_dir() else p.unlink()
        (dest / name).rmdir()
        (outside / "suite_ir.json").write_text("{}", encoding="utf-8")
        (outside / "openapi.yaml").write_text("mine", encoding="utf-8")
        _link_dir(dest / name, outside)
    capsys.readouterr()

    try:
        assert _sync(dest, FIXTURE) == 0
        out = capsys.readouterr().out
        for name in (".partest", "docs"):
            outside = tmp_path / f"outside_{name}"
            assert (outside / "suite_ir.json").read_text(encoding="utf-8") == "{}"
            assert (outside / "openapi.yaml").read_text(encoding="utf-8") == "mine"
        assert "x .partest/suite_ir.json" in out
        assert "x docs/openapi.yaml" in out
    finally:
        for name in (".partest", "docs"):
            os.rmdir(dest / name) if os.name == "nt" else (dest / name).unlink()


def test_init_ui_does_not_write_through_a_junction(tmp_path: Path, capsys):
    dest = tmp_path / "suite"
    _generate(dest)
    outside = tmp_path / "outside"
    outside.mkdir()
    _link_dir(dest / "src/ui", outside)
    capsys.readouterr()

    try:
        assert cli_main(["init-ui", str(dest)]) == 0
        assert list(outside.iterdir()) == []
        assert "Not written — a link" in capsys.readouterr().out
    finally:
        os.rmdir(dest / "src/ui") if os.name == "nt" else (dest / "src/ui").unlink()


# --- keywords, reserved field names, invisible characters, unwritable specifications --------


def _import_all(dest: Path) -> subprocess.CompletedProcess:
    modules = sorted(
        ".".join(p.relative_to(dest).with_suffix("").parts)
        for p in (dest / "src/api").rglob("*.py")
        if p.name != "conftest.py"
    )
    code = (
        "import importlib, sys; sys.path.insert(0, '.')\n"
        f"for m in {modules!r}:\n"
        "    importlib.import_module(m)\n"
        "from src.api.resources.collections.factory import build_models\n"
        "build_models()\n"
        "print('imported')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=dest,
        env={**os.environ, "PYTHONPATH": str(LIB_ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_python_keywords_as_tags_and_paths(tmp_path: Path):
    ok = {"200": {"description": "OK"}}
    spec = _minimal_spec(
        tmp_path,
        "keywords.yaml",
        {
            "/import": {"post": {"tags": ["class"], "responses": ok, "requestBody": {"content": {
                "application/json": {"schema": {"type": "object", "properties": {
                    "a": {"type": "string"}}}}}}}},
            "/async": {"get": {"tags": ["import"], "responses": ok}},
            "/match": {"get": {"tags": ["type"], "responses": ok}},
        },
    )
    dest = tmp_path / "suite"
    assert cli_main(["from-openapi", str(dest), "--file", str(spec), "--depth", "p1"]) == 0

    r = _import_all(dest)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    paths = (dest / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    assert 'self.import_ = "/import"' in paths
    # soft keywords are valid names and keep them
    assert 'self.match = "/match"' in paths
    assert (dest / "src/api/resources/collections/collection_class_.py").is_file()
    assert (dest / "src/api/resources/collections/collection_type.py").is_file()


def test_property_names_that_would_shadow_the_module_become_aliases(tmp_path: Path):
    names = ["Field", "str", "model_config", "__class__", "_priv", "Optional", "List",
             "BaseModel", "model_x", "id", "type"]
    ok = {"200": {"description": "OK", "content": {"application/json": {"schema": {
        "type": "object",
        "properties": {n: {"type": "string"} for n in names},
        "required": ["str", "Field"],
    }}}}}
    spec = _minimal_spec(tmp_path, "shadow.yaml", {"/things": {"get": {"tags": ["things"],
                                                                        "responses": ok}}})
    dest = tmp_path / "suite"
    assert cli_main(["from-openapi", str(dest), "--file", str(spec)]) == 0

    r = _import_all(dest)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    module = next((dest / "src/api/resources/validations/things").glob("*_validation.py"))
    text = module.read_text(encoding="utf-8")
    assert 'field_str: str = Field(..., alias="str")' in text
    assert 'alias="model_config"' in text and 'alias="__class__"' in text
    # ordinary names, builtins among them, stay what the API calls them
    assert "    id: Optional[str] = Field(None)" in text
    assert "    type: Optional[str] = Field(None)" in text


def test_invisible_characters_are_escaped_in_code_and_markdown(tmp_path: Path):
    tricky = "\u202e\u2066\u200b\u2028\u2029\x85\ufeff"
    ok = {"200": {"description": "OK"}}
    spec = _minimal_spec(
        tmp_path,
        "invisible.yaml",
        {f"/a{tricky}|`b": {"get": {"tags": ["t"], "operationId": f"id{tricky}",
                                     "summary": f"s{tricky}", "responses": ok}}},
    )
    dest = tmp_path / "suite"
    assert cli_main(["from-openapi", str(dest), "--file", str(spec), "--depth", "p1"]) == 0

    for path in list((dest / "src").rglob("*.py")) + list((dest / ".partest").glob("*.md")) + list(
        (dest / "src").rglob("*.md")
    ):
        text = path.read_text(encoding="utf-8")
        for ch in tricky:
            assert ch not in text, f"{path.name} carries U+{ord(ch):04X} raw"
    summary = (dest / ".partest/openapi_summary.md").read_text(encoding="utf-8")
    assert "\\u202e" in summary and "\\|" in summary
    assert _import_all(dest).returncode == 0


def test_the_title_is_shown_without_its_control_characters(tmp_path: Path, capsys):
    spec = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    spec["info"]["title"] = "Shop\x1b[31mRED\x1b[0m"
    path = tmp_path / "ansi.yaml"
    path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    dest = tmp_path / "suite"

    assert cli_main(["from-openapi", str(dest), "--file", str(path)]) == 0
    assert _sync(dest, path) == 0

    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "Shop\\u001b[31mRED" in out


@pytest.mark.parametrize("command", ["from-openapi", "sync-openapi"])
def test_a_lone_surrogate_is_refused_before_anything_is_written(tmp_path: Path, capsys, command):
    spec = FIXTURE.read_text(encoding="utf-8").replace(
        "title: Sample Shop API", 'title: "Sample \\ud800 Shop"'
    )
    path = tmp_path / "surrogate.yaml"
    path.write_text(spec, encoding="utf-8")
    dest = tmp_path / "suite"
    if command == "sync-openapi":
        _generate(dest)
    before = _tree(dest) if dest.exists() else {}

    rc = cli_main([command, str(dest), "--file", str(path)])

    assert rc == 2
    assert "lone surrogate" in capsys.readouterr().err
    assert (_tree(dest) if dest.exists() else {}) == before


def test_a_windows_device_name_as_a_tag_is_refused(tmp_path: Path):
    from partest_gen.emitters.util import _unwritable

    def edit(spec):
        spec["paths"]["/health"]["get"]["tags"] = ["NUL"]

    suite = load_openapi(_spec(tmp_path, "nul.yaml", edit))
    problems = _unwritable(suite, windows=True)
    assert problems and "device name" in problems[0]
    assert _unwritable(suite, windows=False) == []
    with pytest.raises(ValueError):
        from partest_gen.emitters import emit_resources

        if os.name == "nt":
            emit_resources(tmp_path / "suite", suite)
        else:
            raise ValueError("only Windows refuses")


def test_the_project_name_cannot_inject_into_confpartest(tmp_path: Path):
    dest = tmp_path / "suite"
    name = 'a"]}; open("PWNED", "w").close(); x = {"'
    assert cli_main(["init", str(dest), "--name", name]) == 0

    conf = (dest / "confpartest.py").read_text(encoding="utf-8")
    namespace: dict = {}
    exec(compile(conf, "confpartest.py", "exec"), namespace)  # noqa: S102 — the point of the test
    assert list(namespace["swagger_files"]) == [name]
    assert not (dest / "PWNED").exists() and not Path("PWNED").exists()


def test_integer_id_properties_keep_the_payload_compilable(tmp_path: Path):
    """An ``*_id`` default carries a TODO comment; the comma must not end up inside it."""
    body = {"type": "object", "required": ["id", "user_id"], "properties": {
        "id": {"type": "integer"}, "user_id": {"type": "integer"}, "name": {"type": "string"}}}
    spec = _minimal_spec(tmp_path, "ids.yaml", {"/users": {"post": {
        "tags": ["users"], "responses": {"201": {"description": "Created"}},
        "requestBody": {"content": {"application/json": {"schema": body}}}}}})
    dest = tmp_path / "suite"
    assert cli_main(["from-openapi", str(dest), "--file", str(spec), "--depth", "p1"]) == 0

    module = dest / "src/api/resources/payloads/users/post_users_payload.py"
    text = module.read_text(encoding="utf-8")
    assert '"id": 0,  # TODO' in text and '"user_id": 0,  # TODO' in text
    r = _import_all(dest)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
