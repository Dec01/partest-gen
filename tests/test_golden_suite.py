"""Golden e2e: OpenAPI fixture → full generate → import + collect-only smoke.

CI-friendly: no live stand, no browser. Ensures G1–G5 output stays importable.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from partest_gen.cli import main as cli_main

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"
LIB_ROOT = Path(__file__).resolve().parents[1]


def _pythonpath(extra: Path | None = None) -> str:
    parts = [str(LIB_ROOT)]
    if extra is not None:
        parts.insert(0, str(extra))
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def _env_for_suite(suite_root: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath(suite_root)
    # avoid picking up host confpartest / plugins noise
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return env


@pytest.fixture
def golden_suite(tmp_path: Path) -> Path:
    dest = tmp_path / "golden_suite"
    rc = cli_main(
        [
            "from-openapi",
            str(dest),
            "--file",
            str(FIXTURE),
            "--depth",
            "p1",
            "--force",
            "--with-ui",
            "--name",
            "golden",
        ]
    )
    assert rc == 0, "from-openapi --depth p1 --with-ui failed"
    return dest


def test_golden_tree_shape(golden_suite: Path):
    root = golden_suite
    must = [
        "confpartest.py",
        "conftest.py",
        "docs/openapi.yaml",
        ".partest/suite_ir.json",
        ".partest/openapi_summary.md",
        "src/api/resources/endpoints/paths.py",
        "src/api/resources/collections/factory.py",
        "src/api/tests/items/test_items_default.py",
        "src/api/tests/items/test_items_new_object.py",
        "src/api/tests/items/test_items_incorrect_body.py",
        "src/api/tests/items/P1_CHECKLIST.md",
        "src/api/tests/test_zorro.py",
        "src/ui/conftest.py",
        "src/ui/pages/base_page.py",
        "src/ui/tools/capture_baselines.py",
        "src/ui/baselines/reference/.gitkeep",
        "docs/UI_GUIDE.md",
        "scripts/run_ui.ps1",
    ]
    missing = [p for p in must if not (root / p).is_file()]
    assert not missing, f"missing golden artifacts: {missing}"

    # Nothing in a full generated suite may switch certificate verification off, and the
    # project-local config is where the switch is documented instead.
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if re.search(r"verify=False|[\"']?ignore_https_errors[\"']?\s*[:=]\s*True",
                     p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"generated code disables TLS verification: {offenders}"
    ui_conftest = (root / "src/ui/conftest.py").read_text(encoding="utf-8")
    assert '"ignore_https_errors": ignore_https_errors()' in ui_conftest
    conf = (root / "confpartest.py").read_text(encoding="utf-8")
    assert "tls_verify" in conf
    # partest reads the specification on first use, not while the suite is collected
    assert "while the suite is assembled" not in conf
    assert "TLS certificate verification failed" in conf

    summary = (root / ".partest/openapi_summary.md").read_text(encoding="utf-8")
    assert "items" in summary.lower()
    paths = (root / "src/api/resources/endpoints/paths.py").read_text(encoding="utf-8")
    assert "/items" in paths or "items" in paths


def test_golden_import_smoke(golden_suite: Path):
    """Import generated packages with suite root on PYTHONPATH."""
    code = """
import importlib
mods = [
    "src.api.resources.endpoints.paths",
    "src.api.resources.collections.factory",
    "src.api.tests.conftest",
    "src.ui.pages.base_page",
    "src.ui.utils.page_monitor",
]
for m in mods:
    importlib.import_module(m)
print("ok", len(mods))
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=golden_suite,
        env=_env_for_suite(golden_suite),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, f"import smoke failed:\n{r.stdout}\n{r.stderr}"
    assert "ok" in r.stdout


def test_golden_api_collect_only(golden_suite: Path):
    """pytest --collect-only on generated API tests (no network)."""
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "src/api/tests",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=golden_suite,
        env=_env_for_suite(golden_suite),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, f"collect-only failed:\n{r.stdout}\n{r.stderr}"
    out = r.stdout + r.stderr
    assert "test_items_default" in out or "TestItemsDefault" in out
    # expect a reasonable suite size from sample OpenAPI
    assert "collected" in out.lower() or "test session" in out.lower() or "tests" in out.lower()


@pytest.fixture
def stub_api():
    """Any request answers 200 with ``{}``: the run only has to reach the counters."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _answer(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _answer

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("mode", ["serial", "xdist"])
def test_the_report_written_at_session_end_counts_the_calls(mode, golden_suite: Path, stub_api):
    """``PARTEST_COVERAGE_JSON`` is written when the session ends, after the session fixtures
    are torn down. A conftest that reset the counters in its teardown left that report with
    zero calls on every endpoint — serially and under xdist alike."""
    args = [sys.executable, "-m", "pytest", "src/api/tests", "-q", "-p", "no:cacheprovider",
            "--domain", stub_api]
    if mode == "xdist":
        try:
            import xdist  # noqa: F401
        except ImportError:
            pytest.skip("pytest-xdist is not installed in this environment")
        args += ["-n", "2"]
    report = golden_suite / "coverage.json"
    env = _env_for_suite(golden_suite)
    env["PARTEST_COVERAGE_JSON"] = str(report)
    env["PARTEST_COVERAGE_HTML"] = str(golden_suite / "coverage_report.html")
    r = subprocess.run(args, cwd=golden_suite, env=env, capture_output=True, text=True,
                       timeout=300)
    assert report.is_file(), f"no coverage.json — is the partest plugin loaded?\n{r.stdout[-2000:]}"
    import json

    rows = json.loads(report.read_text(encoding="utf-8"))["endpoints"]
    calls = {(row["method"], row["path"]): row["calls"] for row in rows}
    assert calls.get(("GET", "/items"), 0) > 0, f"no calls counted: {calls}\n{r.stdout[-2000:]}"


def test_golden_ui_collect_only(golden_suite: Path):
    """Collect UI smoke tests if playwright is available; else skip soft."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright not installed — UI collect optional")

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "src/ui/tests",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=golden_suite,
        env=_env_for_suite(golden_suite),
        capture_output=True,
        text=True,
        timeout=120,
    )
    # UI may need pytest-playwright plugin; accept 0 or document skip
    if r.returncode != 0:
        # still assert tree is present; collection plugins may be missing in lib CI
        assert (golden_suite / "src/ui/tests/smoke/test_ui_smoke.py").is_file()
        pytest.skip(f"UI collect needs suite plugins: {r.stderr[:400]}")
    assert "test_" in r.stdout


def test_sync_openapi_idempotent_banner(golden_suite: Path, capsys):
    """Second sync-openapi should not explode; summary stays; the unchanged spec leaves
    nothing behind as an orphan and nothing generated as skipped."""
    capsys.readouterr()
    rc = cli_main(
        [
            "sync-openapi",
            str(golden_suite),
            "--file",
            str(FIXTURE),
            "--depth",
            "p1",
        ]
    )
    assert rc == 0
    assert (golden_suite / ".partest/suite_ir.json").is_file()
    out = capsys.readouterr().out
    assert "Orphaned" not in out
    assert "Skipped: 0" in out
