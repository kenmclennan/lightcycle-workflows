# Review-ci (you + driver)

CI has failed on this item enough times that write-code kept reworking it without landing a green run. The coder is not converging on its own; a human needs to look at the accumulated failure notes and decide what happens next.

1. `lc show STEP` - the forwarded note carries the latest failing job/test; `lc trace ITEM` shows every prior `ci-failed` note in sequence, so you can see whether it is the same failure repeating or a new one each time.
2. Decide: fix it by hand and push to the branch yourself; leave it blocked; abandon the item; or re-arm the coder - `lc new step "<step>: <title>" --parent ITEM --step <step>` - `--step` names the workflow stage, which is what resolves the node's `agent` role, without which the pool can never claim it (or `lc set STEP --state ready` to re-arm an existing well-formed step, which is simpler when one is already there) once you know what should change, with a note on what to try differently so the next write-code pass does not repeat the same failure.
3. `lc done STEP reviewed` either way - reviewing it is the acknowledgement.
