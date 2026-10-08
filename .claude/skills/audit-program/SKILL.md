---
name: audit-program
description: The method for turning West Berkshire Council's auditor-approved procurement risks into an audit program. The planner writes judgments to outputs/audit-plan.json (per approved risk, expected controls citing [rule:ID], test steps citing a rule or [metric:$.path], a sample recipe over a flagged list in outputs/analytics-full/, and the PBC items each test needs; memo text with {{$.path}} placeholders for every figure). build_pack.py checks the auditor gate, resolves every citation, draws every sample deterministically and sized by risk score, verifies each transaction against spend_clean.csv, checks every control has a test and every rule is cited or listed as not tested, and renders planning-memo.md, risk-control-matrix.md, audit-program.md (ending with the PBC list), outputs/samples/T-*.csv and pack-figures.json. Loaded by the planner agent.
---

# audit-program

You judge; `build_pack.py` (next to this file) computes. You never type a
figure, a sample size, a count or a transaction. You write
`outputs/audit-plan.json`; the builder turns it into the planning pack.
Work only on risks the auditor approved.

## Stop conditions

```
.venv/bin/python -I scripts/test_build_pack.py                         # builder healthy: must PASS
.venv/bin/python -I .claude/skills/audit-program/build_pack.py --gate  # auditor gate: must PASS
```

Stop and report, writing nothing, if either fails. `GATE FAILED` means a
register risk has no decision, the register is not yet a revision, or the
ratings, inputs or decisions changed after the revision: the auditor
completes `outputs/auditor-comments.md` and the risk-assessor rebuilds the
register. Exit code 2 from the builder (`STOP:`) means an input is missing.

## 1. Read the inputs (summaries only)

- `outputs/risk-register.md`: the in-scope risks, their scores, evidence and
  proposed focus. `--gate` prints the scope; rejected risks stay out.
- `outputs/auditor-comments.md`: decisions, comments (an amend comment shapes
  the test), general comments.
- `outputs/risk-ratings.json`: the citations behind each risk.
- `outputs/rules.json`: `rules[].rule_id`, clause, condition,
  required_action, approver.
- `outputs/analytics.json`: `tests.*.counts`, `by_tag`, `parameters`,
  `caveats`, `full_list`, `rules_used`.
- `outputs/analytics-full/*.csv`: **column names only** (`head -3`). Never
  load a full list into context; the builder reads them.

## 2. Write `outputs/audit-plan.json`

```json
{
  "planner": "planner",
  "register_revision": 1,
  "memo": {
    "objective": "…",
    "background": "… {{$.tests.split_purchases.counts.items}} … [metric:$.tests.split_purchases.counts.items]",
    "approach": "… {{$.pack.totals.sampled_items}} items …",
    "limitations": "… [metric:$.tests.split_purchases.caveats]"
  },
  "risks": [
    {
      "risk_id": "R-01",
      "controls": [
        {"control_id": "C-01", "control": "Requirements are aggregated before the route is chosen [rule:CPR-13]."}
      ],
      "tests": [
        {
          "test_id": "T-01",
          "controls": ["C-01"],
          "step": "For each sampled group, establish whether the payments are one requirement … [rule:CPR-13] [metric:$.tests.split_purchases.by_tag.general_procurement.items]",
          "sample": {
            "file": "split_purchases.csv",
            "filter": [{"column": "tag", "op": "==", "value": "general_procurement"},
                       {"column": "boundary", "op": "==", "value": "{{$.rules_used.quote_threshold.value}}"}],
            "sort": [{"column": "sum_gbp", "order": "desc"}],
            "method": "top",
            "size": null,
            "rationale": "The largest general-procurement groups crossing the quote threshold [metric:…]."
          },
          "pbc": ["Purchase orders and invoices for the sampled payments"]
        }
      ]
    }
  ],
  "rules_not_tested": [
    {"rule_id": "CPR-01", "reason": "Social value consideration is not visible in payment data; outside the approved risks."}
  ]
}
```

- `register_revision`: the revision `--gate` reports.
- `risks`: exactly the approved risks (decision `approve` or `amend`), each
  once. A missing approved risk, a rejected risk or an unknown ID fails the
  build. For an `amend`, the tests must do what the auditor's comment asks.
- `control_id` `C-01`… and `test_id` `T-01`… are unique across the plan.
- **Expected control**: what should happen if the rule is followed. Each
  cites at least one `[rule:ID]`. A risk with no CPR rule of its own (e.g.
  duplicate payments) rests on the nearest rule that governs the evidence or
  the route (e.g. clause 10.1 written evidence of every purchase).
- **Test step**: what the auditor does with each sampled item and what
  evidence answers it. Cites at least one `[rule:ID]` or `[metric:$.path]`.
  `controls` lists the control(s) it tests; every control needs a test.
- **PBC**: the documents the test needs from the council, one per string.
  The builder merges identical items across tests and numbers them PBC-01….
