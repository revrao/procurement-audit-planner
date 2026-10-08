# Planning memo: procurement audit, West Berkshire Council

Built 2026-10-08 21:31 UTC by `build_pack.py` from `outputs/audit-plan.json` and register revision 1; every figure the builder computed is in `outputs/pack-figures.json`.

*Results are risk indicators to investigate, not findings.* Nothing in this pack is a finding against the council, a department or a supplier; sampled items are flagged for examination.

## Objective

To give the auditor assurance on whether West Berkshire Council's purchasing follows the Contract Procedure Rules in the areas where the full spend population shows risk indicators: requirements aggregated before the route is chosen [CPR-13, cl. 6.16], contract and notice records for high-value suppliers [CPR-08, cl. 5.2.1] [CPR-52, cl. App B row B1], extensions and variations approved before spend continues [CPR-62, cl. App C row D] [CPR-63, cl. App C row E], repeat payments supported by distinct purchase evidence [CPR-32, cl. 10.1], and recorded reasons for social care placements [CPR-65, cl. App C row F]. The pack covers the 6 risks the auditor approved in register revision 1.

## Background

The analytics cover 3 months of published spend over the reporting threshold (2026-05-01 to 2026-07-31), 8,478 payments after cleaning [`$.cleaning.rows_kept`]. Code tested the whole population, not a random sample. Split-purchase testing found 580 supplier groups, 149 in general procurement [`$.tests.split_purchases.by_tag.general_procurement.items`]. 324 non-placement suppliers above the publication threshold, on an annualised estimate of spend, have no match in the notice export [`$.tests.off_contract.counts.non_placement`]. 8 suppliers were paid after every matched notice had ended [`$.tests.expired_notice_spend.counts.items`], and 8 contracts screen above the award value per year [`$.tests.spend_vs_award.counts.items`]. Duplicate testing found 50 general-procurement repeat chains [`$.tests.duplicates.by_tag.general_procurement.items`]. Contract Letting [AUD-01] and Accounts Payable [AUD-11] last received Reasonable Assurance, as did the Purchase of Residential and Nursing Care Provision [AUD-14].

## Scope

The auditor approved 6 of the 6 risks in register revision 1 (`outputs/auditor-comments.md`).

| Risk | Title | Score | Band | Auditor decision | Controls | Tests | Items sampled | Transactions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-01 | Requirements split, or payments pitched just under a quote or approval boundary | 9 | Medium - High | approve | 3 | 4 | 52 | 563 |
| R-02 | Contract and notice documentation to verify for high-value suppliers not matched in the notice export | 9 | Medium - High | amend | 2 | 2 | 23 | 405 |
| R-03 | Payments to suppliers whose matched contract notices had all ended before the spend window | 9 | Medium - High | approve | 1 | 1 | 8 | 60 |
| R-04 | Spend-to-date against contract values and approved variations | 9 | Medium - High | amend | 1 | 1 | 15 | 55 |
| R-05 | Repeat payments of the same amount to the same supplier within days | 9 | Medium - High | approve | 1 | 1 | 15 | 35 |
| R-06 | Social care placements without a recorded reason for the choice of provider | 4 | Moderate | approve | 1 | 1 | 10 | 1294 |

## Approach

For each approved risk the program sets out the expected control, the test steps and a targeted sample drawn from the items an analytics test flagged, not from the whole spend file. Samples are sized by the risk's score on the council's Table 4 bands and drawn deterministically. The pack examines 123 items covering 2,412 transactions worth £47,685,087.07, through 10 tests of 9 controls, and requests 21 PBC items. Samples exclude placements and grants except where the risk concerns placements or the flagged list is small enough to take whole. Each sampled item is a risk indicator to investigate; an explained item (an instalment under an existing contract, a framework call-off, a distinct invoice) is recorded as explained.

## Sampling

Samples are targeted, not random: each test draws from the full list of items a spend-analytics test flagged, using the filter, order and method in the audit program. Every draw is deterministic, so a rebuild gives the same sample. Items per test are set by the risk's score on the council's Table 4 ranges (score 15+: 25; score 8+: 15; score 4+: 10; score 1+: 5). Every sampled transaction was matched to `outputs/analytics-full/spend_clean.csv`, and each item's payment count and total were reconciled to its transactions.

| Test | Risk | Flagged list | Items flagged | After filter | Sample size | Items drawn | Transactions | Value drawn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-01 | R-01 | `split_purchases.csv` | 580 | 55 | 15 | 15 | 267 | £1,583,227.18 |
| T-02 | R-01 | `split_purchases.csv` | 580 | 7 | 15 | 7 (all available) | 227 | £15,178,598.01 |
| T-03 | R-01 | `threshold_clustering.csv` | 366 | 63 | 15 | 15 | 15 | £60,472.59 |
| T-10 | R-01 | `split_purchases.csv` | 580 | 87 | 15 | 15 | 54 | £36,317.42 |
| T-04 | R-02 | `off_contract.csv` | 618 | 179 | 15 | 15 | 292 | £20,459,189.43 |
| T-05 | R-02 | `off_contract.csv` | 618 | 8 | 15 | 8 (all available) | 113 | £269,452.97 |
| T-06 | R-03 | `expired_notice_spend.csv` | 8 | 8 | 15 | 8 (all available) | 60 | £243,364.42 |
| T-07 | R-04 | `spend_vs_award.csv` | 20 | 20 | 15 | 15 | 55 | £875,827.82 |
| T-08 | R-05 | `duplicates.csv` | 684 | 50 | 15 | 15 | 35 | £542,579.56 |
| T-09 | R-06 | `off_contract.csv` | 618 | 294 | 10 | 10 | 1,294 | £8,436,057.67 |

In total 123 items, 2,412 transactions, £47,685,087.07. The transactions for each test are in `outputs/samples/<test>.csv`.

## Rule coverage

All 66 rules in `outputs/rules.json` are accounted for: 27 are cited by an in-scope risk, control or test, and 39 are not tested, each with a reason (`outputs/risk-control-matrix.md`).

## Limitations

Bands in the rules apply to contract value, not to individual payments [`$.tests.threshold_clustering.caveats`], and regular instalments under one contract produce expected split-purchase groups [`$.tests.split_purchases.caveats`]. The notice export covers only 7.3% of high-value suppliers [`$.tests.off_contract.coverage.share_by_count`], so an unmatched supplier is a record to verify, not evidence that a notice is missing, and the test says nothing about suppliers below the publication threshold [`$.tests.off_contract.caveats`]. Spend against award uses an annualised estimate from 3 months only, to select contracts; the test itself uses ledger spend-to-date [`$.tests.spend_vs_award.caveats`]. The procurement-legislation Threshold is null in the rules extract, so the Thresholds in force are requested as a PBC item and the tiers that depend on them are tested only where the plan names them [`$.rules_used.skipped_tiers[0].reason`]. The 2,710 rows identical in all published columns [`$.tests.duplicates.counts.identical_rows_from_cleaning.rows`] have no full list in analytics-full, so they are covered by requesting the accounts payable duplicate-check report rather than by a sample. Open agreed actions and the Strategic Risk Register are not available in the public papers [GAP-01] [GAP-04].

## Sign-off

Draft for the auditor. The pack is cross-checked by the challenger and the QA reviewer; sign-off is recorded in `outputs/review.md`.
