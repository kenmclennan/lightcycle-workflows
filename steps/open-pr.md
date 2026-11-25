---
script: scripts/open-pr.py
accepts:
  branch: optional
  feedback-decision: optional
  feedback-completed: optional
produces:
  pr: required
  branch: required
  feedback-completed: optional
detail: [outcome, report, out:pr, out:branch]
---

# Open-PR

An engine-owned script stage: no agent claims it. `scripts/open-pr.py` runs in the phase's worktree, reads the step with `lc show`, and prints one outcome. A push or `gh` failure exits non-zero, which the engine parks. Delivery is at-least-once, so every step below is safe to repeat. The numbering is cited by other steps; step 6 stays the PR-open and body step.

1. Read the step: its `phase` decides the body form (see step 6), and `inputs.previous.report` is the closing note QUOTE, used only on a phase other than `code` or `change`. The branch is the worktree's current branch, and OWNER and REPO come from the `origin` remote. The workspace decides which repo the PR opens in, not the item's `repo`.
2. `git fetch origin`, then sync to the remote head: no remote branch, equal heads, or local commits the remote lacks do nothing; otherwise a clean tree is reset to `origin/BRANCH` and the note names LOCAL and REMOTE, and a dirty tree fails naming both SHAs and the dirty paths.
3. Look up an open PR for the branch. If one exists, `git push --force-with-lease`, then resync the text between the `<!-- lc:body -->` and `<!-- /lc:body -->` markers from the commit message (and QUOTE on a phase other than `code` or `change`), add the `<!-- lc:item=ITEM -->` marker if absent, leave everything outside the markers and a body without markers alone, resync the title to the commit subject, and continue at step 7. If none exists but the phase run already records a `pr`, fail naming the divergence. Otherwise continue.
4. Resolve BASE_REF: `git remote set-head origin --auto`, then `git symbolic-ref --short refs/remotes/origin/HEAD`, which prints `origin/<the repo's default branch>`; a failure to resolve it fails the stage naming git's output and never falls back to a literal branch name. Then `git rebase BASE_REF`. On conflict, abort the rebase and print `conflicted` when the stage declares that outcome, otherwise fail naming the conflicting paths.
5. `git push --force-with-lease`. A failure exits non-zero with git's message.
6. Find or open the PR, never a duplicate: look up again, and only if none exists create one against the repo's default branch (BASE_REF without its `origin/` prefix) titled with the commit subject exactly. The body is the item marker on its own first line, then the commit message, all between the sync markers. On a `code` or `change` phase the commit message is all the body carries: no closing note, a commit-body line `Also found, out of scope:` shows as `Follow-ups noticed:` (the commit itself keeps its label), a `Tested:` or `Not tested here:` block is dropped, and a `Check by hand:` line passes through. Before anything is pushed or posted, that body is scanned for the words `spec`, `specs`, `driver`, `finding`, `findings`, `carve-out`, `routed` and the name in `inputs.previous.stage` (case-insensitive, whole words, a hyphen counts as part of a word); a hit fails the stage naming each word and its line. Any other phase keeps the commit message followed, when there is a QUOTE, by a `## Closing note from <stage>` heading and QUOTE exactly as written. If the create call errors, look up again before failing. Then `lc attach ITEM pr URL`; re-attaching the same url on a rework pass is idempotent.
7. Close the loop on queued rework from the item's records, read from the entries of `inputs.item` named `feedback-decision` and `feedback-completed` (each has a `label` and a `value`; the newest per label counts). A `feedback-decision` whose JSON `decision` is `rework`, with no `feedback-completed` under its label and a `sha` different from the current HEAD, is complete. For an `inline` key whose thread root was written by the authenticated GitHub login, post one reply in the thread, then resolve the thread; for an `inline` key with any other, unreadable or unfound root or login, post one top-level comment linking the request and resolve nothing. A `review` or `mention` key posts no comment. A reply is `🤖 <!-- lc -->` then `Done in <7-char sha>: <commit subject>.`, and is skipped when the authenticated login already posted `Done in <sha>` there. React `+1` on the request, then last `lc attach ITEM feedback-completed --label KEY HEAD_SHA`. A failed reaction or resolve goes in the note and never fails the stage.
8. Print `{"outcome": "done", "note": ...}`.
