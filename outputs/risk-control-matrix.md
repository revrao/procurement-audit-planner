# Risk-control matrix: procurement audit, West Berkshire Council

Built 2026-10-08 21:31 UTC by `build_pack.py` from `outputs/audit-plan.json` and register revision 1; every figure the builder computed is in `outputs/pack-figures.json`.

*Results are risk indicators to investigate, not findings.* Nothing in this pack is a finding against the council, a department or a supplier; sampled items are flagged for examination.

| Risk | Score | Expected control | Tested by |
| --- | --- | --- | --- |
| R-01: Requirements split, or payments pitched just under a quote or approval boundary | 9 (Medium - High) | **C-01** Before a purchase route is chosen, the officer estimates the total value of the requirement and does not split or disaggregate it to avoid the Rules [CPR-13, cl. 6.16], and documents the procurement's progress [CPR-31, cl. 9.3]. | T-01, T-02, T-10 |
| R-01: Requirements split, or payments pitched just under a quote or approval boundary | 9 (Medium - High) | **C-02** Where the aggregated requirement reaches the quote threshold, at least three quotes are invited through the Procurement Portal and a contract notice is published [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1] [CPR-53, cl. App B row B2] [CPR-54, cl. App B row B2]; below it, at least one quote is sought [CPR-50, cl. App B row A]. Where the aggregated value exceeds the relevant Threshold, a written report is approved by the relevant board [CPR-47, cl. App A row 2]. | T-01, T-03, T-10 |
| R-01: Requirements split, or payments pitched just under a quote or approval boundary | 9 (Medium - High) | **C-03** Where the aggregated requirement reaches the App A approval boundaries, the award is treated as a Key Decision with a board-approved written report or Executive approval [CPR-04, cl. 4.3] [CPR-48, cl. App A row 3] [CPR-49, cl. App A row 4], and works above the App B row C band go to full competitive tender with a Portal advert [CPR-55, cl. App B row C] [CPR-56, cl. App B row C]. | T-02 |
| R-02: Contract and notice documentation to verify for high-value suppliers not matched in the notice export | 9 (Medium - High) | **C-04** Every contract award is notified and recorded on the Council Contract Register with its value, duration and supplier [CPR-35, cl. 10.4] [CPR-08, cl. 5.2.1], and contracts in Appendix B are in writing in an approved form [CPR-33, cl. 10.2]. | T-04, T-05 |
| R-02: Contract and notice documentation to verify for high-value suppliers not matched in the notice export | 9 (Medium - High) | **C-05** A contract at or above the publication threshold is let through the App B route, with invitations to at least three sources and a contract notice on the CDP [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1] [CPR-53, cl. App B row B2] [CPR-54, cl. App B row B2], or through a Purchasing Scheme with advice and approval obtained before award [CPR-28, cl. 8.2] [CPR-61, cl. App C row C], or under a documented exception [CPR-26, cl. 7.5]. Above the procurement-legislation Threshold, a full competitive tender is run and an advert placed on the CDP [CPR-57, cl. App B row D] [CPR-58, cl. App B row D]. | T-04 |
| R-03: Payments to suppliers whose matched contract notices had all ended before the spend window | 9 (Medium - High) | **C-06** Before spend continues after a contract's end date, an extension provided for in the contract is approved by the S151 Officer [CPR-62, cl. App C row D], or a new contract is let through the App B route [CPR-51, cl. App B row B1] [CPR-52, cl. App B row B1] and recorded on the contract register [CPR-35, cl. 10.4]. | T-06 |
| R-04: Spend-to-date against contract values and approved variations | 9 (Medium - High) | **C-07** Spend against each contract is monitored against the contract value on the contract register [CPR-08, cl. 5.2.1], and any variation that raises the value has prior written approval [CPR-63, cl. App C row E] or, above the Threshold, a board report [CPR-64, cl. App C row E] before the spend is incurred. | T-07 |
| R-05: Repeat payments of the same amount to the same supplier within days | 9 (Medium - High) | **C-08** Every purchase is supported by written or electronic evidence [CPR-32, cl. 10.1], so each payment matches a distinct invoice and the accounts payable duplicate check holds a repeat until it is confirmed [AUD-11]. | T-08 |
| R-06: Social care placements without a recorded reason for the choice of provider | 4 (Moderate) | **C-09** For each social care placement or package, the reasons for the choice of provider are recorded on the case notes [CPR-65, cl. App C row F], and an App C exemption above the Threshold is approved by the relevant board [CPR-66, cl. App C note]. | T-09 |

## Rule coverage

