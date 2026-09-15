# Review-scope (you + driver)

`scope-and-code` decided this brief needs more than a single-PR, no-spec lane can carry - too many unrelated call sites, a design decision reasonable people could disagree on, or simply not small. A human reads the note it left and decides where this goes next.

`review-scope` only routes onward on `rescoped` - closing it any other way, or leaving it as the item's only open step, ends the item outright rather than sending it back for another attempt.

1. `lc show STEP` - the `too-big` note explains what turned out bigger than expected and why.
2. Decide:
   - **Rescope and try again** - rewrite the item's own brief (or open a fresh spec/design conversation for the part that needs one) so a future `scope-and-code` pass has a workable brief, then `lc done STEP rescoped` - routes back into `scope-and-code` for another attempt on the same item, keeping its history.
   - **Abandon** - the work should not be built as scoped - `lc done ITEM abandoned`, the item-level close, which also closes this step; do not additionally run the `rescoped` outcome above.
