# Audit program: procurement audit, West Berkshire Council

Built 2026-10-08 21:31 UTC by `build_pack.py` from `outputs/audit-plan.json` and register revision 1; every figure the builder computed is in `outputs/pack-figures.json`.

*Results are risk indicators to investigate, not findings.* Nothing in this pack is a finding against the council, a department or a supplier; sampled items are flagged for examination.

## R-01 · Requirements split, or payments pitched just under a quote or approval boundary

Score 9 (likelihood 3 × impact 3), Medium - High; auditor decision: approve. Sample size per test: 15 items.

Expected controls:

- **C-01** Before a purchase route is chosen, the officer estimates the total value of the requirement and does not split or disaggregate it to avoid the Rules [CPR-13, cl. 6.16], and documents the procurement's progress [CPR-31, cl. 9.3].
- **C-02** Where the aggregated requirement reaches the quote threshold, at least three quotes are invited through the Procurement Portal and a contract notice is published [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1] [CPR-53, cl. App B row B2] [CPR-54, cl. App B row B2]; below it, at least one quote is sought [CPR-50, cl. App B row A]. Where the aggregated value exceeds the relevant Threshold, a written report is approved by the relevant board [CPR-47, cl. App A row 2].
- **C-03** Where the aggregated requirement reaches the App A approval boundaries, the award is treated as a Key Decision with a board-approved written report or Executive approval [CPR-04, cl. 4.3] [CPR-48, cl. App A row 3] [CPR-49, cl. App A row 4], and works above the App B row C band go to full competitive tender with a Portal advert [CPR-55, cl. App B row C] [CPR-56, cl. App B row C].

### T-01 · tests C-01, C-02

**Test step.** For each sampled general-procurement group at the quote threshold, obtain the purchase orders and invoices and establish whether the payments relate to one requirement [CPR-13, cl. 6.16]. If they do, confirm that quotes were invited through the Procurement Portal from at least three sources and a contract notice was published for the aggregated value [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1]. If the payments are instalments under an existing contract, obtain the contract and record the group as explained [`$.tests.split_purchases.caveats`]. Where the aggregated value exceeds the relevant Threshold in force, confirm that a written report was approved by the relevant board [CPR-47, cl. App A row 2].

**Sample.** The largest of the 55 general-procurement groups that cross the quote threshold [`$.tests.split_purchases.counts.by_boundary[1].by_tag.general_procurement.items`], to cover the most value where the three-quote and notice route applies [CPR-51, cl. App B row B1].

- Flagged list: `outputs/analytics-full/split_purchases.csv` (split_purchases), 580 items; filter: `tag` == general_procurement; `boundary` == 25,000 (`$.rules_used.quote_threshold.value`); 55 after the filter
- Order: `sum_gbp` desc; method: top; size: 15 (score 9)
- Drawn: 15 items, 267 transactions, £1,583,227.18; transactions in `outputs/samples/T-01.csv`
- PBC: PBC-01, PBC-02, PBC-03, PBC-04, PBC-05

Items to examine (risk indicators, not findings):

| # | Boundary | Supplier | First | Last | Payments | Group total | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | £25,000.00 | VolkerHighways Ltd | 2026-05-05 | 2026-05-27 | 32 | £258,306.28 | general_procurement | 32 |
| 2 | £25,000.00 | VolkerHighways Ltd | 2026-07-13 | 2026-07-31 | 37 | £223,741.08 | general_procurement | 37 |
| 3 | £25,000.00 | The Better Group Ltd | 2026-05-28 | 2026-06-25 | 15 | £187,440.02 | general_procurement | 15 |
| 4 | £25,000.00 | WEAVAWAY TRAVEL LTD | 2026-07-08 | 2026-07-24 | 25 | £94,891.38 | general_procurement | 25 |
| 5 | £25,000.00 | VolkerHighways Ltd | 2026-06-08 | 2026-07-07 | 10 | £87,809.91 | general_procurement | 10 |
| 6 | £25,000.00 | Roadside Technologies Ltd | 2026-07-13 | 2026-07-30 | 10 | £84,070.16 | general_procurement | 10 |
| 7 | £25,000.00 | FD TRAVELS LIMITED T/A SCHOOL EXPRESS | 2026-07-09 | 2026-07-27 | 30 | £77,830.64 | general_procurement | 30 |
| 8 | £25,000.00 | The Better Group Ltd | 2026-07-06 | 2026-07-29 | 4 | £77,145.40 | general_procurement | 4 |
| 9 | £25,000.00 | BROADWAY CARS | 2026-05-12 | 2026-05-27 | 30 | £76,612.74 | general_procurement | 30 |
| 10 | £25,000.00 | WEAVAWAY TRAVEL LTD | 2026-05-06 | 2026-06-02 | 20 | £74,460.22 | general_procurement | 20 |
| 11 | £25,000.00 | FD TRAVELS LIMITED T/A SCHOOL EXPRESS | 2026-05-06 | 2026-05-28 | 33 | £72,688.83 | general_procurement | 33 |
| 12 | £25,000.00 | Elior UK PLC | 2026-06-16 | 2026-07-15 | 4 | £72,328.76 | general_procurement | 4 |
| 13 | £25,000.00 | Triple Value Impact | 2026-06-17 | 2026-06-18 | 5 | £68,028.00 | general_procurement | 5 |
| 14 | £25,000.00 | Elior UK PLC | 2026-05-13 | 2026-06-11 | 4 | £65,913.75 | general_procurement | 4 |
| 15 | £25,000.00 | Newbury & District Ltd | 2026-06-12 | 2026-06-30 | 8 | £61,960.01 | general_procurement | 8 |

