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

This repo is decoupled from the engine's release cadence: `lc upgrade` updates the engine code; `lc workflow upgrade` updates these workflows. They share only the `contract` version.
