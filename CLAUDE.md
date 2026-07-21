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
- The engine defines the grammar and the hook catalog; the `author-workflow` skill (in lightcycle-plugin) is the guide. `lc workflow add` and `lc workflow check` validate a bundle - fix what they name, do not work around them.
- The periodic retro audit is an **engine service**, not a workflow step - do not wire it here.
- Hyphens not emdashes. Format markdown with `prettier --prose-wrap=never`.

## Authoring a workflow in this repo

When the pipeline (or you) builds a workflow here - a new `workflows/<name>.md`, or an adaptation, plus any `steps/*.md` it needs - the conventions differ from a code build:

- **The spec is a workflow design, not a code spec.** For a workflow-authoring item, the spec (in `lightcycle-specs`, as usual) designs the flow: a mermaid flowchart of the graph (stages, outcome edges, hook-injected transitions, review gates) plus a short description of each step, gate, and trigger - so a human reviews the flow on the spec PR before any bundle is written.
- **Author with the `lightcycle:author-workflow` skill.** Invoke it for the grammar, the hook catalog, the `steps` `accepts`/`produces` contract, and the self-contained-bundle rule; author the bundle to match the approved design. Do not reconstruct the grammar from memory.
- **The gate is the simulator, not a test suite.** A bundle has no unit tests; its dynamic gate is `lc workflow check <origin>/<name>` (static composition) plus the `simulate` CI job (a full dry-run walk through the engine). Both must pass - that is what `watch-ci`/`review-code` verify here instead of `bash tests/run.sh`. `lc workflow describe <origin>/<name> --mermaid` renders the built graph to confirm it matches the design mermaid.