### T-02 · tests C-01, C-03

**Test step.** For each sampled general-procurement group at the App A approval boundaries, establish whether the payments relate to one contract or requirement [CPR-13, cl. 6.16] and confirm that the approval matched the aggregated value: a Key Decision with a board-approved written report [CPR-04, cl. 4.3] [CPR-48, cl. App A row 3], or Executive approval at the higher boundary [CPR-49, cl. App A row 4]. For works, confirm that a full competitive tender was run [CPR-55, cl. App B row C]. Groups examined: [`$.tests.split_purchases.counts.by_boundary[2].by_tag.general_procurement.items`] [`$.tests.split_purchases.counts.by_boundary[3].by_tag.general_procurement.items`].

**Sample.** Every general-procurement group at the App A approval boundaries, where the approval route changes most [`$.tests.split_purchases.counts.by_boundary[2].by_tag.general_procurement.gbp`] [CPR-48, cl. App A row 3].

- Flagged list: `outputs/analytics-full/split_purchases.csv` (split_purchases), 580 items; filter: `tag` == general_procurement; `boundary` >= 500,000 (`$.rules_used.boundaries[2].value`); 7 after the filter
- Order: `sum_gbp` desc; method: top; size: 15 (score 9); only 7 available
- Drawn: 7 items, 227 transactions, £15,178,598.01; transactions in `outputs/samples/T-02.csv`
- PBC: PBC-01, PBC-04, PBC-06, PBC-07

Items to examine (risk indicators, not findings):

| # | Boundary | Supplier | First | Last | Payments | Group total | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | £2,500,000.00 | VEOLIA ES WEST BERKSHIRE LTD (CHAPS ONLY) | 2026-06-29 | 2026-07-27 | 2 | £3,984,208.64 | general_procurement | 2 |
| 2 | £2,500,000.00 | VolkerHighways Ltd | 2026-06-22 | 2026-07-17 | 42 | £2,623,419.58 | general_procurement | 42 |
| 3 | £2,500,000.00 | VolkerHighways Ltd | 2026-05-01 | 2026-05-28 | 55 | £2,524,806.85 | general_procurement | 55 |
| 4 | £500,000.00 | VolkerHighways Ltd | 2026-05-01 | 2026-05-28 | 55 | £2,524,806.85 | general_procurement | 55 |
| 5 | £500,000.00 | VolkerHighways Ltd | 2026-06-08 | 2026-07-07 | 18 | £1,690,085.96 | general_procurement | 18 |
| 6 | £500,000.00 | VolkerHighways Ltd | 2026-07-13 | 2026-07-31 | 51 | £1,308,291.51 | general_procurement | 51 |
| 7 | £500,000.00 | SoftwareONE UK Ltd | 2026-05-27 | 2026-05-27 | 4 | £522,978.62 | general_procurement | 4 |

### T-03 · tests C-02

**Test step.** For each sampled general-procurement payment just under a boundary, obtain the purchase order and invoice and confirm the quote evidence for the route that applies to the contract's total value: at least one quote below the quote threshold [CPR-50, cl. App B row A], or the three-quote and notice route above it [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1]. Establish whether other payments to the supplier form the same requirement [CPR-13, cl. 6.16]. The register records no excess clustering at the quote threshold [`$.tests.threshold_clustering.counts.by_boundary[1].ratio_band_to_comparison`], so this is a spread sample.

**Sample.** Evenly spaced through the 63 general-procurement payments just under a boundary [`$.tests.threshold_clustering.by_tag.general_procurement.items`], because the comparison band shows no excess clustering [`$.tests.threshold_clustering.counts.by_boundary[0].ratio_band_to_comparison`].

- Flagged list: `outputs/analytics-full/threshold_clustering.csv` (threshold_clustering), 366 items; filter: `tag` == general_procurement; 63 after the filter
- Order: `Net amount` desc; method: systematic; size: 15 (score 9)
- Drawn: 15 items, 15 transactions, £60,472.59; transactions in `outputs/samples/T-03.csv`
- PBC: PBC-01, PBC-02

Items to examine (risk indicators, not findings):

