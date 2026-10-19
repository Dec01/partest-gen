"""G5: deep UI monorepo layout."""

from __future__ import annotations

import re
from pathlib import Path

from partest_gen.cli import main as cli_main
from partest_gen.skeleton import apply_ui_layout, init_skeleton
from partest_gen.ui_layout import build_ui_files


def test_build_ui_files_has_core_tree():
    files = build_ui_files(project_name="demo")
    expected = [
        "src/ui/conftest.py",
        "src/ui/pages/base_page.py",
        "src/ui/pages/login_page.py",
        "src/ui/utils/page_monitor.py",
        "src/ui/utils/health.py",
        "src/ui/utils/visual_compare.py",
        "src/ui/fixtures/auth.py",
        "src/ui/fixtures/api_seed.py",
        "src/ui/tests/smoke/test_ui_smoke.py",
        "src/ui/tests/visual/test_visual_smoke.py",
        "src/ui/tools/capture_baselines.py",
        "src/ui/tools/scenes.example.json",
        "scripts/run_ui.ps1",
        "scripts/run_ui.sh",
        "docs/UI_GUIDE.md",
        "src/ui/README.md",
    ]
    for rel in expected:
        assert rel in files, f"missing {rel}"
    assert "isolated" in files["src/ui/conftest.py"].lower() or "OpenAPI" in files["src/ui/conftest.py"]
    assert "pytest_plugins" in files["src/ui/conftest.py"]
    assert "partest.ui.pytest_plugin" in files["src/ui/conftest.py"]
    assert "async_playwright" not in files["src/ui/conftest.py"]
    assert "from partest.ui import BasePage" in files["src/ui/pages/base_page.py"]
    assert "AsyncBasePage" not in files["src/ui/pages/base_page.py"]
    assert "capture_baselines_sync" in files["src/ui/tools/capture_baselines.py"]
    smoke = files["src/ui/tests/smoke/test_ui_smoke.py"]
    assert "@pytest.mark.asyncio" not in smoke
    assert "await " not in smoke


def test_init_with_ui(tmp_path: Path):
    root = tmp_path / "suite"
    result = init_skeleton(root, name="shop", with_ui=True, force=True)
    assert (root / "src/ui/conftest.py").is_file()
    assert (root / "src/ui/utils/page_monitor.py").is_file()
    assert (root / "docs/UI_GUIDE.md").is_file()
    assert (root / "scripts/run_ui.ps1").is_file()
    env = (root / "env.example").read_text(encoding="utf-8")
    assert "FRONTEND_URL" in env
    assert result.created


def test_init_ui_on_existing(tmp_path: Path):
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", with_ui=False, force=True)
    assert not (root / "src/ui/conftest.py").exists()
    apply_ui_layout(root, name="shop", force=True)
    assert (root / "src/ui/tests/smoke/test_ui_smoke.py").is_file()
    assert (root / "src/ui/baselines/reference/.gitkeep").is_file()


def test_cli_init_ui(tmp_path: Path):
    dest = tmp_path / "proj"
    cli_main(["init", str(dest), "--name", "demo", "--force"])
    rc = cli_main(["init-ui", str(dest), "--force", "-v"])
    assert rc == 0
    assert (dest / "src/ui/README.md").is_file()
    assert (dest / "docs/UI_GUIDE.md").is_file()


def test_page_monitor_reexports_library(tmp_path: Path):
    """G5 utils re-export partest.ui (1.3)."""
    files = build_ui_files()
    assert "from partest.ui.page_monitor import" in files["src/ui/utils/page_monitor.py"]
    assert "BasePage" in files["src/ui/pages/base_page.py"]
    assert "partest.ui" in files["src/ui/pages/base_page.py"]


# --- the browser checks certificates ----------------------------------------------------------

# Runs the generated src/ui/conftest.py with pytest.fixture as the identity, so the session
# fixture can be called with a plain dict; a fresh interpreter, because partest warns about an
# unverified run once per process.
_CONTEXT_PROBE = """
import sys, warnings
warnings.simplefilter("always")
import pytest
pytest.fixture = lambda *a, **k: a[0] if a and callable(a[0]) else (lambda f: f)
ns = {"__name__": "ui_conftest"}
source = open(sys.argv[1], encoding="utf-8").read()
exec(compile(source, sys.argv[1], "exec"), ns)
args = ns["browser_context_args"]({"locale": "en-US"}, "https://ui.example")
print("IGNORE", args["ignore_https_errors"], args["locale"], args["base_url"])
"""


