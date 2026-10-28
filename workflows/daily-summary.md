---
summary: a scheduled standup-ready list of the work closed on one day
when-to-use: an operator enables its suggested schedule so each day's closes are summarised; it is not filed by hand
schedule:
  cron: 0 7 * * *
  name: summary
  guard: day-unsummarised
---

# Daily-summary

A schedule fires one item for a day with closes not yet summarised. `daily-summary` sorts the day's closed work into `Delivered`, `Fixed` and `Improved` bullet sections and attaches a short plain-text `summary` artifact. It ends `done`; `abandoned` exists for a driver who abandons a summary they do not want. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config.

entry: daily-summary

display:
  daily-summary  Writing the daily summary

edges:
  daily-summary  done
  daily-summary  abandoned
