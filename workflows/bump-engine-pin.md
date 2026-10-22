---
summary: checks the repo's engine pin against the engine's main and bumps it via a PR when stale
when-to-use: the repo's staleness report or a failing gate names its engine pin as behind the engine's main
---

# Bump-engine-pin

One item, one id, one phase, one PR. `audit-engine-pin` reads the repo's currently-deployed engine
pin and staleness threshold off `origin/main` - the repo's `CLAUDE.md` `## Engine pin` section says
where they live - and compares the pin to the engine repo's own `main` via the GitHub compare API.
At or below the configured threshold there is nothing to do - it closes the item itself (`clean`)
with no PR opened. Above threshold it bumps the pin to the engine's current `main` sha, commits, and
hands off to the same generic PR/CI machinery every other bundle here already has: open a PR, watch
its own gate run (the very CI workflow this item edits), human reviews and merges, cleanup closes
the item. `audit-engine-pin` is the only stage that carries
this pipeline's own subject matter; everything after it is unmodified reuse.

Filing this workflow is a human act, not something CI can do itself - a CI runner has no path to
the local `lc` store. The repo's scheduled CI run and the gate's own hard failure past threshold are
what prompt a human to run
`lc new item "bump the engine pin (<n> commits behind)" --workflow lightcycle/bump-engine-pin --repo <this repo>`;
everything downstream of that is mechanical.

entry: audit-engine-pin

requires: repo

workspace: project

workspace:
  open-pr  project
  cleanup  project

phase:
  audit-engine-pin  bump
  open-pr           bump
  poll-ci           bump
  watch-ci          bump
  review-ci         bump
  await-merge       bump
  cleanup           bump
  resolve-conflict  bump
  handle-feedback   bump
  review-conflict   bump

display:
  audit-engine-pin  Checking pin
  open-pr           Opening PR
  poll-ci           Watching CI
  watch-ci          Reviewing CI result
  review-ci         CI needs a call
  await-merge       Review PR
  cleanup           Tidying up
  resolve-conflict  Resolving conflict
  review-conflict   Resolve conflict
  handle-feedback   Reading feedback

edges:
  audit-engine-pin  stale          open-pr
  audit-engine-pin  clean
  open-pr           done           poll-ci           primary
  open-pr           conflicted     resolve-conflict
  poll-ci           succeeded      watch-ci
  poll-ci           failed         watch-ci
  poll-ci           conflicted     resolve-conflict
  watch-ci          done           await-merge       primary
  watch-ci          deferred       await-merge
  watch-ci          retried        poll-ci
  watch-ci          ci-failed      audit-engine-pin
  watch-ci          review-rework  audit-engine-pin
  watch-ci          conflicted     resolve-conflict
  await-merge       merged         cleanup
  cleanup           done
  await-merge       changes        audit-engine-pin
  await-merge       conflicted     resolve-conflict
  await-merge       gave-up        review-conflict
  await-merge       head-moved     poll-ci
  resolve-conflict  resolved       open-pr           primary
  resolve-conflict  escalate       review-conflict
  review-ci         reviewed
  handle-feedback   done
  review-conflict   resolved       open-pr           primary

hooks:
  pr_merge              await-merge  merged
  pr_close              await-merge  abandoned
  pr_feedback           await-merge  handle-feedback
  pr_conflict           await-merge  conflicted
  pr_conflict_cap       await-merge  3
  pr_conflict_escalate  await-merge  gave-up
  pr_head_moved         await-merge  head-moved
  pr_conflict           poll-ci      conflicted
  pr_conflict           watch-ci     conflicted
  ci_success            poll-ci      succeeded
  ci_failure            poll-ci      failed
  ci_failed_cap         watch-ci     ci-failed  3  review-ci
  review_rounds_cap     watch-ci     review-rework  review-ci
  mention_token         await-merge  @lc

signals:
  open-pr           conflicts         ~conflict
  watch-ci          review_rounds     review-rework
  watch-ci          resets            ci-failed
  watch-ci          resets            review-rework
  await-merge       resets            changes
  resolve-conflict  resolve_attempts  escalate

disposition:
  clean      completed
  merged     completed
  abandoned  abandoned
