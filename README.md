# partest-gen

Scaffold a runnable pytest + [partest](https://github.com/Dec01/partest) suite from an OpenAPI
document: endpoints, payloads, validations, collection facades and the priority-one stub
matrix, plus an optional isolated UI tree.

**PyPI:** https://pypi.org/project/partest-gen/ — install from here.
**Source:** you are looking at it — see [docs/wiki/index.md](docs/wiki/index.md) for how it
works and why.

```bash
pip install partest-gen
partest-gen from-openapi ./my-suite --file openapi.yaml --depth p1 --with-ui
```

## Working in this repository

| Start here | For |
|---|---|
| [AGENTS.md](AGENTS.md) | rules and red lines for anyone (human or agent) changing this repo |
| [docs/wiki/index.md](docs/wiki/index.md) | documentation catalog — one line per page |
| [docs/wiki/status.md](docs/wiki/status.md) | current version, waves, what is next |
| [docs/wiki/howto/contribute.md](docs/wiki/howto/contribute.md) | invariants, tests, how to make a change |
| [docs/wiki/WIKI.md](docs/wiki/WIKI.md) | how the documentation itself is organized |
| [.claude/skills/](.claude/skills/) | procedures: scaffold a suite, release, maintain docs |

```bash
python tools/check_all.py           # everything CI runs: tests, docs lint, index, wheel drift
python -m pytest tests/ -q          # emitters, golden suite, docs lint
python tools/docs_build_wheel.py    # regenerate partest_gen/docs from the wiki
```

## Layout

```text
partest_gen/      generator source (see docs/wiki/components/generator.md)
  docs/           generated user docs shipped in the wheel — do not hand-edit
docs/
  PYPI.md         long_description for the PyPI page
  wiki/           documentation: concepts, components, howto, decisions
tools/            documentation tooling
tests/            emitter tests and the golden end-to-end suite
```

## Relationship to partest

One-directional: `partest-gen` depends on `partest`, never the reverse. The harness owns the
coverage methodology; this package reads it and writes code against it. Why they are separate
distributions: [docs/wiki/decisions/separate-package.md](docs/wiki/decisions/separate-package.md).

`partest.project_gen` still works as a deprecated bridge to this package, and
`pip install 'partest[gen]'` installs both.

## License

MIT.
