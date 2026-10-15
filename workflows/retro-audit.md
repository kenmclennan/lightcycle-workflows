---
summary: a scheduled audit of closed work for process defects, then a human gate on any findings
when-to-use: an operator enables its suggested schedule so closed items carrying feedback are audited in batches; it is not filed by hand
schedule:
  cron: 0 9 * * *
  guard: pending-reflections
  min: 30
---

# Retro-audit

A schedule fires one item per batch of closed items that carry feedback, once at least 30 reflections are pending. `audit` reads the batch from the item description, judges it against a four-part bar and the plain-language rubric, and ends `findings` (a digest attached as the `findings` artifact) or `clean`. On `findings` a human reads the digest at `review-findings` and decides what, if anything, to file; the audit itself files nothing. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config.

entry: audit

display:
  audit            Auditing recent work
  review-findings  Review the findings

edges:
  audit            findings  review-findings  primary
  audit            clean
  review-findings  done
  review-findings  filed
  review-findings  reviewed
