# Review-ci (you + driver)

CI has failed on this item enough times that write-code kept reworking it without landing a green run. The coder is not converging on its own; a human needs to look at the accumulated failure notes and decide what happens next.

`review-ci` declares exactly one outgoing outcome, `reviewed` - a terminal declaration with no edge target, so the engine now refuses any other string here but still does not treat closing it as a routing decision. Get the ordering right before step 3: closing this step while it is the item's only open one ends the item outright, not just this gate - the terminal declaration stops a typo, not a premature close.

1. `lc show STEP` - the forwarded note carries the latest failing job/test; `lc trace ITEM` shows every prior `ci-failed` note in sequence, so you can see whether it is the same failure repeating or a new one each time.
2. Decide, and put the continuation in place before closing this step:
   - **Re-arm the coder** - `lc new step "<step>: <title>" --parent ITEM --step <step>` - `--step` names the workflow stage, which is what resolves the node's `agent` role, without which the pool can never claim it (or `lc set STEP --state ready` to re-arm an existing well-formed step, which is simpler when one is already there) - once you know what should change, with a note on what to try differently so the next write-code pass does not repeat the same failure.
   - **Fix it by hand and push** to the branch yourself, then re-arm CI-watching the same way: `lc new step "<ci-watch stage>: recheck after hand fix" --parent ITEM --step <ci-watch stage>` - `<ci-watch stage>` is this bundle's `poll-ci`-equivalent (plain `poll-ci` in most bundles; `feature-poll-ci`/`amend-poll-ci` when this gate is `feature-review-ci`/`amend-review-ci`). A push with no open step watching it does not resume anything on its own.
   - **Abandon the item** - `lc done ITEM abandoned`, the item-level close (which also closes this step); do not additionally run step 3 below.
   - **Leave it blocked** for a later look - `lc set STEP --state waiting --needs "<what a human must decide>" --reason "<what happened that led here>"`, then EXIT. Do not proceed to step 3: this step stays open, so there is nothing yet to acknowledge.
3. `lc done STEP reviewed` - only once a re-arm/fix continuation is open, or the item was already closed in step 2. Reviewing it is the acknowledgement.
