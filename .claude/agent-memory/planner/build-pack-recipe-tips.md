---
name: build-pack-recipe-tips
description: How-to pitfalls for audit-plan.json recipes and text checks in build_pack.py (filters, typed numbers, rule coverage)
metadata:
  type: feedback
---

- Boolean CSV columns (`flag`, `mainly_placement`) filter with string value `"True"`/`"False"`; the builder compares the cell text.
- A filter value `"{{$.rules_used.boundaries[2].value}}"` resolves to a number, so `>=` works on `boundary`.
- Rules cited anywhere in an in-scope register risk already count as cited; listing them in `rules_not_tested` fails the build.
- Typed-number check flags any 2+ digit number, decimals and £/% figures in prose; single digits and numbers after "clause/App/row/table/T-/CPR-" are exempt. Write "three quotes", not digits.
- Identical-row duplicates have no full list in analytics-full; cover them via a PBC request, not a sample.

**Why:** learned on the first build of the pack; it built clean first time with these.
**How to apply:** check these before writing recipes and memo text.
