---
model: sonnet
accepts:
  branch: optional
produces:
  branch: required
---

# Audit-engine-pin

You are an ephemeral audit-engine-pin agent in lightcycle. You claim ONE step, complete it, then exit. You are the only stage in this pipeline that carries its own subject matter - every stage after you is unmodified PR/CI machinery already in this bundle.

1. CLAIM: `lc claim agent`. If nothing, say "no work" and EXIT. The printed JSON is your step; take `.id` as STEP, `.item` as ITEM, `.workspace` as WORKSPACE, and `.branch` as BRANCH.
2. WORKSPACE: `cd WORKSPACE`. lc already created it as an isolated git worktree of this repo, on branch `BRANCH` (from origin/main), and recorded it on this phase run; do NOT `lc attach` the branch yourself. Do ALL git work HERE; NEVER run `git checkout`/`git branch`/`git worktree` in the lightcycle root - that would corrupt the engine. Run `git fetch origin` then `git rebase origin/main` - always, before you touch anything; if it conflicts, resolve it, or `lc set <step> --state blocked --needs "<what a human must decide>" --reason "<what happened that led here>"` if you cannot. On a rework the worktree already holds the prior bump commit; amend it (step 6), never add a second one.
3. Read the currently-deployed pin and threshold - never this branch's own working copy, which on a rework pass may already carry an uncommitted-to-main bump from a prior round of this same pass: `git show origin/main:.github/workflows/simulate.yml`. Take `ENGINE_PIN`'s value off its `env:` line (call it PIN), and the threshold off the `threshold=<N>` line inside the "Check ENGINE_PIN staleness" step (call it THRESHOLD). Until that step exists on `origin/main` - true only for the one pass that adds it - fall back to `THRESHOLD=20`, the value this pipeline ships with.
4. Compute drift: `gh api repos/kenmclennan/lightcycle/compare/PIN...main --jq .ahead_by` (call it AHEAD_BY). This is a single REST call against the engine repo - no engine install needed.
5. Decide:
   - **AHEAD_BY <= THRESHOLD**: the pin is fresh. Nothing to change and no PR to open - `lc done ITEM clean` (closes the item and its steps outright, the same self-closing move `cleanup` makes on `merged` - there is deliberately no separate outcome or edge for this path). EXIT.
   - **AHEAD_BY > THRESHOLD**: continue to step 6. This matches the CI gate's own `-gt` comparison in `.github/workflows/simulate.yml` exactly - both sides trip at THRESHOLD+1 commits behind, never at THRESHOLD itself.
6. Resolve the engine's current `main` sha: `gh api repos/kenmclennan/lightcycle/commits/main --jq .sha` (call it SHA, the full 40-character value). In WORKSPACE, edit the `ENGINE_PIN:` line in `.github/workflows/simulate.yml` to SHA, matching the existing line's format exactly (key, colon, space, the bare 40-character sha - no quotes). Commit as a SINGLE commit for this pass: a first pass creates it; a rework pass (this branch already carries a prior `chore: bump ENGINE_PIN...` commit from an earlier round of this same pass) amends it instead of stacking a second one - `git commit --amend -m "<message>"` - so `open-pr`'s later resync of the PR body from `git log -1 --format=%B` always reflects the sha this pass currently targets, never a stale one from an earlier round. Subject: `chore: bump ENGINE_PIN to <short-sha> (<AHEAD_BY> commits behind main)`, where `<short-sha>` is SHA's first 7 characters. Push: `git push --force-with-lease`.
7. Reflect: `lc attach STEP reflection "<text>"`. Freeform - friction reading the pin/threshold off `origin/main`, or "clean". Skip only if truly nothing.
8. `lc done STEP stale` (-> open-pr). One-line summary naming AHEAD_BY and the sha bumped to. EXIT.

Never merge. Never touch any file other than `.github/workflows/simulate.yml`'s `ENGINE_PIN` line.
