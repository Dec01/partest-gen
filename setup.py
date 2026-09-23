import pathlib
import re

from setuptools import find_packages, setup

HERE = pathlib.Path(__file__).parent


def version():
    """Single source of truth: partest_gen/__init__.py. Never duplicate the number here."""
    text = (HERE / "partest_gen" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise RuntimeError("cannot find __version__ in partest_gen/__init__.py")
    return match.group(1)


def readme():
    """PyPI long_description. Kept short on purpose — the repository holds the detail."""
    return (HERE / "docs" / "PYPI.md").read_text(encoding="utf-8")


setup(
    name="partest-gen",
    version=version(),
    author="dec01",
    author_email="parshin.ewgeniy@yandex.ru",
    license="MIT",
    description=(
        "Scaffold a runnable pytest suite from OpenAPI: endpoints, payloads, validations "
        "and the priority-one test matrix partest's methodology asks for."
    ),
    long_description=readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/Dec01/partest-gen",
    packages=find_packages(exclude=["tests", "build", "dist"]),
    include_package_data=True,
    package_data={
        # py.typed: the package ships its annotations (PEP 561).
        "partest_gen": ["py.typed", "docs/*.md"],
        "partest_gen.docs": ["*.md"],
    },
    install_requires=[
        # The generator emits code against this harness and reads its methodology to decide
        # which test cases each operation needs, so the two move together. 2.0.0 is the
        # release that split the methodology into `partest.methodology.api` and `.ui`; the
        # deep paths this package imports do not exist at all before it, and an older
        # install fails as an ImportError while the suite is being collected.
        # Не «код требует нового», а защита потребителя: партии 2.0.x объявляют
        # уязвимые полы requests и python-dotenv, и на минимальном разрешении они
        # приезжают сюда транзитивно. 2.1.0 — первая, где они подняты.
        "partest>=2.1.0",
        "pyyaml>=6.0.2",
        # Imported lazily, only for `--url`. Declared anyway: relying on it arriving through
        # partest's own dependencies would make a URL fetch break on an unrelated change.
        # The floor is where the advisories against 2.31.0 end, not the newest release:
        # PYSEC-2026-1873 is fixed in 2.32.0, PYSEC-2026-1872 in 2.32.4, PYSEC-2026-2275
        # in 2.33.0 — so 2.33.0 is the earliest version free of all three.
        "requests>=2.33.0",
    ],
    extras_require={
        "dev": [
            # PYSEC-2026-1845 has no fix inside the 8.x line, so the floor crosses a major:
            # 9.0.3 is the first release that carries it. No ceiling on purpose — this
            # package registers no pytest plugin (`entry_points` declares a console script
            # only) and imports pytest nowhere, so a new pytest major can break this
            # repository's own test run, never a consumer's collection.
            "pytest>=9.0.3",
        ],
    },
    entry_points={
        "console_scripts": [
            "partest-gen=partest_gen.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Pytest",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development :: Code Generators",
    ],
    keywords="autotest api openapi scaffold generator partest pytest codegen",
    project_urls={
        "Source": "https://github.com/Dec01/partest-gen",
        "Issues": "https://github.com/Dec01/partest-gen/issues",
        "Changelog": "https://github.com/Dec01/partest-gen/blob/master/CHANGELOG.md",
        "Documentation": "https://github.com/Dec01/partest-gen/blob/master/docs/wiki/index.md",
        "PyPI": "https://pypi.org/project/partest-gen/",
        "partest": "https://github.com/Dec01/partest",
    },
    # The emitters write files with `Path.write_text(newline=...)`, which needs 3.10.
    # Same floor as partest, so a suite never has to split its interpreter requirement.
    python_requires=">=3.10",
)