def _browser_context(tmp_path: Path, tls_verify):
    import os
    import subprocess
    import sys

    conftest = tmp_path / "ui_conftest.py"
    conftest.write_text(build_ui_files()["src/ui/conftest.py"], encoding="utf-8")
    probe = tmp_path / "probe.py"
    probe.write_text(_CONTEXT_PROBE, encoding="utf-8")
    # A project file that turns verification off: the browser must not see it.
    (tmp_path / "confpartest.py").write_text("tls_verify = False\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PARTEST_TLS_VERIFY"}
    if tls_verify is not None:
        env["PARTEST_TLS_VERIFY"] = tls_verify
    r = subprocess.run(
        [sys.executable, str(probe), str(conftest)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    line = next(ln for ln in r.stdout.splitlines() if ln.startswith("IGNORE "))
    return line.split()[1:], r.stderr


def test_ui_conftest_does_not_switch_certificate_checking_off_in_its_text():
    conftest = build_ui_files()["src/ui/conftest.py"]
    assert '"ignore_https_errors": True' not in conftest
    assert '"ignore_https_errors": ignore_https_errors()' in conftest
    # public partest only, and the UI road: the environment, never confpartest
    assert "from partest.ui import ignore_https_errors" in conftest
    assert not re.search(r"^\s*(import|from)\s+confpartest", conftest, re.M)
    assert "PARTEST_TLS_VERIFY" in conftest


def test_the_browser_checks_certificates_by_default(tmp_path: Path):
    (ignore, locale, base_url), err = _browser_context(tmp_path, None)
    assert ignore == "False"
    # tls_verify = False in confpartest.py does not reach a UI job
    assert "TLSVerificationDisabled" not in err
    # what pytest-playwright and the project set is kept
    assert (locale, base_url) == ("en-US", "https://ui.example")


def test_partest_tls_verify_off_switches_the_browser_check_off_and_warns(tmp_path: Path):
    (ignore, *_), err = _browser_context(tmp_path, "0")
    assert ignore == "True"
    assert "TLSVerificationDisabled" in err


def test_a_ca_bundle_keeps_the_browser_check_on_and_says_so(tmp_path: Path):
    bundle = tmp_path / "corp-ca.pem"
    bundle.write_text("not read by the browser\n", encoding="utf-8")
    (ignore, *_), err = _browser_context(tmp_path, str(bundle))
    assert ignore == "False"
    assert "cannot be given to a browser" in err


def test_ui_conftest_imports_nothing_it_does_not_use():
    import ast

    tree = ast.parse(build_ui_files()["src/ui/conftest.py"])
    imported = {
        (a.asname or a.name).split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for a in node.names
    } - {"annotations"}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    assert imported <= used, f"unused imports: {imported - used}"


def test_the_generated_ui_docs_and_env_name_the_tls_switch(tmp_path: Path):
    files = build_ui_files()
    for rel in ("src/ui/README.md", "docs/UI_GUIDE.md"):
        assert "PARTEST_TLS_VERIFY=0" in files[rel], rel
        assert "trust store" in files[rel], rel
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", with_ui=True, force=True)
    assert "# PARTEST_TLS_VERIFY=" in (root / "env.example").read_text(encoding="utf-8")


def test_deleting_the_ui_conftest_and_rerunning_init_ui_recreates_only_it(tmp_path: Path):
    """The upgrade path the CHANGELOG offers for trees generated before the browser checked
    certificates: init-ui without --force writes what is missing and nothing else."""
    root = tmp_path / "suite"
    init_skeleton(root, name="shop", with_ui=True, force=True)
    conftest = root / "src/ui/conftest.py"
    old = conftest.read_text(encoding="utf-8").replace(
        '"ignore_https_errors": ignore_https_errors(),', '"ignore_https_errors": True,'
    )
    conftest.write_text(old, encoding="utf-8")
    edited = root / "src/ui/pages/login_page.py"
    edited.write_text("# mine\n", encoding="utf-8")
    snapshot = {
        p: p.read_bytes() for p in root.rglob("*") if p.is_file() and p != conftest
    }

    conftest.unlink()
    result = apply_ui_layout(root, name="shop", force=False)

    assert result.created == ["src/ui/conftest.py"]
    assert '"ignore_https_errors": ignore_https_errors()' in conftest.read_text(encoding="utf-8")
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and p != conftest}
    assert after == snapshot
