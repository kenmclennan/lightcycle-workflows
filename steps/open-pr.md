---
script: scripts/open-pr.py
accepts:
  branch: optional
produces:
  pr: required
  branch: required
detail: [outcome, report, out:pr, out:branch]
---

# Open-PR

An engine-owned script stage: no agent claims it. `scripts/open-pr.py` runs in the phase's worktree, reads the step with `lc show`, and prints one outcome. A push or `gh` failure exits non-zero, which the engine parks. Delivery is at-least-once, so every step below is safe to repeat. The numbering is cited by other steps; step 6 stays the PR-open and body step.

1. Read the step: the closing note QUOTE is `inputs.previous.report` under a heading naming `inputs.previous.stage`. The branch is the worktree's current branch, and OWNER and REPO come from the `origin` remote. The workspace decides which repo the PR opens in, not the item's `repo`.
2. `git fetch origin`, then sync to the remote head: no remote branch, equal heads, or local commits the remote lacks do nothing; otherwise a clean tree is reset to `origin/BRANCH` and the note names LOCAL and REMOTE, and a dirty tree fails naming both SHAs and the dirty paths.
3. Look up an open PR for the branch. If one exists, `git push --force-with-lease`, then resync the text between the `<!-- lc:body -->` and `<!-- /lc:body -->` markers from the commit message and QUOTE, add the `<!-- lc:item=ITEM -->` marker if absent, leave everything outside the markers and a body without markers alone, resync the title to the commit subject, and continue at step 7. If none exists but the phase run already records a `pr`, fail naming the divergence. Otherwise continue.
4. `git rebase origin/main`. On conflict, abort the rebase and print `conflicted` when the stage declares that outcome, otherwise fail naming the conflicting paths.
5. `git push --force-with-lease`. A failure exits non-zero with git's message.
6. Find or open the PR, never a duplicate: look up again, and only if none exists create one against `main` titled with the commit subject exactly. The body is the item marker on its own first line, then the commit message and, when there is a QUOTE, a `## Closing note from <stage>` heading and QUOTE exactly as written, all between the sync markers. If the create call errors, look up again before failing. Then `lc attach ITEM pr URL`; re-attaching the same url on a rework pass is idempotent.
7. Close the loop on queued rework. For each lc acknowledgement carrying `<!-- lc:decision=rework -->` with no reply carrying its `<!-- lc:completes=ID -->` marker and created before the commit time, post one completion reply in its thread. The reply names the pushed SHA and the commit subject and says it does not verify the push addresses the request.
8. Print `{"outcome": "done", "note": ...}`.
