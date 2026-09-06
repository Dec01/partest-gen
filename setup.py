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
        # which test cases each operation needs, so the two move together. 1.8.0 is the
        # first release whose classifier and subtype overrides match what is emitted here.
        "partest>=1.8.0",
        "pyyaml>=6.0.2",
        # Imported lazily, only for `--url`. Declared anyway: relying on it arriving through
        # partest's own dependencies would make a URL fetch break on an unrelated change.
        "requests>=2.31.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
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