| # | Boundary | Supplier | Date | Amount | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | £25,000.00 | Triple Value Impact | 2026-06-18 | £24,244.00 | general_procurement | 1 |
| 2 | £25,000.00 | Elior UK PLC | 2026-05-27 | £23,694.03 | general_procurement | 1 |
| 3 | £1,000.00 | PREPAID FINANCIAL SERVICES | 2026-05-27 | £1,000.00 | general_procurement | 1 |
| 4 | £1,000.00 | Becky Turner | 2026-07-14 | £1,000.00 | general_procurement | 1 |
| 5 | £1,000.00 | ALAN FULLER | 2026-07-16 | £1,000.00 | general_procurement | 1 |
| 6 | £1,000.00 | PRESTIGE NETWORK | 2026-06-15 | £993.48 | general_procurement | 1 |
| 7 | £1,000.00 | FAMILY FUTURES CONSORTIUM CIC | 2026-07-15 | £990.00 | general_procurement | 1 |
| 8 | £1,000.00 | N Mehmood T/A A Star Executive Cars Ltd | 2026-05-12 | £980.00 | general_procurement | 1 |
| 9 | £1,000.00 | MAISHA STAFFING SOLUTIONS LTD | 2026-07-29 | £975.00 | general_procurement | 1 |
| 10 | £1,000.00 | Premier Cars | 2026-06-03 | £968.00 | general_procurement | 1 |
| 11 | £1,000.00 | Early Education | 2026-05-27 | £954.00 | general_procurement | 1 |
| 12 | £1,000.00 | READING TRANSPORT LTD | 2026-07-22 | £936.00 | general_procurement | 1 |
| 13 | £1,000.00 | BRITS AIRPORT CARS LIMITED | 2026-06-30 | £920.00 | general_procurement | 1 |
| 14 | £1,000.00 | Melanie Sneddon | 2026-07-15 | £912.50 | general_procurement | 1 |
| 15 | £1,000.00 | WSP UK  LTD | 2026-07-02 | £905.58 | general_procurement | 1 |

### T-10 · tests C-01, C-02

**Test step.** For each sampled general-procurement group at the lowest boundary, obtain the purchase orders and invoices and establish whether the payments relate to one requirement [CPR-13, cl. 6.16]. If they do, confirm that at least one quote was sought for the aggregated value [CPR-50, cl. App B row A]. If the payments are separate requirements or instalments under an existing arrangement, record the group as explained [`$.tests.split_purchases.caveats`].

**Sample.** Evenly spaced through the 87 general-procurement groups at the lowest boundary [`$.tests.split_purchases.counts.by_boundary[0].by_tag.general_procurement.items`], where the one-quote rule applies [CPR-50, cl. App B row A] and clustering is close to parity [`$.tests.threshold_clustering.counts.by_boundary[0].ratio_band_to_comparison`].

- Flagged list: `outputs/analytics-full/split_purchases.csv` (split_purchases), 580 items; filter: `tag` == general_procurement; `boundary` == 1,000 (`$.rules_used.boundaries[0].value`); 87 after the filter
- Order: `sum_gbp` desc; method: systematic; size: 15 (score 9)
- Drawn: 15 items, 54 transactions, £36,317.42; transactions in `outputs/samples/T-10.csv`
- PBC: PBC-01, PBC-02

Items to examine (risk indicators, not findings):

| # | Boundary | Supplier | First | Last | Payments | Group total | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | £1,000.00 | Stripeweb | 2026-07-08 | 2026-07-31 | 9 | £5,315.86 | general_procurement | 9 |
| 2 | £1,000.00 | WSP UK  LTD | 2026-06-11 | 2026-07-02 | 6 | £4,623.44 | general_procurement | 6 |
| 3 | £1,000.00 | MAISHA STAFFING SOLUTIONS LTD | 2026-05-12 | 2026-06-09 | 6 | £3,845.35 | general_procurement | 6 |
| 4 | £1,000.00 | ABC TRAVEL (WOKINGHAM) LIMITED T/A ABC TRAVEL | 2026-05-06 | 2026-06-01 | 4 | £3,034.82 | general_procurement | 4 |
| 5 | £1,000.00 | MAISHA STAFFING SOLUTIONS LTD | 2026-07-29 | 2026-07-29 | 3 | £2,681.90 | general_procurement | 3 |
| 6 | £1,000.00 | APETITO LTD | 2026-05-20 | 2026-06-16 | 4 | £2,494.05 | general_procurement | 4 |
| 7 | £1,000.00 | FD TRAVELS LIMITED T/A SCHOOL EXPRESS | 2026-07-09 | 2026-07-14 | 4 | £2,255.89 | general_procurement | 4 |
| 8 | £1,000.00 | MAISHA STAFFING SOLUTIONS LTD | 2026-06-11 | 2026-06-24 | 3 | £1,995.50 | general_procurement | 3 |
| 9 | £1,000.00 | P. APPLEYARD (TOFFS CATERING) | 2026-06-17 | 2026-07-14 | 3 | £1,755.40 | general_procurement | 3 |
| 10 | £1,000.00 | PRESTIGE NETWORK | 2026-06-15 | 2026-06-15 | 2 | £1,630.08 | general_procurement | 2 |
| 11 | £1,000.00 | BROADWAY CARS | 2026-07-09 | 2026-07-13 | 2 | £1,500.67 | general_procurement | 2 |
| 12 | £1,000.00 | Newbury & District Ltd | 2026-06-02 | 2026-06-30 | 2 | £1,422.04 | general_procurement | 2 |
| 13 | £1,000.00 | J R TYRES LTD | 2026-07-01 | 2026-07-15 | 2 | £1,351.35 | general_procurement | 2 |
| 14 | £1,000.00 | METRIC GROUP LTD | 2026-07-16 | 2026-07-31 | 2 | £1,228.67 | general_procurement | 2 |
| 15 | £1,000.00 | BFS GROUP LTD t/a Bidfood | 2026-05-20 | 2026-06-03 | 2 | £1,182.40 | general_procurement | 2 |

