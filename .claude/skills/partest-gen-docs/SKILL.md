---
name: partest-gen-docs
description: >
  Maintain the partest-gen documentation wiki: add or update a page, refresh a stale one,
  ingest a new source snapshot, and run the doc linter. Use when documentation is out of date,
  a page must be added or archived, or the docs lint fails.
---

# Maintaining the documentation wiki

## When to use this

- Code changed and a page's `verified:` date is now behind its `sources:`
- `tools/docs_lint.py` or `tests/test_docs.py` fails
- A page must be created, split, or archived
- A new source (a request, an incident write-up, someone else's spec) must reach the wiki

Conventions live in `docs/wiki/WIKI.md`; rationale in
`docs/wiki/decisions/docs-in-wheel.md`. Read those before restructuring anything.

## The three operations

### Update — code moved ahead of the page

1. Read the code named in the page's `sources:`, not your memory of it.
2. Fix the page, refresh `verified:`, add any new files to `sources:`.
3. If the page ships in the wheel, run `python tools/docs_build_wheel.py`.

### Ingest — a new source arrived

1. Put it under `docs/raw/<source>/<date>/` — git-ignored on purpose. **Never edit a raw
   source in place**; a newer snapshot goes in a new dated directory and the old one stays.
2. Never commit the snapshot. What reaches the repository is the conclusion drawn from it,
   written in your own words on a wiki page.
3. Distribute the conclusions — usually `status.md` plus one or two topic pages.
4. Append an entry to `docs/wiki/log.md` saying what was taken from the snapshot.

### Lint — periodic health check

```bash
python tools/docs_lint.py            # report
python tools/docs_lint.py --strict   # non-zero exit on any finding
python tools/docs_index.py           # rebuild docs/wiki/index.json
python tools/docs_build_wheel.py     # regenerate partest_gen/docs
```

Checks: broken `[[wiki-links]]`, missing `sources:` paths, pages whose `sources` changed after
`verified`, version literals outside allowed pages, private markers or consumer names in pages
with `ships_in_wheel: true`, and drift between `docs/wiki` and generated `partest_gen/docs`.

## Rules

1. **Nothing is deleted silently.** Move with `git mv`, or record the successor in `log.md`.
2. **One fact, one place.** Status, version and "what is next" exist only in
   `docs/wiki/status.md`. Everything else links to it.
3. **Code beats documents.** When they disagree, fix the document.
4. **Later date beats earlier date.** When two documents disagree, take the newer source — and
   say so explicitly in `status.md` rather than quietly picking a side.
5. **Do not hand-edit `partest_gen/docs/`.** It is generated.
6. **Every page that describes code needs a non-empty `sources:`.**
7. **A page that ships may only link to pages that ship.** Otherwise the wheel keeps a dangling
   title of an internal document. The linter catches it; do not work around it by unshipping
   the target — rewrite the sentence.
8. Keep `AGENTS.md` at 60 lines or under. Status tables do not belong there.

## Language

Shipped pages (`ships_in_wheel: true`) are **English** — anyone who installs the package reads
them. Internal pages (`status`, `log`, `decisions/`, `howto/contribute`) are Russian, for the
maintainer. Never mix the two inside one page.

## Adding a page

```yaml
---
title: <short noun phrase>
status: current
verified: <today>
sources: [partest_gen/<the files this page describes>]
audience: user | maintainer | agent
ships_in_wheel: false
---
```

Then: one line in `docs/wiki/index.md`, and one line in `docs/wiki/log.md`.

Category by the question it answers — `concepts/` why, `components/` what exists, `howto/` how
to do it, `decisions/` why this way and not another.

## The other repository

Harness, methodology and coverage documentation live in `partest`
(https://github.com/Dec01/partest). Do not copy its pages here — a copy goes stale the day the
original changes. Link to it as a plain URL; `[[wiki-links]]` do not cross repositories.

If a fact belongs to both — the `partest` floor, what the bridge module does — it lives in
`status.md` here and in `status.md` there, and both are updated in the same session.

## RAG

Not enabled. The corpus is small enough that the index plus grep beats embeddings. It is kept
RAG-ready (`docs/wiki/index.json`); the switch-on criteria are in `docs/wiki/WIKI.md`. Do not
build a vector index without checking them, and note that turning it on means indexing both
repositories, not this one alone.
