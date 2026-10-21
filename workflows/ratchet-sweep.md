---
summary: a scheduled sweep of active repos for missing ratchet guards and baselines that have stopped shrinking, then a human gate on any findings
when-to-use: the engine fires it on a schedule so a new catalog ratchet reaches every active repo; it is not filed by hand
---

# Ratchet-sweep

A schedule fires one item per sweep. `ratchet-sweep` finds the repos with recent closed work, detects each one's stack, checks it against the ratchet entries in the guidance workspace (or a built-in starter list when the catalog has none), attaches its digest as the `findings` artifact, and ends `findings` or `clean`. On `findings` a human reads the digest at `review-findings` and decides what, if anything, to file; the sweep files and edits nothing. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The bundle declares the workflow only. The engine owns the schedule and the guard that skips a run when no repo is active.

entry: ratchet-sweep

display:
  ratchet-sweep    Sweeping repos for missing ratchets
  review-findings  Review the findings

edges:
  ratchet-sweep    findings  review-findings  primary
  ratchet-sweep    clean
  review-findings  done
  review-findings  filed
  review-findings  reviewed