## R-02 · Contract and notice documentation to verify for high-value suppliers not matched in the notice export

Score 9 (likelihood 3 × impact 3), Medium - High; auditor decision: amend. Sample size per test: 15 items.

Expected controls:

- **C-04** Every contract award is notified and recorded on the Council Contract Register with its value, duration and supplier [CPR-35, cl. 10.4] [CPR-08, cl. 5.2.1], and contracts in Appendix B are in writing in an approved form [CPR-33, cl. 10.2].
- **C-05** A contract at or above the publication threshold is let through the App B route, with invitations to at least three sources and a contract notice on the CDP [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1] [CPR-53, cl. App B row B2] [CPR-54, cl. App B row B2], or through a Purchasing Scheme with advice and approval obtained before award [CPR-28, cl. 8.2] [CPR-61, cl. App C row C], or under a documented exception [CPR-26, cl. 7.5]. Above the procurement-legislation Threshold, a full competitive tender is run and an advert placed on the CDP [CPR-57, cl. App B row D] [CPR-58, cl. App B row D].

### T-04 · tests C-04, C-05

**Test step.** For each sampled supplier, treat the absence of a notice match as a record to verify, not as evidence that a notice is missing [`$.tests.off_contract.coverage.share_by_count`]. Confirm whether the supplier appears on the council's contract register [CPR-08, cl. 5.2.1] and obtain the written contract [CPR-33, cl. 10.2]. Obtain the procurement route and the published notice [CPR-52, cl. App B row B1], or the recorded reason none was required: a framework call-off with prior approval [CPR-61, cl. App C row C], a contract predating the export, a different legal or trading name, or a documented exception [CPR-26, cl. 7.5] [`$.tests.off_contract.caveats`]. Where the contract value exceeds the procurement-legislation Threshold in force, confirm that a full competitive tender was run and an advert placed on the CDP [CPR-57, cl. App B row D] [CPR-58, cl. App B row D].

**Sample.** The largest non-placement, non-grant suppliers above the publication threshold, on an annualised estimate, with no notice match: general procurement [`$.tests.off_contract.by_tag.general_procurement.items`], agency staff [`$.tests.off_contract.by_tag.agency_staff.items`] and premises [`$.tests.off_contract.by_tag.premises.items`], all bought under the App B routes [CPR-51, cl. App B row B1]. Grant payments are not purchases under App B and stay out. Suppliers below the publication threshold are outside this test [`$.tests.off_contract.parameters.publication_threshold`].

- Flagged list: `outputs/analytics-full/off_contract.csv` (off_contract), 618 items; filter: `main_tag` in general_procurement, agency_staff, premises; `mainly_placement` == False; 179 after the filter
- Order: `window_gbp` desc; method: top; size: 15 (score 9)
- Drawn: 15 items, 292 transactions, £20,459,189.43; transactions in `outputs/samples/T-04.csv`
- PBC: PBC-08, PBC-04, PBC-03, PBC-02, PBC-09, PBC-10, PBC-05

Items to examine (risk indicators, not findings):

| # | Supplier | Payments | Window spend | Annualised estimate | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | VolkerHighways Ltd | 126 | £7,377,922.21 | £29,511,688.84 | general_procurement | 126 |
| 2 | VEOLIA ES WEST BERKSHIRE LTD (CHAPS ONLY) | 3 | £6,186,065.04 | £24,744,260.16 | general_procurement | 3 |
| 3 | Millbrook Healthcare Limited | 4 | £3,459,365.35 | £13,837,461.40 | general_procurement | 4 |
| 4 | Comensura Ltd | 14 | £1,275,552.15 | £5,102,208.60 | agency_staff | 14 |
| 5 | SoftwareONE UK Ltd | 4 | £522,978.62 | £2,091,914.48 | general_procurement | 4 |
| 6 | Livity Life Ltd | 9 | £513,074.85 | £2,052,299.40 | general_procurement | 9 |
| 7 | Elior UK PLC | 9 | £161,415.59 | £645,662.36 | general_procurement | 9 |
| 8 | BBOWT | 3 | £144,317.43 | £577,269.72 | general_procurement | 3 |
| 9 | A2 Dominion | 2 | £136,612.06 | £546,448.24 | premises | 2 |
| 10 | ANCHOR PIPEWORK LIMITED | 36 | £127,841.41 | £511,365.64 | general_procurement | 36 |
| 11 | KPMG | 3 | £119,155.00 | £476,620.00 | general_procurement | 3 |
| 12 | SCOTTISH & SOUTHERN | 2 | £110,760.98 | £443,043.92 | general_procurement | 2 |
| 13 | Education Software Solutions Limited | 2 | £110,330.35 | £441,321.40 | general_procurement | 2 |
| 14 | Continental Landscapes Ltd | 8 | £108,423.39 | £433,693.56 | premises | 8 |
| 15 | KB Real Estate Management Ltd | 67 | £105,375.00 | £421,500.00 | premises | 67 |

