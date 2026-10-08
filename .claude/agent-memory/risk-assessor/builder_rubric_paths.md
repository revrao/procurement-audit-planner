---
name: builder-rubric-paths
description: How build_register.py derives the likelihood rubric level from cited metric paths, and useful analytics.json path recipes
metadata:
  type: reference
---

- rubric_level() only reads `[metric:$.tests.X...]` citations in the likelihood justification: each non-zero value adds test X; "general procurement" = path contains `general_procurement` or `non_placement` (so `mainly_placement` / `by_tag.placement` do NOT count as GP -> caps at 2).
- Citing any non-zero metric from a second test (even a population test like `high_value_suppliers`) lifts the rubric to 4; decide deliberately which tests are indicators.
- Useful paths: `$.tests.threshold_clustering.counts.by_boundary[n].ratio_band_to_comparison` (valid below-rubric reason), `$.tests.off_contract.coverage.share_by_count|pct`, `$.rules_used.skipped_tiers[0].reason`, `$.tests.X.caveats` (list cites fine).
- Financial impact: `impact.financial_figure` is a path; by_tag gbp in duplicates is repeat £ (sums to gbp_total).
- jq recipe: `for t in $(jq -r '.tests|keys[]' outputs/analytics.json); do jq -c ".tests[\"$t\"]|{counts,by_tag,caveats}" outputs/analytics.json; done` (avoid dumping self_check/top20 row_ids: huge).