- `rules_not_tested`: every rule in rules.json that no in-scope risk, control
  or test cites, each with a one-line reason (outside the approved risks,
  not observable in payment data, a threshold null in rules.json, …). A rule
  both cited and listed fails the build.

### Citations

As in the risk-assessment skill: `[rule:ID]` (rules.json), `[metric:$.path]`
(analytics.json), `[history:ID]` (history.json). Every citation must resolve.

### Figures: placeholders only

Every number in any text is a placeholder. `{{$.path}}` fills from
analytics.json; `{{$.pack.…}}` fills from the figures the builder computes,
format suffixes `|gbp`, `|int`, `|pct`, `|num`, `|raw` as in the
risk-assessment skill. A typed figure fails the build here (not a warning).
An annualised figure must be called an "annualised estimate" in the same
text.

| `$.pack` path | Value |
| --- | --- |
| `scope.in_scope`, `scope.rejected`, `scope.risks_in_register`, `scope.register_revision` | the approved scope |
| `risks.R-01.score`, `.likelihood`, `.impact`, `.sample_size_per_test`, `.controls`, `.tests`, `.sampled_items`, `.sampled_transactions`, `.sampled_gbp` | per risk |
| `tests.T-01.population_items`, `.after_filter`, `.target_size`, `.sampled_items`, `.sampled_transactions`, `.sampled_gbp` | per test |
| `totals.controls`, `.tests`, `.sampled_items`, `.sampled_transactions`, `.sampled_gbp`, `.pbc_items` | the pack |
| `rules.total`, `.cited`, `.not_tested` | rule coverage |

## 3. Samples: the recipe

Samples are **targeted**: drawn from the items a spend-analytics test
flagged, never from the whole spend file.

| Field | Meaning |
| --- | --- |
| `file` | a test's `full_list` in `outputs/analytics-full/` (`threshold_clustering.csv`, `split_purchases.csv`, `duplicates.csv`, `high_value_suppliers.csv`, `off_contract.csv`, `expired_notice_spend.csv`, `spend_vs_award.csv`) |
| `filter` | list of `{column, op, value}`, all must hold. `op`: `==` `!=` `>` `>=` `<` `<=` `in` `not_in` `contains`. `value` may be a whole `"{{$.path}}"` into analytics.json, e.g. a threshold |
| `sort` | list of `{column, order: asc\|desc}`; ties keep file order, blanks last |
| `method` | `top` (first n after sorting) or `systematic` (evenly spaced through the sorted list) |
| `size` | `null` = the size for the risk's score. A larger size needs `size_reason`; smaller is not allowed |
| `rationale` | why these items, with a citation |

Size by score (`SAMPLE_SIZES` in the builder, on the council's Table 4
ranges), items per test:

| Score | Table 4 band | Items |
| --- | --- | --- |
| 15-25 | Extreme | 25 |
| 8-12 | Medium - High | 15 |
| 4-6 | Moderate | 10 |
| 1-3 | Low | 5 |

An item is one row of the file: a payment, a split group, a duplicate chain
or a supplier. The builder expands each item to its transactions, checks
every transaction exists in `spend_clean.csv` and that the item's supplier,
payment count and total reconcile to them, and writes them to
`outputs/samples/<test_id>.csv`. If the filter leaves fewer items than the
size, all are taken and the pack says so.

Choosing recipes:
- Filter to `general_procurement` (or `mainly_placement` False) unless the
  risk is about placements; placements have their own explanations (App C
  row F).
- Use `top` by value to cover the most money; use `systematic` when the
  register says the signal is spread thin or a comparison band shows no
  excess.
- Off-contract items: only suppliers above the publication threshold; the
  test says nothing about smaller suppliers.

## 4. Indicator language

The pack describes **risk indicators to investigate**. Never write that the
council, a service or a supplier did wrong. Write test steps as "establish
whether", "confirm", "obtain". Words like fraud, breach, deliberate and
unlawful fail the build. Suppliers appear only as sampled items to examine.

## 5. Build, fix, repeat

```
.venv/bin/python -I .claude/skills/audit-program/build_pack.py
```

- `ERROR`: fix `audit-plan.json` and re-run; nothing was written.
- Never edit the builder, its tests, the register or any input to get past
  a check.

The builder writes `outputs/planning-memo.md` (your memo sections around
its scope, sampling and rule-coverage sections), `outputs/risk-control-matrix.md`
(risk → control → tests, then every rule's coverage),
`outputs/audit-program.md` (per risk: controls, test steps, recipe, the
items to examine, ending with the PBC list), `outputs/samples/T-*.csv` and
`outputs/pack-figures.json` (every figure it computed and every placeholder
it filled, for the QA number check).

## 6. Report

Under 200 words: risks planned, controls and tests, items and transactions
sampled (from the builder's `BUILT` line), rules not tested, and anything the
auditor should look at.