### T-05 · tests C-04

**Test step.** For each supplier with a near-miss name candidate, confirm from the contract register and the notice whether the candidate notice is the same supplier under a different name [CPR-08, cl. 5.2.1] [`$.tests.off_contract.counts.with_candidates`]. Where it is, record the supplier as matched; where it is not, carry it into the verification in T-04.

**Sample.** All suppliers whose only notice match is a near-miss name candidate, which the analytics never count as matched [`$.tests.off_contract.counts.with_candidates`].

- Flagged list: `outputs/analytics-full/off_contract.csv` (off_contract), 618 items; filter: `notice_match` == candidate only; 8 after the filter
- Order: `window_gbp` desc; method: top; size: 15 (score 9); only 8 available
- Drawn: 8 items, 113 transactions, £269,452.97; transactions in `outputs/samples/T-05.csv`
- PBC: PBC-08, PBC-11

Items to examine (risk indicators, not findings):

| # | Supplier | Payments | Window spend | Annualised estimate | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Glen Cleaning Company Ltd | 68 | £92,393.12 | £369,572.48 | premises | 68 |
| 2 | Swan Advocacy | 8 | £51,216.00 | £204,864.00 | grant | 8 |
| 3 | Solutions4Health Ltd | 4 | £45,277.62 | £181,110.48 | general_procurement | 4 |
| 4 | The Advocacy People (formerly SEAP) | 3 | £31,653.23 | £126,612.92 | grant | 3 |
| 5 | S RICHARDS T/AS K RICKETTS & S RICHARDS TAXIS | 8 | £17,144.00 | £68,576.00 | general_procurement | 8 |
| 6 | N Mehmood T/A A Star Executive Cars Ltd | 7 | £12,489.00 | £49,956.00 | general_procurement | 7 |
| 7 | Nadeem Mirza Trading as Parker Travels | 7 | £9,927.50 | £39,710.00 | general_procurement | 7 |
| 8 | POTTINGER'S HIRE SERVICE | 8 | £9,352.50 | £37,410.00 | general_procurement | 8 |

## R-03 · Payments to suppliers whose matched contract notices had all ended before the spend window

Score 9 (likelihood 3 × impact 3), Medium - High; auditor decision: approve. Sample size per test: 15 items.

Expected controls:

- **C-06** Before spend continues after a contract's end date, an extension provided for in the contract is approved by the S151 Officer [CPR-62, cl. App C row D], or a new contract is let through the App B route [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1] and recorded on the contract register [CPR-35, cl. 10.4].

### T-06 · tests C-06

**Test step.** For each sampled supplier, obtain the contract or contracts covering the window payments. Confirm whether the payments fall under an extension approved by the S151 Officer before the matched notice ended [CPR-62, cl. App C row D], or under a newer contract let through the App B route [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1]. A newer contract or approved extension may exist with no notice in the export [`$.tests.expired_notice_spend.caveats`].

**Sample.** Every supplier paid in the window whose matched notices had all ended before it [`$.tests.expired_notice_spend.counts.items`], largest first so the general-procurement suppliers are reached [`$.tests.expired_notice_spend.by_tag.general_procurement.items`].

- Flagged list: `outputs/analytics-full/expired_notice_spend.csv` (expired_notice_spend), 8 items; filter: none; 8 after the filter
- Order: `window_gbp` desc; method: top; size: 15 (score 9); only 8 available
- Drawn: 8 items, 60 transactions, £243,364.42; transactions in `outputs/samples/T-06.csv`
- PBC: PBC-01, PBC-04, PBC-12

Items to examine (risk indicators, not findings):

