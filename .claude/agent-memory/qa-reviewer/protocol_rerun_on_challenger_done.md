---
name: protocol-rerun-on-challenger-done
description: Re-run run_checks.py when CHALLENGER DONE arrives, without waiting for PLANNER DONE, to avoid a mutual wait with the planner
metadata:
  type: feedback
---

When `CHALLENGER DONE` arrives, re-run `run_checks.py` on the latest version straight away and send the `QA vN:` result to the planner. Do this before `PLANNER DONE` arrives.

**Why:** challenge statuses live in `challenges.md`, which the challenger owns. Trace FAILs for open challenges clear only once the challenger finalises that file, not after a plan rebuild. The planner waits for a QA result before sending `PLANNER DONE`. If QA waits for `PLANNER DONE`, the two wait on each other, and the lead had to step in to break the deadlock.

**How to apply:** treat `CHALLENGER DONE` as a re-run trigger for the current version. The final run and `review.md` still follow both DONE messages. Related: [[trace-check-reads-challenges]]
