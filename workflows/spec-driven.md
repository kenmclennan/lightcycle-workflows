---
summary: spec to merged - a co-designed brief becomes a spec PR, then the same item builds the code
when-to-use: the default build flow for a well-scoped feature or fix, spec reviewed before code
---

# Spec-driven

One item, one id, spanning the whole arc: a brief from co-design becomes a formal spec on a spec
PR, and once that PR merges the same item continues into the code build - write the code, open a
code PR, watch CI, review, human merge. There is no workflow flip: the spec phase and the code
phase are two positions of one workflow. `open-pr` and `await-merge` each appear twice (once per
PR); the spec-phase steps take their worktree from the specs repo (`specs-remote`), the code phase
from the project repo. The human review gate is the spec PR itself - no separate inline
draft/review step.

entry: spec-writer

requires: repo
provides: spec

workspace:
  spec-writer               specs
  spec-open-pr              specs
  spec-await-merge          specs
  spec-handle-feedback      specs
  nochange-open-pr          specs
  nochange-await-merge      specs
  nochange-handle-feedback  specs

phase:
  spec-writer               spec
  spec-open-pr              spec
  spec-await-merge          spec
  spec-handle-feedback      spec
  nochange-open-pr          spec
  nochange-await-merge      spec
  nochange-handle-feedback  spec
  write-code                code
  code-open-pr              code
  poll-ci                   code
  watch-ci                  code
  review-code               code
  code-await-merge          code
  cleanup                   code
  resolve-conflict          code
  review-ci                 code
  code-handle-feedback      code
  review-conflict           code

display:
  spec-writer               Writing spec
  spec-open-pr              Opening spec PR
  spec-await-merge          Review spec
  spec-handle-feedback      Reading feedback
  nochange-open-pr          Opening spec PR
  nochange-await-merge      Review spec (no change)
  nochange-handle-feedback  Reading feedback
  write-code                Coding
  code-open-pr              Opening code PR
  poll-ci                   Watching CI
  watch-ci                  Reviewing CI result
  review-code               Reviewing code
  code-await-merge          Review PR
  cleanup                   Tidying up
  resolve-conflict          Resolving conflict
  review-conflict           Resolve conflict
  review-ci                 CI needs a call
  code-handle-feedback      Reading feedback

nodes:
  spec-open-pr              open-pr
  spec-await-merge          await-merge
  spec-handle-feedback      handle-feedback
  nochange-open-pr          open-pr
  nochange-await-merge      await-merge
  nochange-handle-feedback  handle-feedback
  code-open-pr              open-pr
  code-await-merge          await-merge
  code-handle-feedback      handle-feedback

edges:
  spec-writer               done           spec-open-pr
  spec-writer               no-change      nochange-open-pr
  spec-open-pr              done           spec-await-merge
  nochange-open-pr          done           nochange-await-merge
  spec-await-merge          changes        spec-writer
  nochange-await-merge      changes        spec-writer
  nochange-await-merge      head-moved     nochange-await-merge
  spec-await-merge          spec-merged    write-code
  spec-await-merge          head-moved     spec-await-merge
  write-code                done           code-open-pr
  code-open-pr              done           poll-ci           primary
  code-open-pr              conflicted     resolve-conflict
  poll-ci                   succeeded      watch-ci
  poll-ci                   failed         watch-ci
  watch-ci                  done           review-code
  watch-ci                  deferred       review-code
  watch-ci                  retried        poll-ci
  watch-ci                  ci-failed      write-code
  watch-ci                  review-rework  write-code
  review-code               done           code-await-merge  primary
  review-code               rejected       write-code
  code-await-merge          merged         cleanup
  code-await-merge          changes        write-code
  code-await-merge          conflicted     resolve-conflict
  code-await-merge          gave-up        review-conflict
  code-await-merge          head-moved     poll-ci
  resolve-conflict          resolved       code-open-pr      primary
  resolve-conflict          escalate       review-conflict
  review-ci                 reviewed
  spec-handle-feedback      done
  nochange-handle-feedback  done
  code-handle-feedback      done
  review-conflict           resolved       code-open-pr      primary

hooks:
  pr_merge              spec-await-merge      spec-merged
  pr_merge              nochange-await-merge  no-change-merged
  pr_merge              code-await-merge      merged
  pr_close              spec-await-merge      abandoned
  pr_close              nochange-await-merge  abandoned
  pr_close              code-await-merge      abandoned
  pr_feedback           spec-await-merge      spec-handle-feedback
  pr_head_moved         spec-await-merge      head-moved
  pr_feedback           nochange-await-merge  nochange-handle-feedback
  pr_head_moved         nochange-await-merge  head-moved
  pr_feedback           code-await-merge      code-handle-feedback
  pr_conflict           code-await-merge      conflicted
  pr_conflict_cap       code-await-merge      3
  pr_conflict_escalate  code-await-merge      gave-up
  pr_head_moved         code-await-merge      head-moved
  ci_success            poll-ci               succeeded
  ci_failure            poll-ci               failed
  ci_failed_cap         watch-ci              ci-failed      3  review-ci
  review_rounds_cap     watch-ci              review-rework  review-ci
  mention_token         spec-await-merge      @lc
  mention_token         nochange-await-merge  @lc
  mention_token         code-await-merge      @lc

signals:
  spec-await-merge      resets            changes
  nochange-await-merge  resets            changes
  review-code           review_rounds     rejected
  review-code           resets            rejected
  code-open-pr          conflicts         ~conflict
  watch-ci              review_rounds     review-rework
  watch-ci              resets            ci-failed
  watch-ci              resets            review-rework
  code-await-merge      resets            changes
  resolve-conflict      resolve_attempts  escalate

disposition:
  merged            completed
  abandoned         abandoned
  no-change-merged  completed
