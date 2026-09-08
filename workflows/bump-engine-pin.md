---
summary: checks ENGINE_PIN against lightcycle's main and bumps it via a PR when stale
when-to-use: the nightly engine-pin-stale issue or a failing gate names this repo's ENGINE_PIN as behind lightcycle's main
---

# Bump-engine-pin

One item, one id, one phase, one PR. `audit-engine-pin` reads the currently-deployed `ENGINE_PIN`
out of `.github/workflows/simulate.yml` and compares it to `kenmclennan/lightcycle`'s own `main` via
the GitHub compare API. At or below the configured threshold there is nothing to do - it closes
the item itself (`clean`) with no PR opened. Above threshold it bumps `ENGINE_PIN` to the engine's
current `main` sha, commits, and hands off to the same generic PR/CI machinery every other bundle
here already has: open a PR, watch its own gate run (the very `simulate.yml` this item edits),
human reviews and merges, cleanup closes the item. `audit-engine-pin` is the only stage that carries
this pipeline's own subject matter; everything after it is unmodified reuse.

Filing this workflow is a human act, not something CI can do itself - a GitHub Actions runner has no
path to the local `lc` store. The nightly `simulate.yml` schedule run and the gate's own hard failure
past threshold are what prompt a human to run
`lc new item "bump ENGINE_PIN (<n> commits behind)" --workflow lightcycle/bump-engine-pin --repo <this repo>`;
everything downstream of that is mechanical.

entry: audit-engine-pin

requires: repo

workspace: project

phase:
  audit-engine-pin  bump
  open-pr           bump
  watch-ci          bump
  review-ci         bump
  await-merge       bump
  cleanup           bump
  resolve-conflict  bump
  handle-feedback   bump

display:
  audit-engine-pin  Checking pin
  open-pr           Opening PR
  watch-ci          Watching CI
  review-ci         CI needs a call
  await-merge       Review PR
  cleanup           Tidying up
  resolve-conflict  Resolving conflict
  review-conflict   Resolve conflict
  handle-feedback   Reading feedback

edges:
  audit-engine-pin  stale       open-pr
  open-pr           done        watch-ci          primary
  open-pr           conflicted  resolve-conflict
  watch-ci          done        await-merge       primary
  watch-ci          ci-failed   audit-engine-pin
  await-merge       merged      cleanup
  await-merge       changes     audit-engine-pin
  await-merge       conflicted  resolve-conflict
  await-merge       gave-up     review-conflict
  resolve-conflict  resolved    open-pr           primary
  resolve-conflict  escalate    review-conflict

hooks:
  pr_merge              await-merge  merged
  pr_close              await-merge  abandoned
  pr_feedback           await-merge  handle-feedback
  pr_conflict           await-merge  conflicted
  pr_conflict_cap       await-merge  3
  pr_conflict_escalate  await-merge  gave-up
  ci_failed_cap         watch-ci     ci-failed  3  review-ci
  mention_token         await-merge  @lc
  review_bot_allowlist  await-merge  copilot-pull-request-reviewer[bot]

signals:
  open-pr           conflicts         ~conflict
  watch-ci          resets            ci-failed
  await-merge       resets            changes
  resolve-conflict  resolve_attempts  escalate

disposition:
  merged     completed
  abandoned  aborted
