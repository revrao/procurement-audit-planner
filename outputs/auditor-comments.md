# Auditor decisions on the risk register

Register: `outputs/risk-register.md`, revision 1.

Reviewer: Revanth Rao
Date: 2026-10-07

For each risk write a **Decision**: `approve`, `amend` or `reject`.
- `amend`: say in Comment what to change (rating, wording, scope).
- `reject`: say in Comment why; the risk leaves the audit scope.
Avoid the `|` character in comments. Decisions here are kept when the register is rebuilt.

| Risk ID | Risk | Likelihood | Impact | Score | Band | Decision | Comment |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-01 | Requirements split, or payments pitched just under a quote or approval boundary | 3 | 3 | 9 | Medium - High | approve |  |
| R-02 | Contract and notice documentation to verify for high-value suppliers not matched in the notice export | 3 | 3 | 9 | Medium - High | amend | Keep the risk in scope, but frame it as a contract and notice documentation verification risk rather than evidence that required notices are missing, because the notice dataset has limited coverage. |
| R-03 | Payments to suppliers whose matched contract notices had all ended before the spend window | 3 | 3 | 9 | Medium - High | approve |  |
| R-04 | Spend-to-date against contract values and approved variations | 3 | 3 | 9 | Medium - High | amend | Keep the risk in scope, but compare actual spend-to-date against contract values and approved variations rather than relying primarily on the annualised three-month spend estimate. |
| R-05 | Repeat payments of the same amount to the same supplier within days | 3 | 3 | 9 | Medium - High | approve |  |
| R-06 | Social care placements without a recorded reason for the choice of provider | 2 | 2 | 4 | Moderate | approve |  |

## General comments

<!-- Scope, missing risks or anything else; kept when this file is rewritten. -->
