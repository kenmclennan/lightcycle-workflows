# Principal output

A step's front matter can name its **principal output**: what the step authors. The engine uses it at a human gate to pick the callouts that apply to the work the gate presents, so a spec gate and a code gate each run only their own views. The design is LC-1577's; this page records the values the official workflows use.

```yaml
---
model: sonnet
principal-output: code
---
```

Principal output is separate from `produces`, which lists artifact types (`branch`, `pr`, `spec`, `deferred-findings`) and cannot tell a spec branch from a code branch. The engine treats a value as a plain string and holds no list of them; the values below are a convention of these workflows.

## Values

| Value | Meaning | Steps |
| --- | --- | --- |
| `spec` | The step writes a spec or workflow design. | `spec-writer`, `design-workflow`, `amend-writer` |
| `feature` | The step writes executable gherkin scenarios. | `feature-writer` |
| `code` | The step writes code, or a change committed as code. | `write-code`, `scope-and-code`, `implement-features`, `audit-engine-pin` |
| `workflow` | The step authors a workflow bundle. | `build-workflow` |
| `guidance` | The step writes or checks guidance entries. | `guidance-writer`, `check-entries` |

Review, CI, merge, feedback, audit-report and script steps author nothing and declare none.

## Adding an authoring step

A new authoring step picks one of the values above, or documents a new one in this table in the same change. Every PR's stages must resolve to exactly one principal output: a workflow whose PR stages declare none, or two that disagree, is refused at load.

A bundle that uses `principal-output:` needs an engine that supports it, so `requires-engine` in `source.toml` is at least the first release that includes it.
