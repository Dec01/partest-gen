<!-- Part of the partest-gen package: generated documentation, not hand-written.
     Read it with `python -m partest_gen.docs`. Local edits are lost on upgrade. -->

# The generated UI layer

`--with-ui` at generation time, or `init-ui` on an existing project, adds `src/ui`. It is a
second suite that happens to live in the same repository — not an extension of the API one.

```bash
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --with-ui
partest-gen init-ui ./my-suite          # add it later
pip install 'partest[ui]'               # Playwright and Pillow
playwright install chromium
```

## What is emitted

| Path | What it is |
|---|---|
| `src/ui/conftest.py` | browser and page fixtures, frontend URL resolution, certificate checking |
| `src/ui/pages/` | `BasePage` subclass plus a login page stub |
| `src/ui/components/` | shared page fragments (app shell, navigation) |
| `src/ui/fixtures/` | auth fixture and an API seeding fixture |
| `src/ui/utils/` | thin re-exports of `partest.ui`: page monitor, health, visual compare, storage |
| `src/ui/resources/ui_rbac_matrix.py` | an empty role → screen matrix for you to fill |
| `src/ui/tools/` | baseline capture wrapper and a scenes example |
| `src/ui/baselines/{reference,actual,diff}` | reference images are committed; the other two are not |
| `src/ui/tests/{smoke,auth,rbac,visual}` | one runnable example per category |
| `scripts/run_ui.{sh,ps1}` | run the UI suite with the right markers and environment |

The utils modules are re-exports on purpose: the behaviour lives in `partest.ui`, so a fix in
the harness reaches every generated project through an upgrade rather than a regeneration.

## The isolation rule

`src/ui/conftest.py` must never import `confpartest`, load the OpenAPI document, or start the
API coverage session.

This is not a style preference. A UI job that pulls in the API session becomes slow, requires
network access to fetch a specification it never uses, and fails for reasons that have nothing
to do with the browser. The generator emits the two trees already separated; keeping them
separated is yours.

What the generated conftest cannot hold on its own: the `partest` pytest plugin runs before
any conftest, and with the project root on `sys.path` (`pythonpath = .` in the generated
`pytest.ini`, or `python -m pytest`) it imports `confpartest` to read its own switches — in a
UI-only run too. Older `partest` releases also loaded the specification it names at that
moment; current ones read it only on first use, the first tracked API call or a coverage
report, and a UI run makes neither. The cause is on the `partest` side; the generated UI tree
itself imports neither.

Seeding data for a UI test is the one place the temptation appears. Do it through
`fixtures/api_seed.py`, which talks to the API with a plain client — no coverage session, no
specification load.

Its one concession to the harness is TLS: the seed client asks
`partest.tls.resolve_verify(None, env_only=True)` what `verify=` should be, because hardcoding
`verify=False` in a generated file is how a project ends up unverified without ever deciding to
be. `env_only` keeps the isolation rule: `PARTEST_TLS_VERIFY` is read, `confpartest` is not, so
`tls_verify = False` in the project file deliberately does **not** reach a UI job.

The browser follows the same switch. `browser_context_args` in `src/ui/conftest.py` sets
`ignore_https_errors` from `partest.ui.ignore_https_errors()`, which reads the environment
only:

| `PARTEST_TLS_VERIFY` | Browser |
|---|---|
| unset, `1`, `true` | checks certificates — the default |
| `0`, `false` | accepts any certificate; partest warns once (`TLSVerificationDisabled`) |
| a CA bundle path | still checks, against the browser's own trust store; partest says the bundle was not applied |

The message for a CA bundle is a plain `UserWarning`, not `TLSVerificationDisabled`, and it is
worded for baseline capture: it suggests passing `ignore_https_errors=True`. For the generated
conftest that is not the fix — it is the switched-off check this page is about. A Playwright
context has no CA bundle option, only on/off, so a private CA has to go where the browser
looks: the OS trust store for Chromium on Windows and macOS, the NSS database
(`~/.pki/nssdb`, `certutil`) for Chromium on Linux. Firefox and WebKit do not read
`~/.pki/nssdb`; each trusts a store of its own.

Projects generated before this rule set `"ignore_https_errors": True` in that file. It carries
no banner, so nothing rewrites it on its own: either change the line by hand — `CHANGELOG.md`
has the exact replacement — or delete `src/ui/conftest.py` and run `init-ui` without
`--force`, which writes only the files that are missing.

## What stays a stub forever

These are emitted once, with a `TODO`, and are never overwritten by a re-sync, because their
content is your product:

- login page selectors and the application shell
- the role → screen matrix
- the visual scene list
- reference baseline images

`data-testid` selectors survive redesigns; CSS paths do not. Capture reference baselines only
once the selectors have stopped moving, otherwise you are committing screenshots of a moving
target.

## Baselines

```bash
python -m partest.ui.capture_baselines \
  --out src/ui/baselines/reference \
  --scenes src/ui/tools/scenes.json \
  --dry-run
```

Drop `--dry-run` when the list of scenes looks right. Commit `baselines/reference/`; keep
`actual/` and `diff/` out of version control — the generated `.gitignore` already does this.
