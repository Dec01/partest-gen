"""Root files of the legacy flat scaffold (``RootFilesContainer``).

This container predates the G1 skeleton and is still reachable through
``partest.project_gen.root_files``, so what it writes is held to the same rules: it must not
teach a default the harness abandoned, and it must not hand every new project a dependency
set that an audit rejected.
"""

from __future__ import annotations

from partest_gen.root_files import RootFilesContainer


def _content(name: str) -> str:
    found = RootFilesContainer().get_file_by_name(name)
    assert found is not None, f"{name} is no longer emitted"
    return found.content


def test_conftest_does_not_disable_certificate_verification():
    conftest = _content("conftest.py")
    assert "verify=False" not in conftest
    assert "ApiClient(domain=domain)" in conftest
    # a project that inherits the new default needs to be told where the switch lives
    assert "PARTEST_TLS_VERIFY" in conftest


def test_requirements_drop_swagger_parser():
    """Unresolvable, imported by nobody, removed from partest — so not seeded either."""
    requirements = _content("requirements.txt")
    assert "swagger-parser" not in requirements


def test_requirements_carry_the_audited_floors():
    requirements = _content("requirements.txt")
    for pin in ("urllib3==2.7.0", "requests==2.33.0", "idna==3.15", "pytest==9.0.3"):
        assert pin in requirements, f"missing audited pin {pin}"
    assert "partest>=2.0.0" in requirements
