---
summary: brief to merged in one PR - no spec, no separate review stage, for changes too small to justify either
when-to-use: a change small and low-risk enough that a written spec and an agent review round would cost more than they'd ever catch
---

# Small-change

One item, one id, one phase, one PR. `scope-and-code` reads the brief straight off the item's own
description - no spec artifact, no spec PR - decides the approach, and writes the code. `done` when
the change is built; `too-big` when the brief turns out to need more than a single-PR, no-spec lane
can carry, which lands in the human's inbox at `review-scope` rather than being decided by the
agent. From there it is the same generic PR/CI machinery every other bundle here already has: open
a PR, watch CI, human reviews and merges, cleanup closes the item. `scope-and-code` is the only
stage that carries this pipeline's own subject matter; everything after it is unmodified reuse.
There is deliberately no agent code-review stage between `watch-ci` and `await-merge` - the changes
this lane is for should be small and simple enough to review at the PR gate itself, and `too-big` is
the mechanism that keeps them that way.

entry: scope-and-code

requires: repo

workspace: project

phase:
  scope-and-code    change
  open-pr           change
  poll-ci           change
  watch-ci          change
  review-ci         change
  await-merge       change
  cleanup           change
  resolve-conflict  change
  handle-feedback   change
  review-scope      change
  review-conflict   change

display:
  scope-and-code    Coding
  open-pr           Opening PR
  poll-ci           Watching CI
  watch-ci          Reviewing CI result
  review-ci         CI needs a call
  await-merge       Review PR
  cleanup           Tidying up
  resolve-conflict  Resolving conflict
  review-conflict   Resolve conflict
  handle-feedback   Reading feedback
  review-scope      Rescope change

edges:
  scope-and-code    done        open-pr           primary
  scope-and-code    too-big     review-scope
  open-pr           done        poll-ci           primary
  open-pr           conflicted  resolve-conflict
  poll-ci           succeeded   watch-ci
  poll-ci           failed      watch-ci
  watch-ci          done        await-merge       primary
  watch-ci          retried     poll-ci
  watch-ci          ci-failed   scope-and-code
  await-merge       merged      cleanup
  await-merge       changes     scope-and-code
  await-merge       conflicted  resolve-conflict
  await-merge       gave-up     review-conflict
  resolve-conflict  resolved    open-pr           primary
  resolve-conflict  escalate    review-conflict
  review-scope      rescoped    scope-and-code
  review-ci         reviewed
  handle-feedback   done
  review-conflict   resolved    open-pr           primary

hooks:
  pr_merge              await-merge  merged
  pr_close              await-merge  abandoned
  pr_feedback           await-merge  handle-feedback
  pr_conflict           await-merge  conflicted
  pr_conflict_cap       await-merge  3
  pr_conflict_escalate  await-merge  gave-up
  ci_success            poll-ci      succeeded
  ci_failure            poll-ci      failed
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
