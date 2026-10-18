---
title: partest-gen — parts of the generator
status: current
verified: 2026-10-18
sources: [partest_gen/cli.py, partest_gen/ir.py, partest_gen/skeleton.py, partest_gen/openapi_load.py, partest_gen/emitters/resources.py, partest_gen/_fsguard.py, partest_gen/emitters/paths.py, partest_gen/emitters/schema_py.py]
audience: agent
ships_in_wheel: true
---

# partest-gen — parts of the generator

What the tool is made of and what each command produces. For the first run start at
[[howto/scaffold]]; for what you may edit afterwards, [[concepts/generated-contract]].

```bash
pip install partest-gen
```

`partest` comes with it — the generated suite runs on that harness, so the two are installed
together on purpose.

---

## 1. What it produces

From an OpenAPI document (plus an optional UI flag) a **runnable** pytest project that:

1. uses the `partest` harness through its public API — nothing vendored, nothing copied;
2. follows the coverage methodology: every operation is classified into a method subtype, and
   the stub set for that subtype is emitted with the correct `type=` on each call;
3. keeps API and UI suites in separate trees that do not share a session;
4. contains no product secrets, no role lists and no domain values.

The output is a set of **stubs with structure**, not finished tests. What "finished" means and
who owns which file: [[concepts/generated-contract]].

## 2. Pipeline

```text
OpenAPI document
   │  openapi_load.py      YAML/JSON, local path or URL
   ▼
SuiteIR                    ir.py — one OpIR per operation
   │                       method, path, tag, subtype, required_p1, params,
   │                       request_schema, success_response_schema, success_status
   ▼
emitters/                  resources.py drives the rest
   ▼
project tree               resources.py / skeleton.py write files, honouring the banner contract
```

The subtype and the required case list are **not decided here**. `ir.py` calls
`classify_endpoint` and `p1_test_cases` from `partest.methodology.api`, so a suite and its
generator always agree about what an endpoint is. Changing classification means changing
`partest`. The `api` in that path is an area, not a package layout detail: the harness release
this package requires splits its methodology into an API half and a UI half, and only the API
half is derived from a specification — which is the only half a generator reading OpenAPI can
use. The required version is in `CHANGELOG.md`.

## 3. Target tree

```text
{project}/
├── requirements/{base,api,ui,local}.txt
├── confpartest.py, conftest.py, env.example, pytest.ini
├── docs/{README.md, UI_GUIDE.md}
├── scripts/{run_ui.ps1, run_ui.sh}
├── .partest/{suite_ir.json, openapi_summary.md}
└── src/
    ├── api/
    │   ├── resources/{endpoints,payloads,validations,collections,rbac,security}
    │   └── tests/{conftest,test_zorro,<tag>/…}
    └── ui/                          # only with --with-ui / init-ui
        ├── conftest.py              # must not load OpenAPI — see [[components/ui-layer]]
        ├── pages/, components/, fixtures/, utils/, tools/
        ├── resources/ui_rbac_matrix.py
        ├── baselines/{reference,actual,diff}
        └── tests/{smoke,auth,rbac,visual}
```

## 4. Commands

```bash
# whole suite from a specification
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --with-ui

# empty skeleton, no specification yet
partest-gen init ./my-suite --name my-suite

# refresh generated artifacts after the specification changed
partest-gen sync-openapi ./my-suite --depth p1
# … and delete generated files whose operation is gone (otherwise only listed)
partest-gen sync-openapi ./my-suite --depth p1 --prune

# add the UI tree to an existing project
partest-gen init-ui ./my-suite

# inspect what the generator understood, without writing a project
partest-gen dump-ir openapi.yaml -o suite_ir.json

# regenerate package __init__ re-exports under a resources tree
partest-gen init-package-exports ./my-suite/src/api/resources
```

| `--depth` | Emits |
|---|---|
| `resources` | paths + collection facades |
| `default` | + payloads, validations, Default and NotAllowed tests |
| `p1` | + the full priority-one stub set per subtype, plus `P1_CHECKLIST.md` per tag |