| # | Supplier | Payments | Window spend | Annualised estimate | Latest notice end | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Hope & Clay (Construction) Ltd | 1 | £91,306.75 | £365,227.00 | 2024-10-11 | general_procurement | 1 |
| 2 | BERKSHIRE MECHANICAL SERVICES | 45 | £68,040.00 | £272,160.00 | 2024-03-31 | premises | 45 |
| 3 | Berkshire Womens Aid | 2 | £52,997.50 | £211,990.00 | 2026-03-31 | grant | 2 |
| 4 | G7 BUSINESS SOLUTIONS LIMITED | 8 | £16,364.56 | £65,458.24 | 2023-01-18 | general_procurement | 8 |
| 5 | CACI Limited | 1 | £12,071.67 | £48,286.68 | 2025-04-30 | general_procurement | 1 |
| 6 | Morton Pattison Ltd | 1 | £1,102.00 | £4,408.00 | 2024-10-18 | general_procurement | 1 |
| 7 | Davis and Associates Consultancy Limited | 1 | £800.00 | £3,200.00 | 2023-09-30 | general_procurement | 1 |
| 8 | Tactical Facilities Management Ltd | 1 | £681.94 | £2,727.76 | 2023-09-30 | premises | 1 |

## R-04 · Spend-to-date against contract values and approved variations

Score 9 (likelihood 3 × impact 3), Medium - High; auditor decision: amend. Sample size per test: 15 items.

Expected controls:

- **C-07** Spend against each contract is monitored against the contract value on the contract register [CPR-08, cl. 5.2.1], and any variation that raises the value has prior written approval [CPR-63, cl. App C row E] or, above the Threshold, a board report [CPR-64, cl. App C row E] before the spend is incurred.

### T-07 · tests C-07

**Test step.** As the auditor's amendment asks, for each sampled contract obtain ledger spend-to-date over the contract life from the finance system and compare it with the contract value plus any approved variations [CPR-63, cl. App C row E] [CPR-64, cl. App C row E]. Obtain the variation approvals and establish whether the award value was an estimate, a maximum, net of VAT or covering other lots [`$.tests.spend_vs_award.caveats`]. The annualised estimate is used only to order the contracts for this comparison, not as the measure of spend against value [`$.tests.spend_vs_award.counts.items`].

**Sample.** The matched single-supplier contracts with an award value [`$.tests.spend_vs_award.counts.compared`], highest screening ratio first, so the contracts the annualised estimate flags [`$.tests.spend_vs_award.counts.items`] come first and the spend-to-date comparison also reaches unflagged contracts, as the auditor's amendment asks.

- Flagged list: `outputs/analytics-full/spend_vs_award.csv` (spend_vs_award), 20 items; filter: none; 20 after the filter
- Order: `ratio` desc; method: top; size: 15 (score 9)
- Drawn: 15 items, 55 transactions, £875,827.82; transactions in `outputs/samples/T-07.csv`
- PBC: PBC-13, PBC-04, PBC-14, PBC-15

Items to examine (risk indicators, not findings):

| # | Supplier | Window spend | Annualised estimate | Awarded value | Ratio | Notice | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | NEC SOFTWARE SOLUTIONS UK LIMITED | £314,383.57 | £1,257,534.28 | £615,540.00 | 6.1247 | RM6259/CL766 | general_procurement | 10 |
| 2 | BookingLab Limited | £24,000.00 | £96,000.00 | £173,000.00 | 3.8833 | IT-402-1498-P00001498 - AWARD | general_procurement | 1 |
| 3 | Exacom Systems Ltd | £12,105.85 | £48,423.40 | £50,358.00 | 3.8437 | G-Cloud 14 RM1557.14 | general_procurement | 1 |
| 4 | WCL UK Ltd (Trading as Everything ICT) | £102,882.78 | £411,531.12 | £407,558.59 | 3.0244 | P00001021 | general_procurement | 1 |
| 5 | SMS-Environmental Ltd | £7,758.91 | £31,035.64 | £26,021.66 | 2.3805 | IT-402-1599-P00001599 - AWARD | premises | 7 |
| 6 | Softcat Ltd | £11,005.00 | £44,020.00 | £57,907.00 | 2.279 | IT-402-1666-P00001666 - AWARD | general_procurement | 2 |
| 7 | IDOX SOFTWARE LTD | £51,226.41 | £204,905.64 | £714,533.00 | 2.0068 | P00000844 | general_procurement | 2 |
| 8 | TWO SAINTS LTD | £213,288.45 | £853,153.80 | £2,500,000.00 | 1.7061 | IT-402-1432-P00001432 - AWARD | general_procurement | 7 |
| 9 | Southern Communications Corporate Solutions Ltd | £11,492.23 | £45,968.92 | £303,131.96 | 1.0612 | P00001009 | general_procurement | 3 |
| 10 | School of Sexuality Education | £1,250.00 | £5,000.00 | £17,500.00 | 1.0114 | P00001196 | grant | 1 |
| 11 | Ricoh UK Ltd | £9,473.16 | £37,892.64 | £263,013.00 | 1.0082 | IT-402-1584-P00001584 - AWARD | general_procurement | 1 |
| 12 | Ubitricity Distributed Energy Systems UK Ltd | £18,675.00 | £74,700.00 | £425,375.00 | 0.702 | P00000883 | general_procurement | 1 |
| 13 | ELITE SECURITY GROUP | £10,178.25 | £40,713.00 | £175,000.00 | 0.6968 | IT-402-1200-P00001200 - AWARD | premises | 9 |
| 14 | INSIGHT DIRECT (UK) LTD | £46,075.33 | £184,301.32 | £1,915,881.33 | 0.577 | P00001042 | general_procurement | 6 |
| 15 | SWARCO SMART CHARGING LTD | £42,032.88 | £168,131.52 | £1,381,042.00 | 0.4866 | P00001146 | general_procurement | 3 |

