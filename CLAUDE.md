# CLAUDE.md - the lightcycle-workflows origin

This repo is the built-in `lightcycle` workflow **origin** - the `lc` engine pulls it into an immutable, sha-pinned bundle. It is content (workflow + step markdown), never engine code.

## The lightcycle repos

lightcycle is four coordinated repos. A change that spans them lands in tandem.

- **lightcycle** - the `lc` engine: CLI, agent pool, and store. Pipx-installed, zero runtime deps, workflow-agnostic. The only home for engine code.
- **lightcycle-workflows** (this repo) - the built-in workflow origin: pullable bundles (`source.toml` + `workflows/*.md` + `steps/*.md`) the engine turns into sha-pinned, per-item pins. Content, not engine code.
- **lightcycle-specs** - design docs (`lightcycle/*.md`) and briefs (`briefs/*.md`). Specs land there through the spec-PR review gate before code is built.
- **lightcycle-plugin** - the Claude Code companion: a marketplace repo whose SessionStart hook bootstraps the engine (pipx) and whose skills (e.g. `author-workflow`) help you work with it.

The engine _pulls_ these workflows; a change to the engine's contract, the workflow grammar, or the audit/hook model usually spans several repos.

_Cross-repo process (PR-flow, coupled changes) is a driver operation - see the engine's `prompts/driver.md`._

## Conventions

- A source is **self-contained**: `source.toml` (with a required `contract`), `workflows/*.md` (the flow graph - entry / requires / workspace / nodes / edges / hooks / signals), and `steps/*.md` (role prompts with `model` + `accepts`/`produces`). Steps are shared _within_ a bundle, copied _across_ origins.
- The engine defines the grammar and the hook catalog; the `author-workflow` skill (in lightcycle-plugin) is the guide. `lc workflow add` and `lc flow` validate a bundle - fix what they name, do not work around them.
- The periodic retro audit is an **engine service**, not a workflow step - do not wire it here.
- Hyphens not emdashes. Format markdown with `prettier --prose-wrap=never`.
