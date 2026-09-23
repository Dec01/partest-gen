"""The file the audit reads must describe what actually gets installed.

`requirements.txt` exists here for `pip-audit`: dependencies declared imperatively in
`setup.py` are invisible to it statically, and it answers "not audited" — which reads
exactly like "no vulnerabilities" to anyone skimming the output.

Since the file exists for the audit, it has to state the same thing `setup.py` states. A
list that drifted is worse than no list at all: the gate reports a green pip-audit having
checked the wrong set. It can drift in two ways, both silent:

* **names** — a package was added to ``install_requires`` and not here; it is never audited;
* **bounds** — a floor was raised in ``setup.py`` after a finding and left alone here, so
  the audit keeps checking a version the consumer is no longer allowed to install.

So both the names and the full specifiers are compared.

Parsed with ``ast``: ``setup.py`` is not imported (importing would call ``setup()``), and
not cut up with a regular expression either — the tree knows where a list ends.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _setup_call() -> ast.Call:
    tree = ast.parse((REPO_ROOT / "setup.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setup":
            return node
    raise AssertionError("setup.py has no setup() call")


def _keyword(name: str):
    for keyword in _setup_call().keywords:
        if keyword.arg == name:
            return ast.literal_eval(keyword.value)
    raise AssertionError(f"setup.py has no {name} argument")


def _split(requirement: str) -> tuple:
    """``requests>=2.33.0`` -> ``("requests", ">=2.33.0")``, name normalised per PEP 503."""
    head = requirement.split(";")[0].strip()
    name = re.split(r"[<>=!~\[]", head, maxsplit=1)[0].strip()
    return re.sub(r"[-_.]+", "-", name).lower(), head[len(name):].replace(" ", "")


@pytest.fixture()
def declared() -> dict:
    """What a consumer installs. The `dev` extra is deliberately out: it never travels to
    them, and the audit is about what does."""
    return dict(_split(item) for item in _keyword("install_requires"))


@pytest.fixture()
def audited() -> dict:
    lines = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return dict(
        _split(line)
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_the_audited_file_lists_the_same_packages(declared, audited):
    assert declared.keys() == audited.keys(), (
        "requirements.txt drifted from setup.py — the audit checks something else.\n"
        f"  declared, never audited: {sorted(declared.keys() - audited.keys())}\n"
        f"  audited, never declared: {sorted(audited.keys() - declared.keys())}"
    )


def test_the_audited_file_carries_the_same_bounds(declared, audited):
    """Matching names are not enough: an audit is per version, not per package.

    A floor raised in `setup.py` and not here leaves the check sitting on the vulnerable
    version and still reports green, because `pip-audit` on `>=` resolves to the newest.
    """
    differing = {
        name: (spec, audited[name])
        for name, spec in declared.items()
        if name in audited and spec != audited[name]
    }

    assert not differing, (
        "requirements.txt drifted from setup.py on bounds — the wrong version is audited:\n"
        + "\n".join(
            f"  {name}: setup.py {mine!r}, requirements.txt {theirs!r}"
            for name, (mine, theirs) in sorted(differing.items())
        )
    )


def test_the_audited_file_states_a_floor_for_everything(audited):
    """A line without a lower bound is audited as "anything" — there is nothing to check."""
    floorless = sorted(
        name for name, spec in audited.items() if ">=" not in spec and "==" not in spec
    )

    assert not floorless, f"requirements.txt states no floor for: {floorless}"