| Flag | Meaning |
|---|---|
| `--entities a,b` | only these OpenAPI tags; the shared `paths.py`, collection facades and manager keep every tag already generated. A list matching no tag is refused |
| `--with-ui` | also emit the UI tree (orthogonal to `--depth`) |
| `--force` | overwrite files that do not carry the generated banner |
| `--prune` | `sync-openapi` only: delete generated files no operation of the specification produces any more; without it they are listed. Refused for a specification with no operations |
| `--version` | which generator produced a tree — the first thing to check on a bug report |

UI is orthogonal to depth. For a greenfield project `--depth p1 --with-ui` is the usual choice.
`--force` is not needed for a new directory: a file that is still exactly a skeleton
placeholder is replaced by the generated module either way, so `init` followed by
`from-openapi` or `sync-openapi` gives the same tree.

## 5. Emitters

| Emitter | Output |
|---|---|
| `paths` | `src/api/resources/endpoints/paths.py` — path constants per tag, deprecated operations included |
| `collections` | `collection_<tag>.py`, manager, factory |
| `payloads` | `payloads/<tag>/*_payload.py` — shape-correct request bodies |
| `validations` | `validations/<tag>/*_validation.py` — response models |
| `tests_default` | Default and NotAllowed cases |
| `tests_p1` | the subtype's priority-one set: permissions, new/update object, incorrect body, elements, … |
| `ui_layout` | the whole `src/ui` tree, scripts and the UI guide |

No emitter touches the filesystem on its own. They return `path -> source`;
`resources.py` collects that into one plan and writes it, applying the overwrite policy, and
`skeleton.py` does the same for the skeleton and the UI tree. Every write — these, `.partest/*`,
the copy of the specification — is refused when a symlink or junction lies on its path or it
resolves outside the project, and the command lists it. Text from the specification (paths,
`operationId`s, summaries, property and parameter names) is escaped wherever it lands in code,
invisible characters included; a property name that cannot be a field as it is (not an
identifier, a keyword, a name the module uses, `_private`, `model_*`) becomes `field_<snake>`
with an alias, and a tag or path that is a Python keyword gets a trailing `_`. A specification
that cannot be written at all — a lone surrogate, or on Windows a tag named like a device —
is refused before the first write. The same plan, taken for every tag at the deepest depth with
deprecated operations included, is what `sync-openapi` compares the tree against to find
orphans.

### Python API

Exported from `partest_gen.emitters` — the same calls `sync-openapi` makes:

| Call | Does |
|---|---|
| `emit_resources(project_root, suite, *, force=False, tags_filter=None, write_ir=True, depth="default") -> WriteResult` | writes the plan; `result.created`, `.skipped`, `.refused` (a link on the way). `ValueError` when `tags_filter` matches no tag |
| `find_orphans(project_root, suite, *, tags_filter=None, links=None) -> list[str]` | generated files no operation produces any more, project-relative. Pass a list as `links` to receive the links it did not enter |
| `remove_orphans(project_root, orphans, *, failed=None, skipped=None) -> list[str]` | deletes them after checking each again; returns what was deleted, puts paths that failed the re-check into `skipped` and those the system refused into `failed` |

`suite` is what `partest_gen.openapi_load.load_openapi(path_or_url)` returns.

## 6. Artifacts to read after a run

| File | Why |
|---|---|
| `.partest/openapi_summary.md` | operations × subtype × required cases — the map of the work |
| `.partest/suite_ir.json` | the same, machine-readable, if you script on top |
| `src/api/tests/<tag>/P1_CHECKLIST.md` | per tag, every required case and its stub file; rewritten on every sync, so progress is read from the coverage report (`missing_p1`) |

Then: [[howto/after-generation]].

## 7. Limits worth knowing

- **Classification is heuristic.** Unusual paths get a plausible subtype, not a certain one.
  Check the summary before trusting the stub set; `partest` accepts explicit per-route
  overrides for the cases the heuristic cannot get right.
- **Payloads are shape-correct, not domain-correct.** Required business values are yours.
- **`sync-openapi` refreshes generated files only.** Hand-written tests that referenced a
  removed operation will not be fixed for you — see [[howto/resync]]. Generated files of a
  removed operation are listed after the sync and deleted only with `--prune`.
- **OpenAPI `webhooks` and `callbacks` are not emitted.** They are skipped silently today.
