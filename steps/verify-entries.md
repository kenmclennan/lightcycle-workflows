# Verify-entries (you + driver)

The guidance entries on this PR have passed the mechanical check and are all `draft` or `deprecated`. Only a human may make an entry deliverable: `status: stable` plus a `verified` record is the one state a worker is ever given, and it rests on a human's word. You read the PR and decide, entry by entry, whether each is right.

1. `lc show STEP`, then open the PR (the `.runs` entry whose `pass` matches the step's `.pass` and whose `phase` is this gate's, its `pr` field) and read every changed entry. The item's `finding` artifact says why they exist.
2. Decide, per entry. The human states it in conversation with the driver or in a PR comment; the driver acts only on an explicit per-entry word, never infers verification from a general approval of the PR, and never verifies an entry the human did not name.
3. On that word, the driver edits each named entry on the PR branch (from the item's worktree, `git fetch origin` first): `status: stable` and `verified: <the human's name> <date>`, the format the repo's existing stable entries use. Commit them together as one commit, stage by explicit path, and push to the PR branch. The human may instead hand-edit the front matter, commit and push themselves; the check reads only the branch, so both routes are the same to it.
4. Close the step with one of:
   - `lc done STEP verified` - at least one entry was marked stable, by either route. The note names the entries the human verified, so the audit trail shows whose word each `verified` record rests on. Routes to `check-entries`.
   - `lc done STEP left-draft` - the human accepts the PR but verifies nothing. The entries merge as `draft`, which is inert: `draft` is never delivered, and a later item on this workflow can verify them. Routes to `check-entries`.
   - `lc done STEP changes` - the entries need rework; the note says what, and goes to `guidance-writer`.
   - Closing the PR unmerged ends the item as abandoned and is the way to drop the work entirely: `lc done ITEM abandoned`, the item-level close, which also closes this step.

Both `verified` and `left-draft` run the final check before the PR can merge, so a front-matter edit that left a `stable` entry without a `verified` record is caught like any other.

The `--note` on `lc done` and any `--needs` or `--reason` text you park with are read by a human or the next agent. They follow the standard below.

@include plain-language
