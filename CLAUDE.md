# CLAUDE.md - the lightcycle-workflows origin

This repo is the built-in `lightcycle` workflow **origin** - the `lc` engine pulls it into an immutable, sha-pinned bundle. It is content (workflow + step markdown), never engine code.

## The lightcycle repos

lightcycle is four coordinated repos (engine / workflows / specs / plugin); this is the built-in workflow origin - see `lightcycle/CLAUDE.md` for the full map. A change that spans them lands in tandem.

The engine _pulls_ these workflows; a change to the engine's contract, the workflow grammar, or the audit/hook model usually spans several repos.

_Cross-repo process (PR-flow, coupled changes) is a driver operation - see the engine's `prompts/driver.md`._

## Conventions

- A source is **self-contained**: `source.toml` (with a required `contract`), `workflows/*.md` (the flow graph - entry / requires / workspace / nodes / edges / hooks / signals), and `steps/*.md` (role prompts with `model` + `accepts`/`produces`). Steps are shared _within_ a bundle, copied _across_ origins.
- The engine defines the grammar and the hook catalog; the built-in bundles (`workflows/spec-driven.md` + its `steps/*.md`) are the working reference to model from. `lc workflow add` and `lc workflow check` validate a bundle - fix what they name, do not work around them.
- **The authoring process is not restated here - it lives in the workflow.** Workflows in this repo are built by the `workflow-authoring` pipeline, whose `design-workflow`/`build-workflow`/`review-workflow` steps carry the authoring craft (the grammar, the hook catalog, the design mermaid, and the `lc workflow check` + `simulate` gate) inline, so a pulled bundle is self-contained. Editing a bundle by hand, model it on the existing bundles, never on the engine source: a distributed setup has the pipx binary, not `graph.py`/`cli.py`/`contracts.py`, so a bundle designed by reading engine internals cannot be reproduced. A gap is something to fix in a step, not a reason to open the source. (For shaping a new flow with a human before it's built, the `author-workflow` skill in lightcycle-plugin is the co-design guide.)
- The periodic retro audit is an **engine service**, not a workflow step - do not wire it here.
- Hyphens not emdashes. Format markdown with `prettier --prose-wrap=never` - except `workflows/*.md`: its `entry`/`requires`/`workspace`/`phase`/`nodes`/`edges`/`hooks`/`signals` block is significant-whitespace-aligned, not prose, and prettier collapses it onto unreadable single lines. Never run prettier on a `workflows/*.md` file; hand-edit it and match the existing column alignment.
