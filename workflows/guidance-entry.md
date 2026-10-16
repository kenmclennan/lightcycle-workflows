---
summary: a finding to merged guidance entries in one PR - written, mechanically checked, then merged
when-to-use: any change to the guidance repo - a new entry, an edit, or retiring one - so every entry has an item, a recorded finding, and a reviewed PR before it is delivered
---

# Guidance-entry

One item, one id, one phase, one PR, for items whose repo is the guidance repo. `guidance-writer` reads the brief (the finding and what the human and driver agreed), writes, edits or retires entries (new and edited entries are `status: stable`; retiring sets `status: deprecated`, never deletes the file), and records where the finding came from. `check-entries` then runs a mechanical conventions check over every changed entry before any human sees the PR: front matter, `type: Guidance`, an inline `applies-to` list, a concept page for every facet, and steps in a valid form; a non-empty `purpose`, `when` and `why`, and no item id. `open-pr` opens an ordinary PR, and the human merges it through the generic await-merge machinery: merging is the approval, and a stable entry is delivered once it is on main. The guidance repo has no CI, so there are no CI stages: `open-pr` goes straight to the gate. A rework round returns to `guidance-writer` and re-runs the check; a push to the branch while the PR waits re-runs the check too.

entry: guidance-writer

requires: repo

workspace: project

phase:
  guidance-writer   entry
  check-entries     entry
  open-pr           entry
  await-merge       entry
  cleanup           entry
  handle-feedback   entry
  resolve-conflict  entry
  review-conflict   entry

display:
  guidance-writer   Writing entries
  check-entries     Checking entries
  open-pr           Opening PR
  await-merge       Review PR
  cleanup           Tidying up
  handle-feedback   Reading feedback
  resolve-conflict  Resolving conflict
  review-conflict   Resolve conflict

edges:
  guidance-writer   done           check-entries     primary
  check-entries     clean          open-pr           primary
  check-entries     broken         guidance-writer
  open-pr           done           await-merge       primary
  open-pr           conflicted     resolve-conflict
  await-merge       merged         cleanup           primary
  await-merge       changes        guidance-writer
  await-merge       conflicted     resolve-conflict
  await-merge       gave-up        review-conflict
  await-merge       head-moved     check-entries
  resolve-conflict  resolved       open-pr           primary
  resolve-conflict  escalate       review-conflict
  handle-feedback   done
  review-conflict   resolved       open-pr           primary

hooks:
  pr_merge              await-merge     merged
  pr_close              await-merge     abandoned
  pr_feedback           await-merge     handle-feedback
  pr_conflict           await-merge     conflicted
  pr_conflict_cap       await-merge     3
  pr_conflict_escalate  await-merge     gave-up
  pr_head_moved         await-merge     head-moved
  mention_token         await-merge     @lc

signals:
  open-pr           conflicts         ~conflict
  await-merge       resets            changes
  resolve-conflict  resolve_attempts  escalate

disposition:
  merged     completed
  abandoned  abandoned
