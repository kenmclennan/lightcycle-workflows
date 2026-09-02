---
summary: workflow design to merged bundle - a co-designed brief becomes a workflow-design spec PR, then the same item builds and gates the bundle
when-to-use: building or updating a workflow bundle in this origin - a new workflow, an adaptation of an existing one, or a fork
---

# Workflow-authoring

One item, one id, spanning the whole arc: a brief from co-design becomes a formal workflow-design spec on a spec PR - a mermaid flowchart of the intended graph plus a description of each step, gate, and trigger - and once that PR merges the same item continues into the code build: author the bundle, open a code PR, watch CI, review, human merge. There is no workflow flip: the spec phase and the code phase are two positions of one workflow. `design-workflow`, `build-workflow`, and `review-workflow` carry the workflow-authoring craft (the design mermaid convention and grammar, the full grammar and hook catalog, the QA and agnostic-rule checklist) inline, so this bundle works from being pulled alone - no plugin, no target repo `CLAUDE.md`, no engine source. `open-pr` and `await-merge` each appear twice (once per PR) and stay generic PR/CI machinery, reused unchanged; the spec-phase steps take their worktree from the specs repo, the code phase from the target workflow-origin repo. The human review gate is the spec PR itself for the design, and the code PR - gated by `lc workflow check` and `lc workflow simulate`, never a test suite - for the bundle.

entry: design-workflow

requires: repo

workspace:
  design-workflow   specs
  spec-open-pr      specs
  spec-await-merge  specs

phase:
  design-workflow   spec
  spec-open-pr      spec
  spec-await-merge  spec
  build-workflow    code
  code-open-pr      code
  watch-ci          code
  review-workflow   code
  code-await-merge  code
  cleanup           code
  resolve-conflict  code
  review-ci         code
  handle-feedback   code

display:
  design-workflow   Designing workflow
  spec-open-pr      Opening spec PR
  spec-await-merge  Review the spec
  build-workflow    Building workflow
  code-open-pr      Opening code PR
  watch-ci          Watching CI
  review-workflow   Checking workflow
  code-await-merge  Review the PR
  cleanup           Tidying up
  resolve-conflict  Resolving conflict
  review-conflict   Resolve conflict
  review-ci         CI needs a call
  handle-feedback   Reading feedback

nodes:
  spec-open-pr      open-pr
  spec-await-merge  await-merge
  code-open-pr      open-pr
  code-await-merge  await-merge

edges:
  design-workflow   done         spec-open-pr
  spec-open-pr      done         spec-await-merge
  spec-await-merge  changes      design-workflow
  spec-await-merge  spec-merged  build-workflow
  build-workflow    done         code-open-pr
  code-open-pr      done         watch-ci          primary
  code-open-pr      conflicted   resolve-conflict
  watch-ci          done         review-workflow
  watch-ci          ci-failed    build-workflow
  review-workflow   done         code-await-merge  primary
  review-workflow   rejected     build-workflow
  code-await-merge  merged       cleanup
  code-await-merge  changes      build-workflow
  code-await-merge  conflicted   resolve-conflict
  code-await-merge  gave-up      review-conflict
  resolve-conflict  resolved     code-open-pr      primary
  resolve-conflict  escalate     review-conflict

hooks:
  pr_merge              spec-await-merge  spec-merged
  pr_merge              code-await-merge  merged
  pr_close              spec-await-merge  abandoned
  pr_close              code-await-merge  abandoned
  pr_feedback           spec-await-merge  handle-feedback
  pr_feedback           code-await-merge  handle-feedback
  pr_conflict           code-await-merge  conflicted
  pr_conflict_cap       code-await-merge  3
  pr_conflict_escalate  code-await-merge  gave-up
  ci_failed_cap         watch-ci          ci-failed  3  review-ci
  mention_token         spec-await-merge  @lc
  mention_token         code-await-merge  @lc
  review_bot_allowlist  code-await-merge  copilot-pull-request-reviewer[bot]

signals:
  spec-await-merge  resets            changes
  review-workflow   review_rounds     rejected
  review-workflow   resets            rejected
  code-open-pr      conflicts         ~conflict
  watch-ci          resets            ci-failed
  code-await-merge  resets            changes
  resolve-conflict  resolve_attempts  escalate
