---
summary: spec, then frozen gherkin scenarios, then code that makes every scenario pass
when-to-use: behaviour worth pinning as an executable acceptance contract before implementing - the scenarios are frozen and the code is written to satisfy them
---

# BDD-driven

One item, one id, spanning three phases and three review gates, plus a fourth phase entered only
when needed. A brief from co-design becomes a formal spec on a spec PR; once that merges, a
feature-writer derives executable gherkin `.feature` scenarios (tagged `@wip`, gherkin only so
nothing collects them yet) on a feature PR that a review-features agent primes for the human; once
that merges, implement-features writes the code and step definitions to make every scenario pass -
implementing to the spec, un-`@wip`-ing each scenario as it goes green - opens a code PR, watches
CI, is reviewed, and the human merges. Implement-features may never edit a scenario itself; if one
is wrong and a human has authorized the fix on the code PR's own comment thread, it hands off to
the `amend` phase instead, which rewrites the named scenario(s) on their own PR and, once merged,
hands back to implement-features on its next rebase. Absent that authorization a wrong scenario
still blocks for a human, exactly as before. There is no workflow flip: spec, feature, code, and
amend are positions of one workflow. `open-pr` and `await-merge` each appear three times
unconditionally (once per PR) plus a fourth time whenever `amend` runs; the spec phase takes its
worktree from the specs repo, the feature, code, and amend phases from the project repo (three
distinct phases, same repo). The scenarios are the frozen executable contract the code must
satisfy - `amend` is the sole, authorization-gated route to changing that contract after it merges;
the spec is the design intent the code is reviewed against.

entry: spec-writer

requires: repo
provides: spec

workspace:
  spec-writer           specs
  spec-open-pr          specs
  spec-await-merge      specs
  spec-handle-feedback  specs

phase:
  spec-writer              spec
  spec-open-pr             spec
  spec-await-merge         spec
  spec-handle-feedback     spec
  feature-writer           feature
  feature-open-pr          feature
  feature-watch-ci         feature
  review-features          feature
  feature-await-merge      feature
  feature-review-ci        feature
  feature-handle-feedback  feature
  implement-features       code
  code-open-pr             code
  watch-ci                 code
  review-code              code
  code-await-merge         code
  cleanup                  code
  resolve-conflict         code
  review-ci                code
  code-handle-feedback     code
  amend-writer             amend
  amend-open-pr            amend
  amend-watch-ci           amend
  amend-await-merge        amend
  amend-review-ci          amend
  amend-handle-feedback    amend

display:
  spec-writer              Writing spec
  spec-open-pr             Opening spec PR
  spec-await-merge         Review spec
  spec-handle-feedback     Reading feedback
  feature-writer           Writing scenarios
  feature-open-pr          Opening feature PR
  feature-watch-ci         Watching CI (scenarios)
  review-features          Checking scenarios
  feature-await-merge      Review scenarios
  feature-review-ci        CI needs a call (scenarios)
  feature-handle-feedback  Reading feedback
  implement-features       Coding
  code-open-pr             Opening code PR
  watch-ci                 Watching CI
  review-code              Reviewing code
  code-await-merge         Review PR
  cleanup                  Tidying up
  resolve-conflict         Resolving conflict
  review-conflict          Resolve conflict
  review-ci                CI needs a call
  code-handle-feedback     Reading feedback
  amend-writer             Amending scenario
  amend-open-pr            Opening scenario-amendment PR
  amend-watch-ci           Watching CI (scenario amendment)
  amend-await-merge        Review scenario amendment
  amend-review-ci          CI needs a call (scenario amendment)
  amend-handle-feedback    Reading feedback (scenario amendment)

