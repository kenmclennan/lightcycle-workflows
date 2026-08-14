---
summary: spec, then frozen gherkin scenarios, then code that makes every scenario pass
when-to-use: behaviour worth pinning as an executable acceptance contract before implementing - the scenarios are frozen and the code is written to satisfy them
---

# BDD-driven

One item, one id, spanning three phases and three review gates. A brief from co-design becomes a
formal spec on a spec PR; once that merges, a feature-writer derives executable gherkin `.feature`
scenarios (tagged `@wip`, gherkin only so nothing collects them yet) on a feature PR that a review-features agent primes for
the human; once that merges, implement-features writes the code and step definitions to make every
scenario pass - implementing to the spec, never editing a scenario, un-`@wip`-ing each as it goes
green - opens a code PR, watches CI, is reviewed, and the human merges. There is no workflow flip:
spec, feature, and code are three positions of one workflow. `open-pr` and `await-merge` each
appear three times (once per PR); the spec phase takes its worktree from the specs repo, the
feature and code phases from the project repo (two distinct phases, same repo). The scenarios are
the frozen executable contract the code must satisfy; the spec is the design intent the code is
reviewed against.

entry: spec-writer

requires: brief repo

workspace:
  spec-writer          specs
  spec-open-pr         specs
  spec-await-merge     specs

phase:
  spec-writer          spec
  spec-open-pr         spec
  spec-await-merge     spec
  feature-writer       feature
  feature-open-pr      feature
  review-features      feature
  feature-await-merge  feature
  implement-features   code
  code-open-pr         code
  watch-ci             code
  review-code          code
  code-await-merge     code
  cleanup              code
  resolve-conflict     code
  review-ci            code
  handle-feedback      code

nodes:
  spec-open-pr         open-pr
  spec-await-merge     await-merge
  feature-open-pr      open-pr
  feature-await-merge  await-merge
  code-open-pr         open-pr
  code-await-merge     await-merge

edges:
  spec-writer          done             spec-open-pr
  spec-open-pr         done             spec-await-merge
  spec-await-merge     changes          spec-writer
  spec-await-merge     spec-merged      feature-writer
  feature-writer       done             feature-open-pr
  feature-open-pr      done             review-features
  review-features      done             feature-await-merge  primary
  review-features      rejected         feature-writer
  feature-await-merge  changes          feature-writer
  feature-await-merge  features-merged  implement-features
  implement-features   done             code-open-pr
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

hooks:
  pr_merge              spec-await-merge     spec-merged
  pr_merge              feature-await-merge  features-merged
  pr_merge              code-await-merge     merged
  pr_close              spec-await-merge     abandoned
  pr_close              feature-await-merge  abandoned
  pr_close              code-await-merge     abandoned
  pr_feedback           spec-await-merge     handle-feedback
  pr_feedback           feature-await-merge  handle-feedback
  pr_feedback           code-await-merge     handle-feedback
  pr_conflict           code-await-merge     conflicted
  pr_conflict_cap       code-await-merge     3
  pr_conflict_escalate  code-await-merge     gave-up
  ci_failed_cap         watch-ci             ci-failed  3  review-ci
  mention_token         spec-await-merge     @lc
  mention_token         feature-await-merge  @lc
  mention_token         code-await-merge     @lc
  review_bot_allowlist  code-await-merge     copilot-pull-request-reviewer[bot]

signals:
  spec-await-merge     resets            changes
  review-features      review_rounds     rejected
  review-features      resets            rejected
  feature-await-merge  resets            changes
  review-code          review_rounds     rejected
  review-code          resets            rejected
  code-open-pr         conflicts         ~conflict
  watch-ci             resets            ci-failed
  code-await-merge     resets            changes
  resolve-conflict     resolve_attempts  escalate
