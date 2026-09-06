<!-- Part of the partest-gen package: generated documentation, not hand-written.
     Read it with `python -m partest_gen.docs`. Local edits are lost on upgrade. -->

# Re-syncing after the specification changed

An API grows. `sync-openapi` re-emits the generated half of the project from the new
specification and leaves the rest alone.

```bash
partest-gen sync-openapi ./my-suite --file openapi.yaml --depth p1
```

Read [The contract of generated code](concepts-generated-contract.md) before the first sync in a project you care about. It
decides which of your files are overwritten, and the answer is not "none".

## What happens

| | |
|---|---|
| Re-emitted | every file carrying the generated banner: paths, payloads, validations, collection facades, the stub matrix, the checklists |
| Left alone | everything else, including tests you edited into real tests |
| Refreshed | `.partest/suite_ir.json` and `.partest/openapi_summary.md` |
| Copied | the specification into `docs/openapi.yaml`, so the project records what it was generated from |

`--depth` means the same as during generation. Passing a smaller depth than last time does not
remove the deeper files; it only stops refreshing them.

## The safe sequence

```bash
git status                     # a clean tree, so the sync is the only change in the diff
partest-gen sync-openapi ./my-suite --file openapi.yaml --depth p1
git diff --stat                # what the generator actually touched
pytest src/api/tests --collect-only -q
```

The collect-only pass is the important one. A removed or renamed operation takes its path
constant, payload and validation with it, and a hand-written test that imported them now fails
to import. That is the failure you want — loud, immediate, and pointing at the file. Fixing it
is renaming an import or deleting a test for an endpoint that no longer exists.

Never run a sync on a dirty working tree. When the diff mixes your edits with the generator's,
there is no way to tell which is which afterwards.

## New operations

They arrive as new stubs, skipped, with a fresh entry in the tag's checklist. Nothing about
them is different from the first generation: [Turning stubs into tests](howto-after-generation.md).

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
