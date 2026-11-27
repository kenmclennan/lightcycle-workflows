---
escalation: true
presents: in:report
detail: [in:report, outcome]
---

# Review-not-needed (you + driver)

`scope-and-code` read the brief against the base branch and found its premise false - the bug does not reproduce, the branch is already reachable, the change is already present - so it claims nothing is owed. A human reads the note it left (the `in:report` row in the Detail tab, the previous step's closing report) and decides whether the evidence holds.

`review-not-needed` closes the item with nothing delivered on `confirmed`, and returns it to `scope-and-code` on `sent-back`.

1. Read the claim's `inputs.previous.report` - the `not-needed` note names the code path or command that shows nothing is owed, and what it returned.
2. Run that path or command on the base branch yourself. A note that names no runnable evidence is not enough to confirm.
3. Decide:
   - **Confirm** - the evidence shows nothing is owed - `lc done STEP confirmed`. The item closes with nothing delivered.
   - **Send back** - the evidence is missing, wrong, or the premise still holds - say why in `--note`, then `lc done STEP sent-back`. The item returns to `scope-and-code` for another attempt, keeping its history.
