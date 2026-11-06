# lightcycle-workflows

The built-in workflow source for [lightcycle](https://github.com/kenmclennan/lightcycle) - the `lightcycle` origin. `lc init` pulls this repo on first run; `lc workflow upgrade lightcycle` pulls updates.

It is an ordinary workflow source, following the structural convention any source uses:

```
source.toml            # manifest: name, contract, description
workflows/*.md         # the flow graphs (entry, edges, hooks, requires, workspace)
steps/*.md             # the steps the workflows reference (shared within this bundle)
```

- `source.toml`'s `contract` is the engine contract version these workflows target; the engine refuses to pull a source whose contract it does not support.
- Workflows and steps are discovered from the files - there is no explicit list to keep in sync.
- A pulled version is an immutable, self-contained bundle: its workflows reference only the steps in this same bundle.

## Workflows

An item runs one workflow, named on the item (`lc new item "<title>" --workflow lightcycle/<name>`), or inherited from its parent item. Each has its own doc with a flowchart and step-by-step description.

| Workflow | Gates | Summary |
| --- | --- | --- |
| [`spec-driven`](docs/spec-driven.md) | spec PR, code PR | A brief becomes a formal spec on a spec PR; once merged, the same item is built, reviewed, and merged on a code PR. |
| [`bdd-driven`](docs/bdd-driven.md) | spec PR, feature PR, code PR | A behaviour-first variant: the spec is followed by executable gherkin `.feature` scenarios agreed on their own PR, which the code must then make pass. |
| [`workflow-authoring`](docs/workflow-authoring.md) | spec PR, code PR | A brief becomes a workflow-design spec (mermaid + step/gate/trigger descriptions) on a spec PR; once merged, the same item authors the bundle and gets it merged on a code PR, gated by the simulator. |
| [`bump-engine-pin`](docs/bump-engine-pin.md) | code PR (only if stale) | Checks the repo's engine pin against the engine's own `main`; at or below threshold the item closes unattended, no PR opened, otherwise it bumps the pin and merges through the generic PR machinery. |
| [`retro-audit`](docs/retro-audit.md) | none (scheduled) | Suggests a daily schedule behind the `pending-reflections` guard (30 pending); audits a batch of closed items for process defects and routes any findings to a human gate. Not enabled by the bundle. |
| [`review-yield`](docs/review-yield.md) | none (scheduled) | Suggests a weekly schedule behind a guard that skips a week with no new review verdicts or escapes; judges whether agent review is earning its cost (catch rate, escapes, cost per real finding, trend) and routes proposed review-step changes to a human gate. Not enabled by the bundle. |
| [`material-audit`](docs/material-audit.md) | none (scheduled) | Suggests a weekly schedule behind the `materials-changed` guard; audits the guidance and workflow material and routes any findings to a human gate. Not enabled by the bundle. |
| [`ratchet-sweep`](docs/ratchet-sweep.md) | none (scheduled) | Declared by the bundle, scheduled by the engine; sweeps active repos for missing ratchet guards and baselines that have stopped shrinking, and routes any findings to a human gate. |
| [`daily-summary`](docs/daily-summary.md) | none (scheduled) | Suggests a 07:00 schedule behind the `day-unsummarised` guard; writes a standup-ready list of the previous day's closes (Delivered / Fixed / Improved). Not enabled by the bundle. |
| [`guidance-entry`](docs/guidance-entry.md) | code PR | Changes to the guidance repo: a writer writes, edits or retires entries, a mechanical check catches any that break `CONVENTIONS.md`, and the PR merges through the generic machinery. |
| [`small-change`](docs/small-change.md) | code PR | A change small and low-risk enough that a spec and a separate agent review round would cost more than they'd catch: one stage scopes and codes straight from the item's brief, then the generic PR/CI machinery carries it to merge. |

This repo is decoupled from the engine's release cadence: `lc upgrade` updates the engine code; `lc workflow upgrade` updates these workflows. They share only the `contract` version.