## R-05 · Repeat payments of the same amount to the same supplier within days

Score 9 (likelihood 3 × impact 3), Medium - High; auditor decision: approve. Sample size per test: 15 items.

Expected controls:

- **C-08** Every purchase is supported by written or electronic evidence [CPR-32, cl. 10.1], so each payment matches a distinct invoice and the accounts payable duplicate check holds a repeat until it is confirmed [AUD-11].

### T-08 · tests C-08

**Test step.** For each sampled chain, obtain the invoices behind every payment and confirm whether each repeat is a distinct invoice for a distinct supply [CPR-32, cl. 10.1]. Where it is not, confirm whether the repeat was identified by the duplicate check and recovered or reversed, and obtain the evidence [`$.tests.duplicates.by_tag.general_procurement.gbp`]. Obtain the accounts payable duplicate-check report for the spend window, confirm that the groups of rows identical in all published columns [`$.tests.duplicates.counts.identical_rows_from_cleaning.groups`] appear in it, and record each group's resolution: distinct invoice, reversal or recovery.

**Sample.** The largest of the 50 general-procurement chains by repeat value [`$.tests.duplicates.by_tag.general_procurement.items`]; placement chains reflect weekly rates and are expected [`$.tests.duplicates.caveats`].

- Flagged list: `outputs/analytics-full/duplicates.csv` (duplicates), 684 items; filter: `tag` == general_procurement; 50 after the filter
- Order: `repeat_gbp` desc; method: top; size: 15 (score 9)
- Drawn: 15 items, 35 transactions, £542,579.56; transactions in `outputs/samples/T-08.csv`
- PBC: PBC-01, PBC-16, PBC-17

Items to examine (risk indicators, not findings):

| # | Supplier | First | Last | Payments | Amount | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | VolkerHighways Ltd | 2026-07-15 | 2026-07-17 | 2 | £101,925.86 | general_procurement | 2 |
| 2 | VolkerHighways Ltd | 2026-07-13 | 2026-07-16 | 2 | £54,241.36 | general_procurement | 2 |
| 3 | TWO SAINTS LTD | 2026-05-12 | 2026-05-13 | 2 | £27,147.69 | general_procurement | 2 |
| 4 | VolkerHighways Ltd | 2026-07-13 | 2026-07-16 | 2 | £17,882.35 | general_procurement | 2 |
| 5 | Roadside Technologies Ltd | 2026-07-13 | 2026-07-13 | 4 | £5,594.11 | general_procurement | 4 |
| 6 | BROADWAY CARS | 2026-07-13 | 2026-07-13 | 3 | £5,330.00 | general_procurement | 3 |
| 7 | Roadside Technologies Ltd | 2026-07-13 | 2026-07-13 | 2 | £9,103.64 | general_procurement | 2 |
| 8 | Pavillion Publishing and Media Ltd | 2026-05-13 | 2026-05-14 | 2 | £9,084.60 | general_procurement | 2 |
| 9 | BROADWAY CARS | 2026-05-27 | 2026-05-27 | 3 | £3,900.00 | general_procurement | 3 |
| 10 | BROADWAY CARS | 2026-05-12 | 2026-05-13 | 3 | £3,640.00 | general_procurement | 3 |
| 11 | SEISMIC SEWAGE SYSTEMS LTD | 2026-06-18 | 2026-06-18 | 2 | £5,360.00 | general_procurement | 2 |
| 12 | LOCAL GOVERNMENT PROPERTY CONSULTANTS (LGPC) | 2026-06-25 | 2026-06-25 | 2 | £4,925.00 | general_procurement | 2 |
| 13 | BRITISH TELECOM | 2026-06-17 | 2026-06-17 | 2 | £4,364.06 | general_procurement | 2 |
| 14 | FD TRAVELS LIMITED T/A SCHOOL EXPRESS | 2026-07-09 | 2026-07-14 | 2 | £4,018.00 | general_procurement | 2 |
| 15 | FD TRAVELS LIMITED T/A SCHOOL EXPRESS | 2026-05-06 | 2026-05-13 | 2 | £2,744.00 | general_procurement | 2 |

## R-06 · Social care placements without a recorded reason for the choice of provider

Score 4 (likelihood 2 × impact 2), Moderate; auditor decision: approve. Sample size per test: 10 items.

Expected controls:

- **C-09** For each social care placement or package, the reasons for the choice of provider are recorded on the case notes [CPR-65, cl. App C row F], and an App C exemption above the Threshold is approved by the relevant board [CPR-66, cl. App C note].

### T-09 · tests C-09

