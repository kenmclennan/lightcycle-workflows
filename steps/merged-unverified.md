# Merged-unverified (you + driver)

The PR was merged from GitHub while the item still waited at `verify-entries`. Every entry it changed landed on main as it stood at that point: `draft`, which is never delivered. An entry edited from `stable` was reset to `draft` with no `verified` line, so guidance that was live has stopped being delivered. Nothing was verified; the gate was skipped.

1. `lc show STEP`, then open the merged PR (the `.runs` entry whose `pass` matches the step's `.pass` and whose `phase` is this gate's, its `pr` field).
2. Name every entry the merge left `draft` on main: each changed entry file on the merged PR whose `status` is `draft`, read from the merged tree rather than from the PR's earlier commits. Retired entries are `deprecated`, not `draft`, and are not listed. Say which of them were `stable` before this PR, since those stopped being delivered.
3. State the fix to the human: file a follow-up `guidance-entry` item for the listed entries, so a human can verify them and they become `stable` again. List the entry ids in that item's brief.
4. The driver or human files that item. Close the step with `lc done STEP acknowledged`, whose note names the entries left `draft` and the follow-up item. This routes to `cleanup`, since the PR did merge.

Do not edit the merged entries on main from here, and do not mark any entry verified: only a human's per-entry word does that, and it belongs in the follow-up item.

The `--note` on `lc done` and any `--needs` or `--reason` text you park with are read by a human or the next agent. They follow the standard below.

@include plain-language
