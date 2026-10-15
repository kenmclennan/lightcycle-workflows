---
summary: a scheduled audit of the guidance and workflow material agents are told to follow, then a human gate on any findings
when-to-use: an operator enables its suggested schedule so the material is judged whenever it has changed; it is not filed by hand
schedule:
  cron: 0 9 * * 1
  guard: materials-changed
---

# Material-audit

A schedule fires one item whenever the guidance repo or a workflow origin has changed since the last firing. `material-audit` judges the guidance entries and the workflow bundles against its criteria, attaches its digest as the `findings` artifact, and ends `findings` or `clean`. On `findings` a human reads the digest at `review-findings` and decides what, if anything, to file; the audit files and edits nothing. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config.

entry: material-audit

display:
  material-audit   Auditing guidance and workflows
  review-findings  Review the findings

edges:
  material-audit   findings  review-findings  primary
  material-audit   clean
  review-findings  done
  review-findings  filed
  review-findings  reviewed
