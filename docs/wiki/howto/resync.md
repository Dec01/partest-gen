---
title: Re-syncing after the specification changed
status: current
verified: 2026-10-25
sources: [partest_gen/cli.py, partest_gen/emitters/resources.py, partest_gen/emitters/util.py]
audience: user
ships_in_wheel: true
---

# Re-syncing after the specification changed

An API grows. `sync-openapi` re-emits the generated half of the project from the new
specification and leaves the rest alone.

```bash
partest-gen sync-openapi ./my-suite --file openapi.yaml --depth p1
```

Read [[concepts/generated-contract]] before the first sync in a project you care about. It
decides which of your files are overwritten, and the answer is not "none".

## What happens

| | |
|---|---|
| Re-emitted | every file carrying the generated banner: paths, payloads, validations, collection facades, the stub matrix; checklists of the current form; skeleton placeholders nobody edited |
| Kept, with a hint | checklists written by earlier releases, which asked to be marked by hand — delete one to get a current one |
| Left alone | everything else, including tests you edited into real tests |
| Refreshed | `.partest/suite_ir.json` and `.partest/openapi_summary.md` |
| Copied | only with `--file`: the specification into `docs/openapi.yaml`, so the project records what it was generated from. A `--url` download is not saved; the command says so while `docs/openapi.yaml` is still the placeholder |
| Listed | generated files no operation produces any more — deleted only with `--prune` |

`--depth` means the same as during generation. Passing a smaller depth than last time does not
remove the deeper files and does not list them as orphans; it only stops refreshing them.

## The safe sequence

```bash
git status                     # a clean tree, so the sync is the only change in the diff
partest-gen sync-openapi ./my-suite --file openapi.yaml --depth p1
git diff --stat                # what the generator actually touched
pytest src/api/tests --collect-only -q
```

The collect-only pass is the important one. A removed or renamed operation takes its path
constant and collection wiring with it, and a hand-written test that imported them now fails
to import. That is the failure you want — loud, immediate, and pointing at the file. Fixing it
is renaming an import or deleting a test for an endpoint that no longer exists.

Never run a sync on a dirty working tree. When the diff mixes your edits with the generator's,
there is no way to tell which is which afterwards.

## Operations that were removed

The generated files that belonged only to a removed operation or tag — its payload and
validation modules, its stub tests, its collection facade, its checklist — are not rewritten,
because nothing produces them any more. The sync lists them:

```text
Orphaned generated files (no operation in the specification): 3
  ! src/api/resources/payloads/items/post_items_payload.py
  ...
Delete them with --prune (only files the generator owns are listed).
```

Read the list, then run the same command with `--prune`. Only files the generator owns are
listed — a Python file that opens with the banner, a checklist of the current form; anything
else is yours and is never listed or deleted. The list is measured against the whole
specification at the deepest depth, deprecated operations included, so `--depth resources`
does not report the stub tests, and with `--entities` only those tags are listed and pruned.

`--prune` does not follow symlinks or junctions (the sync says how many it passed by), keeps a
package `__init__.py` while anything else lives in its directory, and never removes
`src/api/tests` or the `src/api/resources/*` roots. It refuses — exit code 2, nothing written —
a specification with no operations and one in which none of the tags already generated in the
project is present: both are far more often the wrong file than an API that changed that
much. If the tags really were renamed, prune in two steps: a sync without `--prune` (it
generates the new tags), then the same command with it. A file the system will not delete is
listed and the exit code is 1; one that changed since the scan — edited, its banner removed —
is listed as "skipped on recheck" and left alone.

`--entities` that matches no tag of the specification is refused too, with the list of tags.
So a tag that vanished from the specification is pruned by a sync **without** `--entities`.
A run with `--entities` still rebuilds `paths.py` and the collection facades of every tag; if
another tag's paths changed, the sync names it — its tests were not regenerated, so run a full
sync.

**The list also depends on `partest`.** Which case files an operation needs is decided by the
methodology in the installed `partest`, not by the specification alone. After upgrading
`partest`, a sync may list stub files of a case the new methodology no longer asks for — read
the list before passing `--prune`, especially on the first sync after an upgrade.

Deleting is opt-in on purpose: a sync that removes files by default would do more to a tree
than the banner contract promised. If a listed file holds work you want, remove its banner
first — then it is yours and stays.

## New operations

They arrive as new stubs, skipped, with a fresh entry in the tag's checklist. Nothing about
them is different from the first generation: [[howto/after-generation]].

## Operations that changed shape

A field added to a request body reaches the payload module. A changed response reaches the
validation module. Neither reaches the assertions you wrote about specific values — those are
yours, they still compile, and they may now be wrong. After a sync that changed a schema, run
the affected tests against a real stand rather than trusting a green collect.

## When `--force` is the answer

Rarely. It overwrites files without the banner too, which means your tests. Use it when you
deliberately regenerate a project — an abandoned scaffold, an experiment, a tree you are
recreating from scratch — and never as a way to get past an error message.

If a sync refuses to update something and you are tempted to reach for `--force`, the file
has lost its banner: someone edited a generated file by hand, or copied one. Move the custom
part out to a sibling module and let the generated file be generated again.