Every rule in `outputs/rules.json` (66) is cited by an in-scope risk, a control or a test, or is listed as not tested with the planner's reason.

| Rule | Clause | Condition | Cited by | Not tested: reason |
| --- | --- | --- | --- | --- |
| CPR-01 | 3.5 | service contract with estimated value exceeding the Threshold for Goods & Services |  | Social value consideration is not visible in payment data; outside the approved risks. |
| CPR-02 | 4.1 | every contract |  | Recorded decisions for every contract are outside the approved risks; approval is tested only at the App A boundaries. |
| CPR-03 | 4.2 | every contract |  | Budget provision is not visible in payment data; outside the approved risks. |
| CPR-04 | 4.3 | contract award with a value over £500,000 | C-03, T-02 |  |
| CPR-05 | 4.4 | Service Director without delegated authority to enter into the contract |  | Delegated authority of individual Service Directors is outside the approved risks. |
| CPR-06 | 5.1.1 | expenditure exceeding £500 |  | Publication of spend is the source of the data itself, not a tested control. |
| CPR-07 | 5.2 | invitation to tender for goods and/or services with a value exceeding £5,000 |  | Publication of invitations to tender is outside the approved risks. |
| CPR-08 | 5.2.1 | every contract in progress or awarded | C-04, T-04, T-05, C-07 |  |
| CPR-09 | 5.3 | contract information held by service areas |  | Monthly reporting of contract information to boards is outside the approved risks. |
| CPR-10 | 6.8 | contract opportunity advertised by a Service Director |  | Portal advertising of opportunities is covered through the App B route rules; this clause is not tested separately. |
| CPR-11 | 6.10 | contract opportunity above the relevant Procurement Legislation threshold (not a Further Competition under a compliant Framework) |  | Depends on the procurement-legislation Threshold, which is null in the rules extract. |
| CPR-12 | 6.14 | every CDP notice |  | Approval of each CDP notice by the named officer is outside the approved risks. |
| CPR-13 | 6.16 | any contract | R-01, C-01, T-01, T-02, T-03, T-10 |  |
| CPR-14 | 6.19 | contract with an estimated value more than the appropriate Threshold |  | Depends on the procurement-legislation Threshold, which is null in the rules extract. |
| CPR-15 | 6.20 | every electronic tender |  | Tender submission and storage is not visible in payment data; outside the approved risks. |
| CPR-16 | 6.21 | tender received after the opening time and date |  | Late tender handling is not visible in payment data; outside the approved risks. |
| CPR-17 | 6.22 | every tender submitted on the Procurement Portal |  | Electronic tender opening is not visible in payment data; outside the approved risks. |
| CPR-18 | 6.24 | every quote and tender |  | Evaluation criteria are not visible in payment data; outside the approved risks. |
| CPR-19 | 6.26 | every contract award not on the most advantageous / best value basis |  | Award basis is not visible in payment data; outside the approved risks. |
| CPR-20 | 7.2 | exception or waiver of competition for a contract with a value of more than £24,999.99 |  | Grounds for exceptions are outside the approved risks; an exception met in T-04 is recorded as an explanation only. |
| CPR-21 | 7.2.2 | exception under the discretion ground |  | Discretionary exceptions are outside the approved risks. |
| CPR-22 | 7.3 | any waiver or exception to these Rules |  | Waiver approval is outside the approved risks. |
| CPR-23 | 7.4.1 | exception for a contract up to the Threshold |  | Exception approval tiers depend on the Threshold, which is null in the rules extract. |
| CPR-24 | 7.4.2 | exception for a contract above the relevant Threshold and up to £500,000 |  | Exception approval tiers depend on the Threshold, which is null in the rules extract. |
| CPR-25 | 7.4.3 | exception for a contract over £500,000 |  | Exception approval for large contracts is outside the approved risks. |
| CPR-26 | 7.5 | every exception or waiver | C-05, T-04 |  |
| CPR-27 | 7.5.3 | every exception or waiver |  | S151 Officer consideration of exceptions is outside the approved risks. |
| CPR-28 | 8.2 | use of a Purchasing Scheme | C-05 |  |
| CPR-29 | 9.1 | contract awarded above the Threshold and subject to the Procurement Legislation |  | Depends on the procurement-legislation Threshold, which is null in the rules extract. |
| CPR-30 | 9.2 | every 9.1 report |  | Retention of procurement reports depends on CPR-29, which is not tested. |
| CPR-31 | 9.3 | every procurement, regardless of value | C-01 |  |
| CPR-32 | 10.1 | every purchase | C-08, T-08 |  |
| CPR-33 | 10.2 | contracts detailed in Appendix B | C-04, T-04 |  |
| CPR-34 | 10.3 | every sealed contract |  | Retention of sealed contracts by Legal Services is outside the approved risks. |
| CPR-35 | 10.4 | every contract award | C-04, C-06 |  |
| CPR-36 | 10.5 | every contract |  | Standard contract clauses are not visible in payment data; outside the approved risks. |
| CPR-37 | 10.6 | amended Standard Form of Agreement |  | Amendment of the standard form is outside the approved risks. |
| CPR-38 | 10.7 | every contract (where appropriate) |  | Minimum contract clauses are not visible in payment data; outside the approved risks. |
| CPR-39 | 10.7.7 | every contract |  | Data protection impact assessments are outside the approved risks. |
| CPR-40 | 11.1 | any relaxation of full indemnities |  | Indemnity relaxation is outside the approved risks. |
| CPR-41 | 11.2 | contract estimated to exceed £500,000 for works (or supplies/services by a date or dates) |  | Performance bonds are outside the approved risks. |
| CPR-42 | 11.3 | contract with a performance bond |  | Performance bonds are outside the approved risks. |
| CPR-43 | 11.4 | 11.2 contract where a performance bond is not considered necessary |  | Performance bond risk assessments are outside the approved risks. |
| CPR-44 | 11.5 | every contract |  | Contract risk and insurance are outside the approved risks. |
| CPR-45 | 11.11 | contract above the Threshold |  | Depends on the procurement-legislation Threshold, which is null in the rules extract. |
| CPR-46 | App A row 1 | Total Contract Value up to the relevant Threshold |  | Depends on the relevant Threshold, which is null in the rules extract. |
| CPR-47 | App A row 2 | Total Contract Value above the relevant threshold and less than £500,000 | C-02, T-01 |  |
| CPR-48 | App A row 3 | Total Contract Value above £500,000 and less than £2.5million | R-01, C-03, T-02 |  |
| CPR-49 | App A row 4 | Total Contract Value £2.5million or more | C-03, T-02 |  |
| CPR-50 | App B row A | Total Value (excl. VAT) above £1,000 and less than £25,000 | R-01, C-02, T-03, T-10 |  |
| CPR-51 | App B row B1 | goods/services, Total Value (excl. VAT) £25,000 or more and less than the Threshold | R-01, R-02, R-03, C-02, T-01, T-03, C-05, C-06, T-06 |  |
| CPR-52 | App B row B1 | goods/services, Total Value (excl. VAT) £25,000 or more and less than the Threshold | R-01, R-02, R-03, C-02, T-01, T-03, C-05, T-04, C-06, T-06 |  |
| CPR-53 | App B row B2 | works, concession or light touch, Total Value (excl. VAT) £25,000 or more and less than £500,000 | C-02, C-05 |  |
| CPR-54 | App B row B2 | works, concession or light touch, Total Value (excl. VAT) £25,000 or more and less than £500,000 | R-02, C-02, C-05 |  |
| CPR-55 | App B row C | works, concession or light touch, Total Value (excl. VAT) above £500,000 and less than the Threshold | C-03, T-02 |  |
| CPR-56 | App B row C | works, concession or light touch, Total Value (excl. VAT) above £500,000 and less than the Threshold | C-03 |  |
| CPR-57 | App B row D | Total Value (excl. VAT) above the Threshold | C-05, T-04 |  |
| CPR-58 | App B row D | Total Value (excl. VAT) above the Threshold | C-05, T-04 |  |
| CPR-59 | App C row A | contract excluded under the Procurement Legislation (no competition) |  | Excluded contracts are not identifiable in payment data; outside the approved risks. |
| CPR-60 | App C row B | contract governed by the Provider Selection Regime (PSR) |  | Provider Selection Regime contracts are not identifiable in payment data; outside the approved risks. |
| CPR-61 | App C row C | award under a Purchasing Scheme with no further competition | C-05, T-04 |  |
| CPR-62 | App C row D | extension of an existing contract that provides for extension | R-03, C-06, T-06 |  |
| CPR-63 | App C row E | permitted variation of scope, contract value below the Threshold | R-04, C-07, T-07 |  |
| CPR-64 | App C row E | permitted variation of scope, contract value greater than the Threshold | R-04, C-07, T-07 |  |
| CPR-65 | App C row F | social care placement or package listed in a)-f) | R-06, C-09, T-09 |  |
| CPR-66 | App C note | contract under an Appendix C exemption with annual or total value more than the Threshold | C-09, T-09 |  |
