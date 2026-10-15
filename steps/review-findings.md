---
escalation: true
---

# Review-findings (you + driver)

An audit step found things worth a human's attention and attached its digest as the `findings` artifact. The audit files nothing and edits nothing; this gate is where a human decides what, if anything, becomes work.

`review-findings` declares three outgoing outcomes, `done`, `filed` and `reviewed`, each a terminal declaration with no edge target. Closing this step while it is the item's only open one ends the item, which is what you want once the findings are dealt with.

1. `lc show STEP` - the forwarded note summarises the findings; the full digest is the `findings` artifact on the audit step (`lc show ITEM` lists it). Read the digest, not only the note.
2. Go through each finding with the human. For one that warrants work, file it yourself (`lc new item`) with the finding's own brief; the audit never does. A finding the human declines needs no action.
3. Close with the outcome that says what happened: `lc done STEP filed` when at least one follow-up item was filed from the findings; `lc done STEP reviewed` when the findings were read and none warranted action; `lc done STEP done` when a finding was handled some other way. All three end the item.

The `--note` on `lc done` and any `--needs` or `--reason` text you park with are read by a human or the next agent. They follow the standard below.

@include plain-language
