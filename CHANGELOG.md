# Changelog

All notable changes to `partest-gen`. Format follows [Keep a Changelog](https://keepachangelog.com/),
versioning follows [Semantic Versioning](https://semver.org/) — with one addition specific to a
code generator: the **names and locations of the files it writes** are part of the public API.
Renaming a generated module breaks hand-written imports in every project that ran the previous
version, so it is a major change even though no exported name moved.

## 1.2.2 — 2026-10-25

### Fixed

- **The coverage report written at the end of the session counted no calls.** The generated
  `src/api/tests/conftest.py` reset the counters in its session fixture twice — at the start
  and again in its teardown. `partest` writes the report named by `PARTEST_COVERAGE_JSON` (and
  `PARTEST_COVERAGE_HTML`) when the session ends, after that teardown, so every endpoint showed
  `calls: 0` and the run read as nothing covered — serially and under `pytest -n` alike. This
  is the report a parallel run needs: the one `test_zorro.py` writes inside a test sees only
  its own worker. The fixture now resets once, at the start. `test_zorro.py` was not affected:
  it runs before the teardown.

  **Existing projects.** None of the three files carries the banner, so `sync-openapi`
  rewrites none of them. Three steps by hand:

  1. `src/api/tests/conftest.py` — delete the second `reset_storage()`, the one after `yield`
     (the `yield` can go too):

     ```python
     @pytest.fixture(scope="session", autouse=True)
     def _clear_coverage():
         reset_storage()
         yield
         reset_storage()      # remove this line
     ```

  2. `.gitignore` — add `coverage.json`. The report lists every endpoint of the stand, and
     with TLS checking off it records the stand's host names.
  3. `README.md` — in `## Run`, replace the two commands with
     `PARTEST_COVERAGE_JSON=coverage.json pytest src/api/tests -q`.

- **A specification downloaded with `--url` left the coverage report on the placeholder, and
  nothing said so.** The download is not saved in the project, so `docs/openapi.yaml` stays
  the skeleton's `/health` placeholder. `confpartest.py` points the coverage report at that
  file, and `sync-openapi` without `--file` or `--url` reads it. `init --openapi <URL>`,
  `from-openapi --url` and `sync-openapi --url` now print a line starting with `Not saved:`
  while `docs/openapi.yaml` is still the placeholder, with what to do: save the specification
  as `docs/openapi.yaml` before the first run. Saving the download is not done here: it is a
  new write into existing projects (see `docs/wiki/proposals.md`, (9)).
- **`dump-ir -o` to a path it cannot write ended in a traceback with exit code 1.** A
  directory, a path under a file, or a write the system refuses now prints one line to
  stderr — `error: cannot write IR to <path>: <reason>` — and exits with code 2, as an
  unreadable specification does since 1.2.1. The IR is written to a temporary file beside
  the target and moved over it, so a failed or interrupted write leaves the previous file
  whole and no temporary file behind (a read-only target included). A specification that
  holds a lone surrogate (an escape such as `"\ud800"`) is refused with one line before
  anything is written, with `-o` or without, as by the other commands since 1.2.0. An IR
  printed to a stdout whose encoding cannot hold one of its characters gives one line with
  advice to use `-o`. Both used to end in a `UnicodeEncodeError` traceback with exit code 1.
- **A date that does not exist in the specification was a traceback or the wrong message.**
  YAML reads an unquoted `2023-02-29` (an `example`, a `default`) as a date, and the safe
  constructor let the `ValueError` of the impossible date out bare: a local file was
  reported as "not valid JSON", and a downloaded one ended in a traceback with exit code 1.
  Every command that reads a specification now says
  `is not valid YAML: cannot read the value '2023-02-29': day is out of range for month;
  quote it to keep it a string (line …, column …)` and exits with code 2. `load_openapi()`
  raises `yaml.constructor.ConstructorError` for it — a `yaml.YAMLError` at the value's
  position, the type the generator page documents for YAML it cannot read. For a downloaded
  body that is no longer a `ValueError`. A local file still raises `json.JSONDecodeError`,
  with the YAML error in its `__context__` chain. The same holds for a value its explicit tag
  cannot hold: `!!int abc` or `!!float abc` (a `ValueError`) and `!!timestamp abc` (an
  `AttributeError`). The message shows the value cut to 40 characters, and the error's reason
  only up to its first colon — `invalid literal for int() with base 10` — because the rest
  repeats the whole value.
- **`init_skeleton(openapi_source=<URL>)` recorded the URL as a `"local"` file** in the
  generated `confpartest.py`. `partest` opens a `"local"` entry as a path, so the coverage
  report found no specification. An `http://` or `https://` source (any case, surrounding
  whitespace dropped) is now recorded as `["url", "<URL>"]`, and the TLS comment under it
  says that this source is fetched with the same switch. A path stays `"local"`. The kind,
  the address and the project name are written as ASCII Python literals, with `\uXXXX` and
  `\UXXXXXXXX` escapes that read back as the same characters (also outside the BMP), so an
  invisible or look-alike character shows up in review. An ASCII name and address are
  written as before. The file is committed: pass an address without credentials and without
  tokens in its query. The `partest-gen` commands never pass a source to the skeleton, so
  trees they generate are unaffected; only Python code calling
  `partest_gen.skeleton.init_skeleton` with a URL is.
- **A `sync-openapi` without `--file` or `--url` against the placeholder said nothing.** When
  `docs/openapi.yaml` is still the skeleton's `/health` placeholder and the project has
  generated tags the placeholder does not declare, the sync now prints a `Warning:` line
  naming them before it rewrites `paths.py` and the facades: pass the real specification. It
  is a warning, not a refusal — the files it rewrites carry the banner.
- **The `confpartest.py` comment put `test_types_exception` under "used only when
  `zorro(use_matrix=False)`".** That holds for `test_types_coverage` only. The coverage report
  always reads `test_types_exception`: an endpoint called with one of those types is reported
  as `exception`, and from `partest` 2.7.0 on it is left out of every average. The list now
  has its own comment line. Existing projects own `confpartest.py`; the old comment is wrong,
  not harmful.

### Documentation

- The generated `README.md`, the after-generation guide and the `partest-scaffold` playbook
  told you to run `pytest src/api/tests/test_zorro.py` after the suite, as a separate process.
  The counters live in the test process, so that run starts from zero and reports nothing
  covered. All three now give one command,
  `PARTEST_COVERAGE_JSON=coverage.json pytest src/api/tests`, which writes `coverage.json`
  and `coverage_report.html` when the session ends. The generated `.gitignore` lists
  `coverage.json`. The README, the after-generation guide and the docstring of the generated
  `test_zorro.py` (which said "run last in CI after suite") now say what that test sees: only
  the calls made before it in its own process. Tags collected after it are missing — pytest
  collects files and directories together, alphabetically, so a tag directory named after
  `test_zorro.py` comes later — and so are the other workers under `pytest -n`. The guide,
  the playbook and the skill name the symptom of the old conftest: zero calls on every
  endpoint.
- The scaffold guide and the playbook say what `--url` leaves behind, and warn against a
  `sync-openapi --prune` without `--file`/`--url` while `docs/openapi.yaml` is the
  placeholder. The prune is refused only when no generated tag is left in the specification.
  If the real specification has a `health` tag, the prune goes ahead and deletes the
  generated files of every other tag. The resync guide says the specification is copied
  into `docs/openapi.yaml` only with `--file`.
- The generator page said `load_openapi()` raises `yaml.YAMLError` for YAML it cannot parse.
  For a local file it raises `json.JSONDecodeError`, a `ValueError`: the file is tried as YAML
  and then as JSON, and the JSON error is the one raised, with the `yaml.YAMLError` in its
  `__context__` chain. A `.json` file is read as JSON only. Only a downloaded body, tried as
  JSON and then as YAML, raises `yaml.YAMLError`. The page now says so, and a test checks
  each case. The code is unchanged: raising `yaml.YAMLError` for a local file would stop
  `except ValueError` from catching it.

### Compatibility

- Checked against `partest` 2.7.0 as published on PyPI, and 2.6.0, each in a clean
  environment with its pytest plugin loaded. The generated tree and the `dump-ir` output
  are byte-for-byte the same on both: the methodology tables this package reads did not
  change. The generated code does
  not call `attach_response`, the request logger or `Logger.warning`, and does not read
  `summary.avg`. The `test_zorro.py` stub checks `report.average_pct >= 0`, which still holds:
  the value is still a `float`, `0.0` when nothing is scored.
- Measured on a tree from this version against a stub API whose responses carry
  secrets. `PARTEST_COVERAGE_JSON` was set, and runs were serial and with `-n 2`.
  - 2.6.0 and 2.7.0 count the same calls (14) and the same average (52.38).
  - With 2.7.0, `coverage.json` carries `meta.avgRule: 2` and a `depth` per endpoint:
    11 cells, status asked in all 11, schema in 7. The stubs pass `expected_status_code`, and
    `validate_model` where the specification has a response schema.
  - The secrets appear nowhere in the terminal, `logs/pytest.log` or the Allure results.
    With 2.6.0 they appear in all three.
  - Without this version's conftest fix, `coverage.json` has zero calls on both.
  - Repeated with the published 2.7.0: the repository's tests, golden included, pass, and
    a generated project counts 14 calls in `coverage.json`, serially and with `-n 2`.
  - The `-n 2` case of the repository's own test of this report runs only where
    `pytest-xdist` is installed. It is not in the `dev` extra, so a plain
    `pip install -e ".[dev]"` and CI skip that case; the parallel run above was measured
    with `pytest-xdist` installed by hand.
- A failing stub fails the same way with 2.7.0, but reads differently. A status mismatch is
  raised as `partest.client.StatusMismatchError`, which subclasses `AssertionError`, and the
  terminal names that type instead of `AssertionError`. Bodies and secret headers in the
  message are masked, and a JSON body is re-serialised. The incorrect-body stubs expect a set
  of statuses, `(400, 415)`, but pass no `validate_model`, so 2.7.0's re-raised schema error
  under a set of statuses does not reach them. The generated clients set no `max_retries`,
  so the new rule that an expected status is never retried changes nothing either.
- The `partest>=2.1.0` floor stays: nothing generated needs 2.7.0.

## 1.2.1 — 2026-10-19

### Fixed

- **The generated UI tree switched certificate checking off in the browser.**
  `src/ui/conftest.py` set `"ignore_https_errors": True` in `browser_context_args`, so every
  page of a UI run accepted any certificate — the browser half of the default that 1.0.0
  removed from the HTTP clients, and nowhere documented. The browser now checks certificates by
  default. The switch is the one the UI seed client already uses, read from the environment
  only (the UI tree does not load `confpartest`): `PARTEST_TLS_VERIFY=0` turns the check off
  for the run and partest warns once per process (`TLSVerificationDisabled`, on the 2.1.0
  floor as well); `tls_verify` in
  `confpartest.py` does not reach the browser. The value comes from the public
  `partest.ui.ignore_https_errors()`, available from the `partest` floor this package already
  requires.

  A CA bundle path in `PARTEST_TLS_VERIFY` cannot be given to a browser — a Playwright
  context has only on/off — so the check stays on. partest then emits a plain `UserWarning`
  (not `TLSVerificationDisabled`, so a filter on that category does not catch it) worded for
  baseline capture; its advice to pass `ignore_https_errors=True` is not the fix for the
  generated conftest. Install the CA where the browser looks instead: the OS trust store for
  Chromium on Windows and macOS, the NSS database (`~/.pki/nssdb`) for Chromium on Linux. The
  generated comment, `src/ui/README.md`, `docs/UI_GUIDE.md` and a commented
  `# PARTEST_TLS_VERIFY=` line in `env.example` say so. The unused `import os` is gone from
  the generated conftest.

  **Existing projects keep the old line.** `src/ui/conftest.py` carries no banner, so neither
  `sync-openapi` nor `init-ui` rewrites it (`init-ui --force` would, together with every
  other UI file you edited). Either delete `src/ui/conftest.py` and run `init-ui` without
  `--force` — it writes only the files that are missing, so if you edited the conftest, carry
  your changes over — or change it by hand: add the import and replace the line:

  ```python
  from partest.ui import ignore_https_errors          # next to the other partest.ui import

          "ignore_https_errors": True,                # remove this line …
          "ignore_https_errors": ignore_https_errors(),  # … and write this one
  ```

  A UI run against a frontend with a self-signed certificate then fails until you install
  its CA in the browser's trust store or set `PARTEST_TLS_VERIFY=0` for that run.

- **A specification that could not be read ended in a traceback with exit code 1.**
  `from-openapi`, `sync-openapi`, `dump-ir` and `init --openapi` now print one line to
  stderr — which file, and what is wrong with it — and exit with code 2, before anything is
  written (`from-openapi` no longer announces itself before the specification is read): the
  file does not exist or is a directory; it cannot be read (permissions, not UTF-8 — a
  UTF-16 file is named, with "re-save it as UTF-8"; a downloaded body gets its own message,
  below); it is not valid YAML or JSON (with the line and
  column); its top level is not a mapping, or `info` or `paths` holds a value that is not a
  mapping (an empty one — `[]`, `""`, `0` — reads as absent, as before); or the URL cannot be
  used. For a URL the line gives the HTTP status with the advice to download the file and
  pass it as a file; names an HTML or XML page (a login or error page) served instead of a
  specification, and credentials in the URL that are not Latin-1 (requests cannot send them;
  its own error quoted the character); for a rejected certificate, gives OpenSSL's reason (self-signed, expired,
  hostname mismatch) and the ways out — `REQUESTS_CA_BUNDLE=/path/to/ca.pem`, or the file
  (`PARTEST_TLS_VERIFY` does not apply to the generator's download); and otherwise names the
  class of the failure and of its cause, from `requests` or `urllib3`
  (`ConnectionError (NameResolutionError)`, `LocationParseError`), never the text of the
  exception. An exception while building the model of a readable specification is still
  raised as it is: that is a generator bug. A document without an `openapi`/`swagger` field
  is read as before. For a shape it cannot build from, a body it cannot decode and
  credentials it cannot send, `load_openapi()` raises `SpecReadError` — a `ValueError`
  subclass, so `except ValueError` keeps catching it, as it caught the non-mapping case
  before; its `downloaded` attribute is true for a URL source, and `stage` says where it
  failed — `fetch` (credentials it cannot send), `read` (a body it cannot decode) or `shape`
  (not a specification). Other failures keep their own
  exception types, and the message of a missing file shows the source cleaned as below.

- **`HTTP://…` was looked for as a local file.** The scheme is recognised in any case and
  with whitespace around the source; such a source is now downloaded where it used to end in
  "not found". A source without `://` — a mistyped scheme such as `http:/host/x.yaml`
  included — is a path, and is printed as it is.

- **A downloaded specification was decoded as ISO-8859-1** when the server sent `text/*`
  without a charset: a BOM and every non-ASCII character in it were garbled. A `charset=` the
  `Content-Type` declares is now honoured, and a response without one is decoded as UTF-8
  (a BOM accepted). A body that cannot be decoded is one line with code 2 and the advice to
  download the file: UTF-16 the `Content-Type` does not announce ("does not say so", also
  under `charset=utf-8`), bytes outside the declared charset (named, with the offset), a
  charset Python does not know or cannot decode with (`undefined`, `idna`; the value is
  quoted, cut to 40 characters). An HTML or XML page is recognised by its body, not its
  `Content-Type`: a specification served as `text/html` is read, a login page served as
  `text/plain` — or an XML error from object storage — is refused with the same advice. So
  is a downloaded body that is empty or not a mapping (an SSO answering 200 with
  `Unauthorized`). Only an HTTP error status is reported as
  `HTTP <code>`; another failure after the server answered (`TooManyRedirects`) is named by
  its class, with the same advice.

- **A local specification named like `http-api.yaml` was not copied to `docs/openapi.yaml`**:
  any source starting with `http` was taken for a URL. Only `http://` and `https://` are.

- **A UTF-8 byte order mark broke JSON specifications.** Local documents, and downloaded
  ones that declare no charset or UTF-8, are decoded as `utf-8-sig`.

- **A specification URL kept its credentials in the generated tree.** The source recorded in
  `.partest/suite_ir.json` and `.partest/openapi_summary.md`, and printed by `dump-ir`, was
  the URL as given — `user:password@`, query string and fragment included. It is now stored
  and shown without them (`https://***@host/path`), and so are the URLs in error messages.
  The cleaning does not rely on URL parsing, which raised on a malformed URL (an unclosed
  `[`) and let a password with an unencoded `/` or `?` through. Any string with `://` — any
  scheme, any case, surrounding whitespace — loses its query string and fragment, and the
  credentials in its authority (the text up to the first `/`, `?` or `#`, up to its last `@`)
  become `***@`. An `@` after the authority is ambiguous — a CDN path
  (`https://cdn.jsdelivr.net/npm/@scope/pkg@1.0.0/openapi.yaml`) or the rest of a password
  with an unencoded `/`, `?` or `#` (`admin:2024/q@host`, `tok/en@github.com`) — and
  ambiguity is settled towards hiding: the URL is shown as `<URL not shown>` when the
  authority carries credentials and another `@` follows anywhere (`u:pa@ss.word/x@h.test` —
  so `u:p@registry.example/…/npm/@scope/…` is hidden too), when that `@` is there and the host has a
  `:` (a port included) or is a name without a dot that is not an IPv6 literal, and when the
  host after a userinfo `@` has a `:` not followed by a number. A dotted host without a port
  and without credentials keeps its path, so no host is invented. The cleaning never
  raises; a failure inside it shows `<URL not shown>`. A token inside the path itself cannot
  be told apart and stays. Trees generated earlier from such a URL: the next `sync-openapi` rewrites both
  `.partest` files; check your history for the old ones.

- **A method the specification declares was probed for 405.** `test_<tag>_not_allowed.py`
  picks, for each path, a method the path does not declare — but it counted only the tag's
  own live operations. A deprecated method (`POST /items` deprecated next to a live
  `GET /items`) or a method under another tag (`GET /items` tagged `items`, `POST /items`
  tagged `admin`) produced `test_post_items_not_allowed`, expecting 405 from a method the
  server answers. What a path declares is now taken from the whole specification — every
  tag, deprecated operations included, whatever `--entities` selected — and paths are matched
  by template, so `PUT /items/{id}` and `GET /items/{item_id}` are one endpoint. Probes are still
  emitted only for paths with a live operation of the tag, so a path whose operations are all
  deprecated gets none, as in 1.2.0. The file carries the banner: the next `sync-openapi`
  rewrites it, nothing to do by hand.

- **The `confpartest.py` comment on TLS described an older `partest`.** It said a
  certificate failure happens during collection "because the specification is loaded while
  the suite is assembled". The generated specification source is a local file and needs no
  TLS; a failure against the stand comes from the first test that calls the API, as
  `httpx.ConnectError` with "partest: TLS certificate verification failed", which names the
  switches. The comment now says that, and what happens to a `"url"` source from `partest`
  2.6.0 on: it is fetched on first use, and if that fails the first tracked API call raises
  `ConfpartestError` naming the source, while the coverage report is built with nothing
  counted and says why under `partest: coverage NOT COUNTED`. Older releases fetch it when
  `partest` is imported, during collection. Existing projects own `confpartest.py`; the old
  comment is wrong, not harmful, and can be left or replaced by the new one from a fresh
  `init`.

### Documentation

- `init-package-exports` is no longer advertised for `src/api/resources`. Its `--help` and
  the generator page used that path as the example; run there, it rewrites the generator's
  `__init__.py` files under a banner of its own, and `sync-openapi` then keeps them as yours
  and stops refreshing them. Both now say it is for a package you wrote by hand and that it
  rewrites every `__init__.py` under the directory whole and recursively (commit first); the
  generator page gives the full recovery: delete the `__init__.py` files under
  `src/api/resources` whose first line is
  `# AUTO-GENERATED by partest.tools.generate_init — safe to re-run`, run `sync-openapi`
  with the `--depth` the project was generated with, then `init` without `--force` for the
  skeleton's own (`resources/`, `rbac/`, `security/`). A test walks that recipe.
- The 1.2.0 entry on deprecated operations said they keep their "path constants and facade
  entries"; only the constants in `paths.py` and the facade's `paths` entries are kept, and it
  did not say that their methods were probed for 405. Corrected in place.
- The UI page and the `partest-scaffold` playbook said a certificate failure shows up during
  collection; with the current `partest` it shows up at the first API call. The generator
  page describes the exit code 2 for an unreadable specification.

## 1.2.0 — 2026-10-18

### Fixed

- **A first `from-openapi` without `--force` produced a tree that could not build its
  models.** The skeleton writes placeholders without a banner at paths the resource emitters
  own (`endpoints/paths.py`, `endpoints/__init__.py`, `payloads/__init__.py`,
  `validations/__init__.py`, `validations/common/__init__.py`,
  `validations/common/problem_detail.py`, `collections/__init__.py`,
  `collections_manager.py`), and the emitters skipped them as the user's. `pytest
  --collect-only` stayed green; the first test that asked for `models` failed with
  `ImportError: cannot import name 'CollectionsManager'`.

  A file whose bytes are exactly a skeleton placeholder — the text every released skeleton
  wrote, LF or CRLF, with or without a UTF-8 BOM — is now replaced by the generated module
  (the amendments of 2026-10-18 in `docs/wiki/decisions/banner-overwrite.md`). This repairs,
  with no manual step, `init` followed by `from-openapi` or `sync-openapi`, a re-run after an
  interrupted `from-openapi`, and trees generated by 1.1.0 or earlier without `--force`: the
  next `sync-openapi` completes them.

  **A placeholder you edited, even by one line, stays yours** and is not repaired. Sync names
  each such shared module (`paths.py`, `collections_manager.py`, `collections/__init__.py`,
  `endpoints/__init__.py`): delete those files and run `sync-openapi` again.

- **A bare `pytest` in a generated project produced an empty coverage report.** The partest
  plugin reads `confpartest` once, when it is imported, before any `conftest.py` puts the
  project root on `sys.path`; the import failed quietly and every test passed with nothing
  counted. `python -m pytest` hid it by adding the working directory. The generated
  `pytest.ini` — and the flat scaffold's — now has `pythonpath = .`. `pytest.ini` carries no
  banner: **in an existing project add the line by hand.**

  `pytest src/ui` imported `confpartest` before this change as well; it found nothing, so the
  UI run loaded no specification. With the root on `sys.path` it now loads the one
  `confpartest` names, as `python -m pytest src/ui` always did. The cause is on the `partest`
  side, which loads the specification when the harness is imported; the generated UI tree
  itself still imports neither.

- **New projects were seeded with `partest>=2.0.0`** while this package requires 2.1.0.
  `requirements/api.txt`, `requirements/ui.txt` (`partest[ui]`) and the flat scaffold's
  `requirements.txt` now seed `>=2.1.0`, and a test ties the seeded floor to `setup.py`.
  Existing projects: raise the line by hand, the files are yours.

- **`--entities` broke the other tags.** `paths.py`, `collections_manager.py` and
  `collections/__init__.py` were rebuilt from the filtered tags only, so every other
  collection failed at import; and when another tag's paths had changed in the
  specification, its facade no longer matched `paths.py`. The shared modules and the
  collection facades now cover the filtered tags plus every tag whose collection module
  already exists; a facade of a tag outside the filter wires only payload and validation
  modules that exist, at any `--depth`. A first filtered generation is unchanged. When
  another tag's paths changed, sync names it: its tests were not regenerated, run a full sync.

- **`--entities` that matched no tag rewrote every tag** — the emitters read an empty
  selection as "no filter". `from-openapi` and `sync-openapi` now exit with code 2 and list
  the specification's tags.

- **Deprecating every operation of a tag broke its tests.** `paths.py` dropped the tag's
  constants while the tests written for it stayed. Deprecated operations now keep their
  constants in `paths.py` and their entries in the collection facade's `paths`: the operation
  is still in the specification. Nothing else is generated for them — no payload builder, no
  response validator and no tests of their own, so the facade's `payload` and `validate` have
  no entry for them; such files written before the operation was deprecated stay and are not
  orphans. One thing did aim at them: the NotAllowed file took a deprecated method for one its
  path lacks and probed it for 405 — fixed in 1.2.1.
  Live operations are named first, so a deprecated path that maps to the same attribute
  (`/items/{itemId}` next to `/items/{item_id}`) takes the `_2` name and never the live
  endpoint's. *(Corrected after release: this entry first said deprecated operations keep
  their "path constants and facade entries", which read as every facade entry.)*

- **Text from the specification could run as code.** Paths, `operationId`s, summaries and
  parameter names went into emitted string literals, docstrings and comments unescaped, and
  property names became pydantic field names as they were: a path like `/x"; import os; …`
  executed when `paths.py` was imported, and a property such as `first-name` produced a
  module that did not compile. Such text is now escaped wherever it lands in code; a property
  name that is not a Python identifier becomes `field_<snake>` with the original name as the
  pydantic alias. Ordinary specifications produce the same output as before.

  The same goes for names that are valid identifiers but cannot be fields as they are — a
  name the model module itself uses (`Field`, `str`, `Optional`, `BaseModel`, …), a private
  `_name` or a pydantic-reserved `model_name`: they become `field_<snake>` with an alias
  instead of failing at import. Common names such as `id` or `type` stay as they are.

  Invisible characters from the specification — controls, bidi overrides, zero-width
  characters, line and paragraph separators — are written as `\uXXXX` escapes in emitted
  code, in `.partest/openapi_summary.md` and `P1_CHECKLIST.md`, and in what the commands
  print; in Markdown, `|` and backticks can no longer break a table or a code span.

- **A Python keyword as a tag or a path broke the whole tree.** `/import`, `/export` or a
  tag `class` produced `self.import = …` and `class=…(token=token)`, and `build_models()`
  failed for every tag. A name that is a keyword now gets a trailing `_` (`import_`,
  `collection_class_.py`). Soft keywords (`match`, `type`) are valid names and keep them.

- **Some specifications failed halfway through writing.** A lone surrogate anywhere in the
  specification cannot be encoded into a file, and on Windows a tag named like a device
  (`nul`, `con`, `aux`, `prn`, `com1`…, `lpt1`…) cannot become a directory; generation
  stopped with a traceback after part of the tree was written. Both are now refused before
  the first write, with exit code 2 (`emit_resources()` raises `ValueError`).

- **A request body with an integer `*id` property that was not the last one did not
  compile.** Its default carries a `# TODO` comment, and the comma after it landed inside the
  comment (`"user_id": 0  # TODO …,`). The comma now comes first. The test fixture has such a
  property, so the golden suite imports it.

- **`init --name` went into `confpartest.py` unescaped**; a quote in the name broke the file
  or ran code. It is now written as a string literal.

- **The generator no longer writes through links.** Every file it writes — the skeleton,
  the UI tree, `env.example` and `.gitignore` additions, `.partest/*`, the copy of the
  specification in `docs/openapi.yaml`, the generated modules — is skipped when a symlink or
  a junction lies on its path or when it resolves outside the project, and the command lists
  it ("Not written — a link …") instead. A hard link is not detected.

- **`src/api/resources/security/risk_profiles.py` did not compile**: its docstring was never
  closed. Projects that already have it own the file; close the docstring after the first
  line by hand.

### Changed

- **`P1_CHECKLIST.md` is kept up to date by `sync-openapi`.** A new checklist opens with the
  banner line and carries a paragraph of its own, `Rewritten on every sync.`; together they
  make it the generator's. A checklist written by 1.1.0 or earlier asked to be marked by hand
  ("Mark when implemented for real.") and stays yours: sync leaves it alone and names it —
  delete the file to get one that sync keeps current. Python files are recognised exactly as
  before, by the full banner line.

- `emit_resources()` raises `ValueError` when `tags_filter` matches no tag of the suite. It
  used to treat the empty selection as "no filter" and rewrite every tag.

### Added

- **`sync-openapi` reports generated files whose operation left the specification**, and
  `--prune` deletes them. A file is listed when the generator owns it (the banner opens the
  file; for a checklist, the current form) and no operation of the specification — all
  tags, deepest depth, deprecated operations included — would produce it, so a narrower
  `--depth` or `--entities` never makes the rest of the tree look abandoned. With
  `--entities` only those tags are listed and pruned. Listing is the default; deletion is
  opt-in because a sync that deletes by default would widen what it does to a tree
  (`docs/wiki/decisions/banner-overwrite.md`).

  `--prune` refuses (exit code 2) a specification with no operations, and one in which none
  of the tags already generated in the project is present — both look like the wrong file. It
  does not enter symlinks or junctions (and says how many it passed by), keeps a package
  `__init__.py` while its directory holds anything that is not an orphan, never removes the
  generated roots (`src/api/tests`, `src/api/resources/*`), and checks each path again right
  before deleting it — what fails that check is listed as "skipped on recheck" and left in
  place. A file the system refuses to delete does not stop the rest: both lists are printed
  and the exit code is 1. When tags were honestly renamed, the refusal says how to proceed: a
  sync without `--prune` first (it generates the new tags), then one with it.

  Which files are orphans also depends on the installed `partest`: its methodology decides
  which case files an operation needs. See `howto/resync`.

- `partest_gen.emitters.find_orphans(project_root, suite, *, tags_filter=None, links=None)`
  and `remove_orphans(project_root, orphans, *, failed=None, skipped=None)` — the two halves
  of `--prune`, exported from `partest_gen.emitters`. `WriteResult.refused`: paths not written
  because of a link.

### Deprecated

- `partest_gen.emitters.util.write_file`. Nothing in the package calls it; it stays for
  callers of earlier releases. It now recognises ownership by the banner and the checklist
  mark only — not skeleton placeholders, and it does not check for links — so with
  `always=True` it skips a checklist written by 1.1.0 or earlier, which it used to rewrite.

### Documentation

- The CHANGELOG entry for 1.1.0 said `partest>=2.0.0` "did not move"; the published 1.1.0
  requires `partest>=2.1.0`. Corrected in place. Releases 1.0.0, 1.0.1 and 1.1.0 now carry
  their PyPI dates.

## 1.1.0 — 2026-09-23

### Added

- **Python 3.14 is supported**, and the classifier says so because the suite was run on it,
  not because the version looked plausible: 54 passed on 3.14.4 in a clean interpreter, the
  same count as on 3.10. Nothing the generator depends on lacks a 3.14 wheel.

  The floor stays at 3.10. This adds a version rather than dropping any.

### Security

- **Dependency floors rose to the first release without a known advisory.** A floor is what
  a consumer is allowed to install, and sooner or later something installs exactly it — a
  lockfile resolved for reproducibility, an offline mirror, a `--no-binary` build on an old
  index. Auditing the *declared* floors rather than the resolved environment found eight
  advisories in two packages:

  | Package | Was | Now | Why this number |
  |---|---|---|---|
  | `requests` | `>=2.31.0` | `>=2.33.0` | PYSEC-2026-1873 is fixed in 2.32.0, PYSEC-2026-1872 in 2.32.4, PYSEC-2026-2275 in 2.33.0 — the earliest release free of all three, not the newest release |
  | `pytest` (extra `dev`) | `>=8.0.0` | `>=9.0.3` | PYSEC-2026-1845 has no fix in the 8.x line at all |

  `pyyaml>=6.0.2` audits clean at its floor and did not move.

- **The floor on `partest` rose to 2.1.0** (was `>=2.0.0`). Not because the generator needs
  anything new in it: the 2.0.x releases declare vulnerable floors of their own, and on a
  minimum resolution those arrive here transitively. 2.1.0 is the first release with them
  raised. *(Corrected after release: this entry first said the `partest` floor did not move.)*

- **The `dev` extra no longer installs pytest 8.** Contributors to this repository need
  pytest 9.0.3 or newer; there is no fix for PYSEC-2026-1845 inside 8.x, so supporting it
  would mean asking people to develop on a version with a known advisory. This affects
  only `pip install -e ".[dev]"` — `partest-gen` itself neither imports pytest nor
  registers a plugin, and nothing constrains the pytest version in *your* suite. No upper
  bound is declared for the same reason.

- **Generated projects are no longer seeded with vulnerable minimums.** `partest-gen init`
  writes `requirements/{base,api}.txt`, and those floors were the ones a new suite starts
  from. Auditing them the same way found four:

  | Seeded in | Was | Now | Advisory |
  |---|---|---|---|
  | `requirements/api.txt`, `ui.txt` | `pytest>=8.0.0` | `pytest>=9.0.3` | PYSEC-2026-1845 |
  | `requirements/api.txt` | `requests>=2.31.0` | `requests>=2.33.0` | PYSEC-2026-1873, -1872, -2275 |
  | `requirements/base.txt` | `pydantic>=2.0.0` | `pydantic>=2.4.0` | PYSEC-2026-1812 |
  | `requirements/base.txt` | `python-dotenv>=1.0.0` | `python-dotenv>=1.2.2` | PYSEC-2026-2270 |

  Three plugin floors travelled with pytest's, because a set of floors has to be
  installable *and runnable* at its minimum, not only resolvable from the newest index:

  | Seeded | Was | Now | What the old floor did next to pytest 9 |
  |---|---|---|---|
  | `pytest-asyncio` | `>=0.23.7` | `>=1.3.0` | declares `pytest<9` up to 1.2.0 — the minimum does not install |
  | `pytest-playwright` | `>=0.5.0` | `>=0.7.2` | declares `pytest<9.0.0` up to 0.7.1 — the minimum does not install |
  | `allure-pytest` | `>=2.8.18` | `>=2.13.3` | installs, then errors **every** test in `pytest_runtest_setup` with `AttributeError: 'str' object has no attribute 'iter_parents'` |

  **In an existing generated tree these files are yours**, not the generator's: they carry
  no `AUTO-GENERATED` banner, so `sync-openapi` will not update them. Raise the floors by
  hand — nothing else in the suite has to change, and a suite already running on newer
  plugins is unaffected, because these are minimums, not pins.

  The pinned flat scaffold (`RootFilesContainer`) was corrected under 1.0.0 — "The
  `requirements.txt` of the flat scaffold matches what `partest` declares today". The G1
  skeleton, which is what `init` actually writes, was missed then; this finishes that job.

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

## 1.0.0 — 2026-09-23

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
