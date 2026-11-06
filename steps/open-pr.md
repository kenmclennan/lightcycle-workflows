---
script: scripts/open-pr.py
accepts:
  branch: optional
  delivery: optional
produces:
  pr: required
  branch: required
detail: [outcome, report, out:pr, out:branch]
---

# Open-PR

An engine-owned script stage: no agent claims it. `scripts/open-pr.py` runs in the phase's worktree, reads the step with `lc show`, and prints one outcome. A push or `gh` failure exits non-zero, which the engine parks. Delivery is at-least-once, so every step below is safe to repeat. The numbering is cited by other steps; step 6 stays the PR-open and body step.

1. Read the step: the closing note QUOTE is `inputs.previous.report` under a heading naming `inputs.previous.stage`. The branch is the worktree's current branch, and OWNER and REPO come from the `origin` remote. The workspace decides which repo the PR opens in, not the item's `repo`.
2. `git fetch origin`, then sync to the remote head: no remote branch, equal heads, or local commits the remote lacks do nothing; otherwise a clean tree is reset to `origin/BRANCH` and the note names LOCAL and REMOTE, and a dirty tree fails naming both SHAs and the dirty paths.
   - **Stack fork.** If the worktree holds a stack (`gh stack view --json` lists two or more branches, the last being BRANCH), steps 3 to 6 are replaced: `gh stack rebase` in place of step 4's rebase, with a conflict aborted and printed as `conflicted`; then, when the run already records a `stack` and the stack on GitHub (read through `gh api`) has a different branch set from the local layers, a re-cut: `gh stack unstack <n>` and `gh stack init <local layers bottom to top>` first, then `gh stack submit --auto --open`, then close each PR whose head is no longer a layer with the comment `Layer dropped by a re-cut; see <top PR url>`, delete its branch, and attach the new stack and top PR with `--replace`; a dissolved or unchanged stack skips that and submits as normal. The submit pushes and opens a PR per layer; then `lc attach ITEM stack STACK_URL` and `lc attach ITEM pr TOP_URL`. Each layer's PR body is the item marker, then between the sync markers that layer's tip commit message and a `## Delivery` section quoting its `Layer <n>` line from the item's `delivery` entry; the top layer's body also carries the `Decision` and `Reasons` lines and the QUOTE. Titles are each layer's tip commit subject. Exit code 9 from `gh stack` (stacks not enabled for the repo) falls back to one PR from BRANCH with steps 3 to 6 as written, its body noting that stacks are not enabled and carrying the `delivery` reasons, and no `stack` attached; any other non-zero exit fails the stage. Steps 7 and 8 then follow. A worktree with no stack never takes this fork.
3. Look up an open PR for the branch. If one exists, `git push --force-with-lease`, then resync the text between the `<!-- lc:body -->` and `<!-- /lc:body -->` markers from the commit message and QUOTE, add the `<!-- lc:item=ITEM -->` marker if absent, leave everything outside the markers and a body without markers alone, resync the title to the commit subject, and continue at step 7. If none exists but the phase run already records a `pr`, fail naming the divergence. Otherwise continue.
4. Resolve BASE_REF: `git remote set-head origin --auto`, then `git symbolic-ref --short refs/remotes/origin/HEAD`, which prints `origin/<the repo's default branch>`; a failure to resolve it fails the stage naming git's output and never falls back to a literal branch name. Then `git rebase BASE_REF`. On conflict, abort the rebase and print `conflicted` when the stage declares that outcome, otherwise fail naming the conflicting paths.
5. `git push --force-with-lease`. A failure exits non-zero with git's message.
6. Find or open the PR, never a duplicate: look up again, and only if none exists create one against the repo's default branch (BASE_REF without its `origin/` prefix) titled with the commit subject exactly. The body is the item marker on its own first line, then the commit message and, when there is a QUOTE, a `## Closing note from <stage>` heading and QUOTE exactly as written, all between the sync markers. If the create call errors, look up again before failing. Then `lc attach ITEM pr URL`; re-attaching the same url on a rework pass is idempotent.
7. Close the loop on queued rework. For each lc acknowledgement carrying `<!-- lc:decision=rework -->` with no reply carrying its `<!-- lc:completes=ID -->` marker and created before the commit time, post one completion reply in its thread. The reply names the pushed SHA and the commit subject and says it does not verify the push addresses the request.
8. Print `{"outcome": "done", "note": ...}`.
