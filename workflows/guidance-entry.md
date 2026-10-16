---
summary: a finding to merged guidance entries in one PR - drafted, mechanically checked, human-verified, then merged
when-to-use: any change to the guidance repo - a new entry, an edit, or retiring one - so every entry has an item, a recorded finding, and a human gate before it can become stable
---

# Guidance-entry

One item, one id, one phase, one PR, for items whose repo is the guidance repo. `guidance-writer` reads the brief (the finding and what the human and driver agreed), writes, edits or retires entries as `draft` (retiring sets `status: deprecated`, never deletes the file), and records where the finding came from. `check-entries` then runs a mechanical conventions check over every changed entry before any human sees the PR: front matter, `type: Guidance`, an inline `applies-to` list, a concept page for every facet, and steps in a valid form; a non-empty `purpose`, `when` and `why`, and no item id; the writer's output may never be `stable` or carry a `verified` record, except that an entry whose only change is its `purpose`, `when` and `why` keeps the status and record it had. `verify-entries` is the human gate where an entry is marked `status: stable` with its `verified` record, since only a human may make an entry deliverable; entries the human leaves unverified merge as `draft`, which is never delivered. The check runs again after the gate so a front-matter edit cannot slip a malformed entry past merge, and then `ready-pr` marks the PR ready for review and it merges through the generic await-merge machinery. `open-pr` opens the PR as a GitHub draft with a warning in its body, so it cannot be merged from the button while the item waits at `verify-entries`; a merge that happens anyway routes to `merged-unverified`, a human gate that names each entry left `draft` on main and asks for a follow-up item to verify them. The guidance repo has no CI, so there are no CI stages: `open-pr` goes straight to the gate. A rework round returns to `guidance-writer` and re-runs the check and the gate.

entry: guidance-writer

requires: repo

workspace: project

nodes:
  open-pr  open-guidance-pr

phase:
  guidance-writer   entry
  check-entries     entry
  open-pr           entry
  verify-entries    entry
  ready-pr          entry
  await-merge       entry
  merged-unverified entry
  cleanup           entry
  handle-feedback   entry
  resolve-conflict  entry
  review-conflict   entry

display:
  guidance-writer   Writing entries
  check-entries     Checking entries
  open-pr           Opening PR
  verify-entries    Verify entries
  ready-pr          Marking ready
  await-merge       Review PR
  merged-unverified Merged unverified
  cleanup           Tidying up
  handle-feedback   Reading feedback
  resolve-conflict  Resolving conflict
  review-conflict   Resolve conflict

edges:
  guidance-writer   done           check-entries     primary
  check-entries     clean          open-pr           primary
  check-entries     broken         guidance-writer
  check-entries     final-clean    ready-pr
  check-entries     verify-broken  verify-entries
  open-pr           done           verify-entries    primary
  open-pr           conflicted     resolve-conflict
  verify-entries    verified       check-entries     primary
  verify-entries    left-draft     check-entries
  verify-entries    changes        guidance-writer
  verify-entries    merged-early   merged-unverified
  ready-pr          done           await-merge       primary
  await-merge       merged         cleanup
  merged-unverified acknowledged   cleanup           primary
  await-merge       changes        guidance-writer
  await-merge       conflicted     resolve-conflict
  await-merge       gave-up        review-conflict
  await-merge       head-moved     check-entries
  resolve-conflict  resolved       open-pr           primary
  resolve-conflict  escalate       review-conflict
  handle-feedback   done
  review-conflict   resolved       open-pr           primary

hooks:
  pr_merge              verify-entries  merged-early
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
