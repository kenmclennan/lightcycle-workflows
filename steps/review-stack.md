---
escalation: true
accepts:
  pr: required
produces:
  pr: optional
presents: pr
detail: [pr, stack, in:report, outcome]
---

# Review-stack (you + driver)

The engine saw the PR stack take a shape the flow did not plan for - for example a layer closed unmerged - and stopped here rather than guess. A human decides what the stack should become.

`review-stack` only routes onward on `reopen`, `fold` or `drop` - closing it any other way, or leaving it as the item's only open step, ends the item outright rather than re-entering the PR/CI cycle.

1. Read the claim's `inputs.previous.report`: the engine's description of the difference between the stack as recorded and the stack on GitHub. Look at the stack as GitHub shows it before choosing.
2. Decide:
   - **Reopen** - the closed layer should stand. Reopen it (`gh pr reopen <layer>`), then `lc done STEP reopen` - routes to `poll-ci`, which reads CI on every layer's head.
   - **Fold** - the closed layer's commits belong in its upper neighbour. `lc done STEP fold --note "Re-cut: <which layer folds into which, and why>"` - routes to `cut-delivery`, which cuts the stack again.
   - **Drop** - the layer should go and the layers above restack onto its base. `lc done STEP drop --note "Layer dropped: <n> - <why>"` - routes to the coder, which restacks and pushes with a lease.
   - **Leave it blocked** for a later look - `lc set STEP --state waiting --needs "<what a human must decide>" --reason "<what happened that led here>"`, then EXIT.

The `--note` on `lc done` and any `--needs` or `--reason` text you park with are read by a human or the next agent. They follow the standard below.

@include plain-language
