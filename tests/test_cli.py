"""The command line surface: subcommands, and the version a bug report needs.

The emitters have their own tests. This file covers the layer above them — that a command
exists, parses what it claims to parse, and reports the right thing on bad input.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from partest_gen import __version__
from partest_gen.cli import build_parser, main as cli_main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_version_flag_reports_the_package_version(capsys):
    """A generated tree carries no version; the CLI is the only way to ask which one wrote it."""
    with pytest.raises(SystemExit) as exit_info:
        cli_main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_every_documented_command_is_registered():
    """The skill and the wiki name these; a rename must break here, not in someone's terminal."""
    parser = build_parser()
    actions = [a for a in parser._actions if getattr(a, "choices", None) and hasattr(a, "_name_parser_map")]
    assert actions, "no subparsers found"
    commands = set(actions[0].choices)
    assert commands == {
        "init",
        "init-ui",
        "from-openapi",
        "sync-openapi",
        "dump-ir",
        "init-package-exports",
    }


def test_init_package_exports_writes_reexports(tmp_path: Path):
    pkg = tmp_path / "res"
    pkg.mkdir()
    (pkg / "paths.py").write_text("P=1\n", encoding="utf-8")

    assert cli_main(["init-package-exports", str(pkg), "-v"]) == 0
    assert "from .paths import *" in (pkg / "__init__.py").read_text(encoding="utf-8")


def test_dump_ir_writes_json_without_touching_a_project(tmp_path: Path):
    """The one command that is safe to run against a directory you care about."""
    out = tmp_path / "suite_ir.json"
    assert cli_main(["dump-ir", str(FIXTURE), "-o", str(out)]) == 0
    assert out.is_file()
    assert out.read_text(encoding="utf-8").strip().startswith("{")
    assert list(tmp_path.iterdir()) == [out], "dump-ir must write only the file it was asked for"


def test_sync_without_a_project_fails_instead_of_creating_one(tmp_path: Path, capsys):
    """A typo in the path must not silently scaffold a project somewhere unexpected."""
    missing = tmp_path / "not-here"
    code = cli_main(["sync-openapi", str(missing), "--file", str(FIXTURE)])
    assert code != 0
    assert not missing.exists()
    assert "not found" in capsys.readouterr().err
