# Changelog

All notable changes to `partest-gen`. Format follows [Keep a Changelog](https://keepachangelog.com/),
versioning follows [Semantic Versioning](https://semver.org/) — with one addition specific to a
code generator: the **names and locations of the files it writes** are part of the public API.
Renaming a generated module breaks hand-written imports in every project that ran the previous
version, so it is a major change even though no exported name moved.

## 1.0.1 — 2026-09-23

### Fixed

- **The source distribution could not be built.** `MANIFEST.in` pruned `docs/`, and
  `setup.py` reads `docs/PYPI.md` unconditionally for its long description, so the file
  the build needs was the one the manifest removed. Installing from source —
  `pip install --no-binary :all:`, a mirror that carries no wheels, a closed network that
  builds everything itself — failed on the first line of the build:

  ```
  FileNotFoundError: [Errno 2] No such file or directory: '.../docs/PYPI.md'
  ```

  The wheel was fine, which is why ordinary installation never noticed and why the defect
  shipped. Nothing else changed in this release.

## [1.0.0] — unreleased

First release as a standalone distribution. The generator itself is not new: it shipped inside
`partest` as `partest.project_gen` through waves G0–G6 and arrives here unchanged.

### Extracted from partest

- `partest.project_gen.**` → `partest_gen.**`. Moved with `git subtree split`, so the history
  of the directory came along instead of collapsing into one initial commit.
- The `partest-gen` console script is now declared by this distribution, the one that
  implements it. `pip install partest` alone no longer provides the command.
- `partest` keeps `partest.project_gen` as a deprecated bridge that re-exports from here, and
  a `partest[gen]` extra that installs both. The bridge is removed in a major `partest`
  release, not before.

Rationale and the alternatives that were rejected:
`docs/wiki/decisions/separate-package.md`.

### Added

- `partest-gen --version`. Generated trees look alike; the version that produced one is the
  first thing a bug report needs.
- `python -m partest_gen.docs list | show <page> | path` — the user-facing pages ship inside
  the wheel, generated from the wiki by `tools/docs_build_wheel.py`.
- `py.typed`: the package ships its annotations (PEP 561).
- Documentation wiki, linter and CI carried over from `partest`: frontmatter with `sources:`
  and `verified:`, staleness detection against git history, wheel-drift checks, and
  `tools/check_all.py` as the single command CI and a laptop both run.

### Changed

- Requires `partest>=2.0.0`. The generator reads the methodology to decide which cases each
  operation needs, and `partest` 2.0.0 split it into two areas: the modules this package
  imports now live under `partest.methodology.api.*`. Nothing inside them was renamed — only
  the import path — but the new paths do not exist in 1.x at all, so an older harness fails
  as an `ImportError` while the suite is being collected. A suite generated here must also be
  countable by that harness.

  **Publication order:** this release cannot be uploaded before `partest` 2.0.0 is on PyPI.
  Until then the floor names a version `pip` cannot resolve.

- Generated projects no longer turn certificate verification off. `partest` 2.0.0 verifies TLS
  by default; a generator that keeps writing the old default teaches it, and the warning about
  an unverified run then points at a line nobody wrote by hand.

  - The root `conftest.py` of the flat scaffold (`RootFilesContainer`) creates
    `ApiClient(domain=domain)` and names `PARTEST_TLS_VERIFY` in a comment.
  - The generated `confpartest.py` carries a commented `tls_verify` hint — the CA-bundle form
    first, because it keeps the check — so the first run against a self-signed stand has its
    answer in the project, not only in the library's migration guide.
  - The UI seed client (`src/ui/fixtures/api_seed.py`) resolves `verify=` through
    `partest.tls.resolve_verify(None, env_only=True)`. `env_only` is the UI road: the
    environment is read, `confpartest` is not, so the isolation of the UI layer holds.

- Generated dependency floors follow the same release: `requirements/api.txt` asks for
  `partest>=2.0.0` and `requirements/ui.txt` for `partest[ui]>=2.0.0`.

- The `requirements.txt` of the flat scaffold matches what `partest` declares today: no
  `swagger-parser` (dropped there as unresolvable and imported by nobody), and the audited
  floors for `urllib3`, `requests`, `idna` and `pytest`. A new project used to start with the
  dependency set an audit had already rejected.
- `python_requires=">=3.10"`. The emitters write files with `Path.write_text(newline=...)`,
  which does not exist earlier. Unchanged from the last `partest` release.

### Unchanged, deliberately

- The shape of what is emitted: the same files in the same places, with the same names. The
  extraction itself was a packaging change, not a rewrite; the only content that moved since
  is listed under `Changed`, and all of it follows `partest` 2.0.0 rather than introducing
  anything of its own.
- The overwrite policy: only files carrying `AUTO-GENERATED by partest-gen` are rewritten by
  `sync-openapi`. See `docs/wiki/decisions/banner-overwrite.md`.

### Migration

```bash
pip install partest-gen
```

Then, in code that imported the old path:

```python
from partest.project_gen.cli import main   # deprecated, still works with partest-gen installed
from partest_gen.cli import main           # supported
```

Nothing changes for projects that only use the CLI, and nothing changes in an already
generated tree — no regeneration is needed.
