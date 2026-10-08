---
name: script-pitfalls
description: Parsing and scripting pitfalls found while building the spend-analyst pipeline (aliases, NaN truthiness, rules.json boundary conflicts)
metadata:
  type: feedback
---

How-to lessons for scripts/ (no figures or names here).

- Normalisation step 4 joins single letters, so "T/A" becomes token "TA"; the alias split must also use " TA ", not only " T A ". Record this deviation in analytics.json `normalisation`.
  **Why:** the spec's " T A " separator can never fire after normalising. **How to apply:** keep " TA " in both tests.py and the self-check's own alias function.
- A pandas column built from str-or-None turns None into NaN, and NaN is truthy. Test `isinstance(x, str)` or `.notna()`, never `if x:`.
  **Why:** this silently skipped the off_contract candidate search on the first run (0 candidates). **How to apply:** be suspicious of any zero count; check it with a quick aggregate.
- rules.json: boundary 500000 has rules that disagree on inclusivity (low-side exclusive vs high-side exclusive). load_thresholds uses the low-side rule and logs a derivation note, which becomes a warning.
- Contracts Finder supplier column: the 200+-block framework notice belongs to a non-council buyer, so it drops out after the buyer filter.
- self_check: read the source with openpyxl `iter_rows(min_row=1)` so blank leading rows keep Excel row numbering, and run it only after tests.py (it rewrites analytics.json).
