---
title: From an OpenAPI file to a collectable suite
status: current
verified: 2026-09-13
sources: [partest_gen/cli.py, partest_gen/skeleton.py, partest_gen/emitters/resources.py]
audience: user
ships_in_wheel: true
---

# From an OpenAPI file to a collectable suite

The first run, end to end. Twenty minutes, no stand required — everything here works against
a specification file alone.

## 1. Install

```bash
pip install partest-gen
```

`partest` arrives as a dependency: the generated suite runs on that harness. Python 3.10 or
newer.

For a UI suite as well:

```bash
pip install 'partest[ui]'
playwright install chromium
```

## 2. Look before you write

```bash
partest-gen dump-ir openapi.yaml -o suite_ir.json
```

This writes nothing except the file you asked for. Read it — or the summary the full run
produces — before generating into a directory you care about. What to look at:

- the operation count, against what you expected from the specification;
- the `subtype` on a few endpoints you know well. Classification is heuristic, and this is the
  cheapest moment to notice it guessed wrong;
- `required_p1` — the case list each operation will get stubs for.

## 3. Generate

```bash
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1
```

Add `--with-ui` for the browser tree, `--entities orders,users` to limit to some tags. A URL
works in place of `--file`:

```bash
partest-gen from-openapi ./my-suite --url https://api.example.com/openapi.json --depth p1
```

`--depth` controls how much is emitted: `resources` for paths and collection facades only,
`default` to add payloads, validations and the first tests, `p1` for the full stub matrix.
Start at `p1` unless you have a reason not to — the extra files are skipped stubs, and a
smaller depth is not a smaller commitment, only a shorter checklist.

## 4. Check it holds together

```bash
cd my-suite
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements/api.txt
pytest src/api/tests --collect-only -q
```

Collect-only is the acceptance test for a generation: every emitted module imports, every test
is discovered, nothing runs. If this is green, the tree is sound and the rest is your work.

A red collect almost always means the specification used a shape the emitters could not
express. The error names the file; the operation it came from is in
`.partest/openapi_summary.md`.

## 5. Read the three maps

| File | What it tells you |
|---|---|
| `.partest/openapi_summary.md` | every operation, its subtype, the cases it needs |
| `src/api/tests/<tag>/P1_CHECKLIST.md` | the same as a per-tag backlog you can tick off |
| `src/api/resources/endpoints/paths.py` | the path constants to use instead of raw strings |

## 6. Wire the environment

```bash
cp env.example .env
```

Fill `BASE_URL`, and the OIDC settings if the API needs a token. Then fill
`src/api/resources/rbac/roles.py` with the roles your project has and where their credentials
come from — environment variables, never literals. Uncomment the `TokenManager` fixtures in
`src/api/tests/conftest.py` once roles exist.

Never commit a filled `.env`, a password, or a private stand URL.

## 7. Then what

The tree is stubs. Turning them into tests is a loop, not a step:
[[howto/after-generation]].

When the specification changes: [[howto/resync]] — and read
[[concepts/generated-contract]] first, because it decides which of your files survive.
