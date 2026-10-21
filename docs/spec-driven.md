# spec-driven

**One item, one id, from brief to merged code, through two PRs.** A brief settled in co-design becomes a formal spec on a spec PR; once that merges, the same item continues into the code build. The spec PR is the single human review gate before code; the code PR is the merge gate.

**Use it when** the design is best captured as a prose spec that a human reviews and merges before any code is written.

**Phases:** `spec` (specs repo) then `code` (project repo). `open-pr` and `await-merge` appear once per phase.

The graph is `workflows/spec-driven.md`; the step prompts are in `steps/*.md`.

## Flow

Node shape shows who runs each stage: `[ agent-step ]` an ephemeral agent claims and completes it; `{{ human-gate }}` a human decides (the driver assists); `([ start / terminal ])` the item's inputs or where the flow ends. Edge labels are outcomes; edges back to an earlier stage are rework loops. Merge, CI-failure, and conflict transitions are driven by engine hooks watching the PR - folded into the labelled edges here; exact wiring is in the graph file.

```mermaid
flowchart TD
    brief(["brief + repo"]) --> SW["spec-writer"]
    subgraph S ["spec phase (specs repo)"]
        SW --> SD["spec-digest"] --> SOP["spec-open-pr"] --> SAM{{"spec-await-merge"}}
        SAM -->|changes| SW
    end
    SAM -->|spec-merged| WC["write-code"]
    subgraph C ["code phase (project repo)"]
        WC --> COP["code-open-pr"] --> WCI["watch-ci"] --> RC["review-code"]
        WCI -->|ci-failed| WC
        WCI -->|review-rework| WC
        WCI -.->|"ci_failed_cap: ci-failed"| RCI{{"review-ci"}}
        WCI -.->|"review_rounds_cap: review-rework"| RCI
        RC -->|rejected| WC
        RC -->|done| CAM{{"code-await-merge"}}
        CAM -->|changes| WC
        COP -->|conflicted| RCF["resolve-conflict"]
        CAM -->|conflicted| RCF
        RCF -->|resolved| COP
        CAM -->|merged| CU(["cleanup"])
    end
    RCF -->|escalate| RCON{{"review-conflict"}}
    CAM -->|gave-up| RCON
    RCON -->|resolved| COP
```

## Steps

| Step | Who | Does |
| --- | --- | --- |
| `spec-writer` | agent | Formalizes the brief into a spec on a branch in the specs repo. |
| `spec-digest` | agent | Writes a short plain-language digest of the spec beside it, for the human at the spec gate. |
| `spec-open-pr` / `spec-await-merge` | script / human | Opens the spec PR; the human reviews and merges it (the review gate). |
| `nochange-open-pr` / `nochange-await-merge` | script / human | The spec PR's second gate: `spec-writer` closes `no-change` when the spec concludes nothing should change. Merging that PR completes the item with no code phase. |
| `write-code` | agent | Implements the spec so every acceptance check passes. |
| `code-open-pr` | script | Rebases on main, pushes, opens the code PR. |
| `watch-ci` | agent | Watches CI; routes failing CI and correct review comments back to `write-code` (each capped, then `review-ci`). |
| `review-code` | agent | Reviews the diff against the spec and primes the human gate; bounces back on defects. |
| `code-await-merge` | human | Merges the code PR, or routes changes/feedback back. |
| `resolve-conflict` / `review-conflict` | agent / human | Handle a PR that hits a merge conflict (escalating to a human past the cap), who resolves it by hand and re-enters the PR/CI cycle, or abandons the item. |
| `cleanup` | script, terminal | The item is merged and done. |
