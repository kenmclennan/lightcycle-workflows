---
summary: a scheduled judgement of whether agent review is earning its cost, then a human gate on any proposed change to a review step
when-to-use: an operator enables its suggested weekly schedule so review verdicts and escapes are analysed whenever new ones have arrived; it is not filed by hand
schedule:
  cron: 0 9 * * 1
  guard: script:scripts/new-review-activity.py
  catch-rate-floor: 0.5
  repeat-min: 3
---

# Review-yield

A schedule fires one item per week that has new review verdicts or escapes. `analyse-yield` reads `lc review-yield` for the window, judges each finding and escape for severity and kind of failure, and computes per codebase and per review stage the verdicts, rejection rate, catch rate, escapes by source and severity, cost per real finding and the trend against the previous run. It also extends a replay set of known-defect PR heads. It ends `findings` (the report plus concrete, codebase-agnostic proposals for a review step, attached as the `findings` artifact) or `clean`. On `findings` a human reads the digest at `review-findings` and decides what, if anything, to file; the analysis edits and files nothing. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config. `catch-rate-floor` and `repeat-min` are required parameters of the guard, set here so the operator sees both where the schedule is enabled.

entry: analyse-yield

display:
  analyse-yield    Analysing review yield
  review-findings  Review the findings

edges:
  analyse-yield    findings  review-findings  primary
  analyse-yield    clean
  review-findings  done
  review-findings  filed
  review-findings  reviewed
