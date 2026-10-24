---
escalation: true
presents: pr
detail: [pr, in:report, outcome]
---

# Review-ci (you + driver)

The engine routes an item here on one of two caps, and a human opening this step must first tell which fired. `ci_failed_cap` means CI kept failing and the coder stage kept reworking it without landing a green run. `review_rounds_cap` means the CI-watch stage kept closing `review-rework` on new review comments, often with CI green. The coder is not converging on its own either way; decide what happens next.

To tell which cap fired, read the step note or park reason, which names the cap when present. Otherwise `lc trace ITEM` shows whether the run of CI-watch outcomes is `ci-failed` or `review-rework`.

`review-ci` declares exactly one outgoing outcome, `reviewed` - a terminal declaration with no edge target, so the engine refuses any other string here but does not treat closing it as a routing decision. Get the ordering right before step 3: closing this step while it is the item's only open one ends the item outright, not just this gate - the terminal declaration stops a typo, not a premature close.

1. Read the right thing for the cap that fired. For `ci_failed_cap`, read the claim's `inputs.previous.report`, which carries the latest failing job/test, and `lc trace ITEM`, which shows every prior `ci-failed` note in sequence, so you can see whether it is the same failure repeating or a new one each time. For `review_rounds_cap`, read the repeated review comments on the PR and the `review-rework` notes in `lc trace ITEM`, to see whether each round raised a new point or the same one again.
2. Decide, and put the continuation in place before closing this step:
   - **Re-arm the coder** - `lc new step "" --parent ITEM --step <step>` - a step takes no title of its own (it is composed from its stage and the item's title, and a non-empty one is refused), so the positional stays an empty string; `--step` names the workflow stage, which is what resolves the node's `agent` role, without which the pool can never claim it (or `lc set STEP --state ready` to re-arm an existing well-formed step, which is simpler when one is already there) - once you know what should change, with a note on what to try differently so the next coder pass does not repeat the same failure.
   - **Fix it by hand and push** to the branch yourself, then re-arm CI-watching the same way: `lc new step "" --parent ITEM --step <ci-watch stage>` - `<ci-watch stage>` is this bundle's `poll-ci`-equivalent (plain `poll-ci` in most bundles; `feature-poll-ci`/`amend-poll-ci` when this gate is `feature-review-ci`/`amend-review-ci`). A push with no open step watching it does not resume anything on its own.
   - **Let the PR go to merge as is** - only for `review_rounds_cap` with CI green and the remaining comments not worth another round. First reply to each remaining trusted comment on the PR as deferred or will not be fixed: CI-watch re-dispatches any trusted comment left without a reply, so re-arming without the replies sends the item straight back here. Only then re-arm the CI-watch stage as in the previous option (`lc new step "" --parent ITEM --step <ci-watch stage>`), so the item reaches await-merge.
   - **Abandon the item** - `lc done ITEM abandoned`, the item-level close (which also closes this step); do not additionally run step 3 below.
   - **Leave it blocked** for a later look - `lc set STEP --state waiting --needs "<what a human must decide>" --reason "<what happened that led here>"`, then EXIT. Do not proceed to step 3: this step stays open, so there is nothing yet to acknowledge.
3. `lc done STEP reviewed` - only once a re-arm/fix continuation is open, or the item was already closed in step 2. Reviewing it is the acknowledgement.

The `--note` on `lc done` and any `--needs` or `--reason` text you park with are read by a human or the next agent. They follow the standard below.

@include plain-language