**Test step.** For each sampled placement supplier, select the largest payment for that supplier in samples/T-09.csv, obtain the case notes and confirm that the reasons for the choice of provider are recorded [CPR-65, cl. App C row F]. Confirm that the rate paid matches the agreed package, and where the arrangement's value is above the Threshold, obtain the board approval [CPR-66, cl. App C note]. Compare the selected payment with its invoice or payment schedule.

**Sample.** The highest-value of the 294 mainly-placement suppliers above the publication threshold [`$.tests.off_contract.counts.mainly_placement`], where App C row F applies [CPR-65, cl. App C row F].

- Flagged list: `outputs/analytics-full/off_contract.csv` (off_contract), 618 items; filter: `mainly_placement` == True; 294 after the filter
- Order: `window_gbp` desc; method: top; size: 10 (score 4)
- Drawn: 10 items, 1,294 transactions, £8,436,057.67; transactions in `outputs/samples/T-09.csv`
- PBC: PBC-18, PBC-19, PBC-20, PBC-21

Items to examine (risk indicators, not findings):

| # | Supplier | Payments | Window spend | Annualised estimate | Tag | Transactions |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | BUPA Care Services | 370 | £1,874,166.50 | £7,496,666.00 | placement | 370 |
| 2 | Affinity Trust Support Ltd | 263 | £1,098,336.76 | £4,393,347.04 | placement | 263 |
| 3 | Oaklands SEN School Berkshire Limited | 54 | £1,026,661.89 | £4,106,647.56 | placement | 54 |
| 4 | Amegreen Childrens Services | 27 | £750,437.33 | £3,001,749.32 | placement | 27 |
| 5 | Brighter Living Care Ltd | 74 | £747,183.47 | £2,988,733.88 | placement | 74 |
| 6 | Sukhbir Singh and Harvinder Singh T/A Calcot Services for… | 26 | £639,381.60 | £2,557,526.40 | placement | 26 |
| 7 | We Are The Care Company Ltd | 349 | £589,012.31 | £2,356,049.24 | placement | 349 |
| 8 | The Better Group Ltd | 26 | £588,490.08 | £2,353,960.32 | placement | 26 |
| 9 | Phoenix Child Care Limited -The Grange School | 25 | £567,708.85 | £2,270,835.40 | placement | 25 |
| 10 | VOYAGE CARE | 80 | £554,678.88 | £2,218,715.52 | placement | 80 |

## PBC list

Items to request from the council before fieldwork, derived from the test steps.

| Ref | Item | For tests | Risks |
| --- | --- | --- | --- |
| PBC-01 | Purchase orders and invoices for the sampled payments | T-01, T-02, T-03, T-10, T-06, T-08 | R-01, R-03, R-05 |
| PBC-02 | Quotation or tender records from the Procurement Portal, including invitations sent and responses received | T-01, T-03, T-10, T-04 | R-01, R-02 |
| PBC-03 | Contract notice published on the CDP, or the reason none was required | T-01, T-04 | R-01, R-02 |
| PBC-04 | Contract or framework call-off covering the sampled payments, where one exists | T-01, T-02, T-04, T-06, T-07 | R-01, R-02, R-03, R-04 |
| PBC-05 | Procurement-legislation Thresholds in force during the spend window, as published on the Procurement intranet page | T-01, T-04 | R-01, R-02 |
| PBC-06 | Key Decision record, board report and approval, or Executive decision, for the contract | T-02 | R-01 |
| PBC-07 | Tender records for the contract (invitation to tender, tenders received, evaluation and award report) | T-02 | R-01 |
| PBC-08 | The council's contract register as at the end of the spend window | T-04, T-05 | R-02 |
| PBC-09 | Purchasing Scheme advice and approval before award, where a framework was used | T-04 | R-02 |
| PBC-10 | Exception or waiver report and approval, where one was used | T-04 | R-02 |
| PBC-11 | Supplier master-file record (legal name, trading name and company number) for the sampled suppliers | T-05 | R-02 |
| PBC-12 | Extension approval by the S151 Officer, with the contract clause providing for extension | T-06 | R-03 |
| PBC-13 | Ledger spend-to-date over the contract life for the sampled contracts, from the finance system | T-07 | R-04 |
| PBC-14 | Variation approvals (prior written approval, or board report) for the sampled contracts | T-07 | R-04 |
| PBC-15 | Award report showing the basis of the award value (estimate, maximum, VAT treatment, lots) | T-07 | R-04 |
| PBC-16 | Accounts payable duplicate-check report for the spend window, with the resolution of each flagged pair | T-08 | R-05 |
| PBC-17 | Credit notes, recoveries or reversals for any repeat payment | T-08 | R-05 |
| PBC-18 | Case notes recording the reasons for the choice of provider for one placement per sampled supplier | T-09 | R-06 |
| PBC-19 | Agreed care package and rate for the sampled placement | T-09 | R-06 |
| PBC-20 | Board approval for App C exemptions above the Threshold, where applicable | T-09 | R-06 |
| PBC-21 | Invoice or payment schedule for the selected placement payment per sampled supplier | T-09 | R-06 |