nodes:
  spec-open-pr             open-pr
  spec-await-merge         await-merge
  spec-handle-feedback     handle-feedback
  feature-open-pr          open-pr
  feature-watch-ci         watch-ci
  feature-await-merge      await-merge
  feature-review-ci        review-ci
  feature-handle-feedback  handle-feedback
  code-open-pr             open-pr
  code-await-merge         await-merge
  code-handle-feedback     handle-feedback
  amend-open-pr            open-pr
  amend-watch-ci           watch-ci
  amend-await-merge        await-merge
  amend-review-ci          review-ci
  amend-handle-feedback    handle-feedback

edges:
  spec-writer          done             spec-open-pr
  spec-open-pr         done             spec-await-merge
  spec-await-merge     changes          spec-writer
  spec-await-merge     spec-merged      feature-writer
  feature-writer       done             feature-open-pr
  feature-open-pr      done             feature-watch-ci     primary
  feature-watch-ci     done             review-features
  feature-watch-ci     ci-failed        feature-writer
  review-features      done             feature-await-merge  primary
  review-features      rejected         feature-writer
  feature-await-merge  changes          feature-writer
  feature-await-merge  features-merged  implement-features
  implement-features   done             code-open-pr
  implement-features   scenario-conflict  amend-writer
  code-open-pr         done             watch-ci             primary
  code-open-pr         conflicted       resolve-conflict
  watch-ci             done             review-code
  watch-ci             ci-failed        implement-features
  review-code          done             code-await-merge     primary
  review-code          rejected         implement-features
  code-await-merge     merged           cleanup
  code-await-merge     changes          implement-features
  code-await-merge     conflicted       resolve-conflict
  code-await-merge     gave-up          review-conflict
  resolve-conflict     resolved         code-open-pr         primary
  resolve-conflict     escalate         review-conflict
  amend-writer         done             amend-open-pr
  amend-open-pr        done             amend-watch-ci       primary
  amend-watch-ci       done             amend-await-merge    primary
  amend-watch-ci       ci-failed        amend-writer
  amend-await-merge    changes          amend-writer
  amend-await-merge    scenario-merged  implement-features

hooks:
  pr_merge              spec-await-merge     spec-merged
  pr_merge              feature-await-merge  features-merged
  pr_merge              code-await-merge     merged
  pr_close              spec-await-merge     abandoned
  pr_close              feature-await-merge  abandoned
  pr_close              code-await-merge     abandoned
  pr_feedback           spec-await-merge     spec-handle-feedback
  pr_feedback           feature-await-merge  feature-handle-feedback
  pr_feedback           code-await-merge     code-handle-feedback
  pr_conflict           code-await-merge     conflicted
  pr_conflict_cap       code-await-merge     3
  pr_conflict_escalate  code-await-merge     gave-up
  ci_failed_cap         watch-ci             ci-failed  3  review-ci
  ci_failed_cap         feature-watch-ci     ci-failed  3  feature-review-ci
  mention_token         spec-await-merge     @lc
  mention_token         feature-await-merge  @lc
  mention_token         code-await-merge     @lc
  review_bot_allowlist  code-await-merge     copilot-pull-request-reviewer[bot]
  pr_merge              amend-await-merge    scenario-merged
  pr_close              amend-await-merge    abandoned
  pr_feedback           amend-await-merge    amend-handle-feedback
  ci_failed_cap         amend-watch-ci       ci-failed  3  amend-review-ci
  mention_token         amend-await-merge    @lc
  review_bot_allowlist  amend-await-merge    copilot-pull-request-reviewer[bot]

signals:
  spec-await-merge     resets            changes
  review-features      review_rounds     rejected
  review-features      resets            rejected
  feature-await-merge  resets            changes
  feature-watch-ci     resets            ci-failed
  review-code          review_rounds     rejected
  review-code          resets            rejected
  code-open-pr         conflicts         ~conflict
  watch-ci             resets            ci-failed
  code-await-merge     resets            changes
  resolve-conflict     resolve_attempts  escalate
  amend-await-merge    resets            changes
  amend-watch-ci       resets            ci-failed

disposition:
  merged     completed
  abandoned  aborted
