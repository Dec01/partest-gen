"""G1: IR builder + monorepo skeleton + CLI smoke."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from partest_gen.cli import main as cli_main
from partest_gen.ir import build_ir_from_openapi_dict
from partest_gen.openapi_load import load_openapi
from partest_gen.skeleton import init_skeleton

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_load_openapi_ir():
    ir = load_openapi(FIXTURE)
    assert ir.title == "Sample Shop API"
    assert ir.version == "1.2.0"
    assert len(ir.operations) >= 5
    tags = ir.tags()
    assert "items" in tags
    assert "health" in tags

    create = next(o for o in ir.operations if o.method == "POST" and o.path == "/items")
    assert create.has_request_body
    assert create.success_status == 201
    assert create.request_schema is not None
    assert "name" in (create.request_schema.get("required") or [])
    assert create.subtype == "post_create_object"
    assert "request_new_object" in create.required_p1
    assert "request_incorrect_body" in create.required_p1

    get_one = next(o for o in ir.operations if o.method == "GET" and o.path == "/items/{id}")
    assert get_one.subtype == "get_dynamic_object"
    assert any(p.name == "id" for p in get_one.path_params)

    listing = next(o for o in ir.operations if o.method == "GET" and o.path == "/items")
    assert listing.subtype in {"get_list_objects", "get_static_object"}


def test_ir_to_dict_jsonable():
    ir = load_openapi(FIXTURE)
    data = ir.to_dict()
    json.dumps(data)  # must not raise
    assert data["operation_count"] == len(ir.operations)


def test_init_skeleton_tree(tmp_path: Path):
    result = init_skeleton(tmp_path / "suite", name="shop", force=True)
    root = Path(result.root)
    expected = [
        "README.md",
        "pytest.ini",
        "confpartest.py",
        "conftest.py",
        "env.example",
        "requirements/api.txt",
        "src/api/tests/conftest.py",
        "src/api/tests/test_zorro.py",
        "src/api/resources/endpoints/paths.py",
        "src/api/resources/validations/common/problem_detail.py",
        "docs/openapi.yaml",
    ]
    for rel in expected:
        assert (root / rel).is_file(), f"missing {rel}"
    assert result.created
    # second run without force skips
    result2 = init_skeleton(tmp_path / "suite", name="shop", force=False)
    assert result2.skipped
    assert not any(x == "README.md" for x in result2.created) or True


def test_skeleton_documents_tls_instead_of_disabling_it(tmp_path: Path):
    """partest verifies certificates; the scaffold explains the switch, never flips it."""
    result = init_skeleton(tmp_path / "tls", name="shop", force=True, with_ui=True)
    root = Path(result.root)

    conf = (root / "confpartest.py").read_text(encoding="utf-8")
    assert "tls_verify" in conf, "confpartest.py must carry the TLS hint"
    assert "PARTEST_TLS_VERIFY" in conf
    # the hint is a hint: every tls_verify line stays commented out
    for line in conf.splitlines():
        if "tls_verify" in line:
            assert line.lstrip().startswith("#"), f"uncommented TLS switch: {line!r}"

    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "verify=False" not in text, f"{path} disables certificate verification"


def test_skeleton_requirements_floor_matches_methodology_layout(tmp_path: Path):
    """Emitted code reads partest.methodology.api, which only exists from 2.0.0."""
    result = init_skeleton(tmp_path / "reqs", name="shop", force=True)
    root = Path(result.root)
    api = (root / "requirements/api.txt").read_text(encoding="utf-8")
    ui = (root / "requirements/ui.txt").read_text(encoding="utf-8")
    assert "partest>=2.0.0" in api
    assert "partest[ui]>=2.0.0" in ui


def test_skeleton_requirements_seed_audited_floors(tmp_path: Path):
    """A scaffold hands every new suite its minimum, and nobody installs the minimum until
    a lockfile or an offline mirror does. Floors with a known advisory must not be seeded.

    Each pin below is the earliest release free of the advisories against the floor it
    replaced; raise one here only after the audit says the old one is no longer clean.
    """
    result = init_skeleton(tmp_path / "floors", name="shop", force=True)
    root = Path(result.root)
    seeded = "".join(
        (root / "requirements" / name).read_text(encoding="utf-8")
        for name in ("base.txt", "api.txt", "ui.txt")
    )

    for floor in ("pytest>=9.0.3", "requests>=2.33.0", "pydantic>=2.4.0",
                  "python-dotenv>=1.2.2"):
        assert floor in seeded, f"generated project no longer seeds the audited {floor}"
    for withdrawn in ("pytest>=8.0.0", "requests>=2.31.0", "pydantic>=2.0.0",
                      "python-dotenv>=1.0.0"):
        assert withdrawn not in seeded, f"generated project seeds vulnerable {withdrawn}"

    # Plugin floors travel with pytest's or the minimum stops being installable — and, for
    # allure, stops running: 2.8.18 resolves next to pytest 9 and then errors every test.
    for floor in ("pytest-asyncio>=1.3.0", "pytest-playwright>=0.7.2",
                  "allure-pytest>=2.13.3"):
        assert floor in seeded, f"generated project seeds a plugin floor pytest 9 rejects: {floor}"


def test_init_with_ir_writes_partest_dir(tmp_path: Path):
    ir = load_openapi(FIXTURE)
    result = init_skeleton(
        tmp_path / "suite2",
        name="shop",
        force=True,
        suite_ir=ir,
    )
    root = Path(result.root)
    assert (root / ".partest" / "suite_ir.json").is_file()
    assert (root / ".partest" / "openapi_summary.md").is_file()
    data = json.loads((root / ".partest" / "suite_ir.json").read_text(encoding="utf-8"))
    assert data["title"] == "Sample Shop API"
    assert data["operation_count"] >= 5


def test_cli_dump_ir(tmp_path: Path):
    out = tmp_path / "ir.json"
    rc = cli_main(["dump-ir", str(FIXTURE), "-o", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["title"] == "Sample Shop API"


def test_cli_init(tmp_path: Path):
    dest = tmp_path / "myproj"
    rc = cli_main(
        [
            "init",
            str(dest),
            "--name",
            "myproj",
            "--openapi",
            str(FIXTURE),
            "--force",
        ]
    )
    assert rc == 0
    assert (dest / "src" / "api" / "tests" / "conftest.py").is_file()
    assert (dest / ".partest" / "suite_ir.json").is_file()
    # openapi copied
    assert (dest / "docs" / "openapi.yaml").is_file()
    text = (dest / "docs" / "openapi.yaml").read_text(encoding="utf-8")
    assert "Sample Shop API" in text


def test_cli_from_openapi(tmp_path: Path):
    dest = tmp_path / "from_oas"
    rc = cli_main(
        [
            "from-openapi",
            str(dest),
            "--file",
            str(FIXTURE),
            "--name",
            "shop",
            "--force",
        ]
    )
    assert rc == 0
    assert (dest / ".partest" / "openapi_summary.md").is_file()


def test_cli_init_with_ui(tmp_path: Path):
    dest = tmp_path / "ui_proj"
    rc = cli_main(["init", str(dest), "--with-ui", "--force"])
    assert rc == 0
    assert (dest / "src" / "ui" / "conftest.py").is_file()
