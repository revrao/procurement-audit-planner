# Challenges to the audit planning pack

Register revision: 1 · Pack versions reviewed: v1, v2 · Status: closed

| # | Round | Type | Risk | Challenge (with citations) | Ask | Planner response | Status | Verified in | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | sample | R-01 | T-01 draws only quote-threshold groups although groups also sit at the App A boundaries [metric:$.tests.split_purchases.counts.by_boundary[3].groups] [rule:CPR-13] | Add the App A boundary groups to the sample | accepted: filter widened | resolved | v2 | |
| 2 | 1 | rating | R-05 | Same-amount chains are widespread [metric:$.tests.duplicates.counts.items]; sample covers `$.pack.tests.T-03.sampled_items` items | Should the likelihood be higher? | for the auditor: rating is the auditor's decision | for the auditor | | |
| 3 | 2 | test | R-01 | T-02 step names no evidence for the quotation record [rule:CPR-51] | Name the quote record in the step | declined: PBC item already requests it | declined | | |
