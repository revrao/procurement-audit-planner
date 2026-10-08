---
name: risk-assessment
description: The method for rating procurement risks for West Berkshire Council. The risk-assessor writes judgments to outputs/risk-ratings.json, citing [rule:ID], [metric:$.path] and [history:ID] and writing every figure as a {{$.path}} placeholder; build_register.py resolves citations, fills figures from analytics.json, scores on the council's 5x5 matrix (or the stated fallback), drops uncited risks, applies the likelihood rubric and the repeat-finding check, and renders outputs/risk-register.md plus the auditor's decision template outputs/auditor-comments.md. Also handles the post-gate revision. Loaded by the risk-assessor agent.
---

# risk-assessment

You judge; `build_register.py` (next to this file) computes. You never type a
figure, a score product, a band or a matrix label. You write
`outputs/risk-ratings.json`; the builder turns it into
`outputs/risk-register.md` and `outputs/auditor-comments.md`.

## Stop conditions

Stop and report, writing nothing, if `outputs/rules.json`,
`outputs/analytics.json` or `outputs/history.json` is missing, or
`analytics.json` has `self_check.passed` false. Exit code 2 from the builder
means the same: report its `STOP:` line.

## 1. Read the inputs (summaries only)

- `analytics.json`: read `tests.*.counts`, `by_tag`, `gbp_total`,
  `parameters`, `caveats`, `top20`, and the top-level `warnings`. Never open
  `outputs/analytics-full/`; the full lists are for the audit program.
- `history.json`: `audits_completed`, `follow_ups`, `advisory_reviews` (IDs
  `AUD-nn`, `FU-nn`, `ADV-nn`), `discrepancies` (`DIS-nn`), `gaps`
  (`GAP-nn`), and `scoring_method`.
- `rules.json`: `rules[].rule_id` (`CPR-nn`), clause, condition, and the
  `notes`.

Use `jq` or short Python one-liners to list paths and values; you need the
exact path for every figure you use.

## 2. Write `outputs/risk-ratings.json`

```json
{
  "assessor": "risk-assessor",
  "risks": [
    {
      "risk_id": "R-01",
      "title": "Purchases split or pitched just under a quote threshold",
      "likelihood": {
        "score": 4,
        "justification": "{{$.tests.split_purchases.by_tag.general_procurement.items}} general-procurement supplier groups … [metric:$.tests.split_purchases.by_tag.general_procurement.items] … [rule:CPR-13]",
        "below_rubric_reason": null,
        "uplift": null
      },
      "impact": {
        "score": 3,
        "column": "compliance",
        "financial_figure": null,
        "justification": "… [rule:CPR-50] … [history:AUD-01]"
      },
      "evidence": ["… {{$.tests.split_purchases.gbp_total}} [metric:$.tests.split_purchases.counts.items]"],
      "proposed_focus": "…"
    }
  ],
  "revision": null
}
```

- `risk_id`: `R-01`, `R-02`, … Once the auditor has seen an ID it never
  changes meaning.
- One risk per theme. Typical themes, each only if the evidence supports it:
  splitting / threshold avoidance, off-contract spend above the publication
  threshold, spend after notice expiry, spend beyond the award value,
  duplicate payments, gaps in contract records.

### Citations

| Tag | Resolves against | Example |
| --- | --- | --- |
| `[rule:ID]` | `rules.json` `rule_id` | `[rule:CPR-13]` |
| `[metric:$.path]` | a path in `analytics.json` | `[metric:$.tests.duplicates.counts.items]` |
| `[history:ID]` | any `id` in `history.json` | `[history:AUD-11]` |

Paths use `.key`, `[n]` and `['key with spaces or dots']`:
`$.tests.split_purchases.top20[0].sum_gbp`,
`$.cleaning.expectation_checks['Over500_2026_P02_-_published.xlsx'].rows`.

**Hard rule:** the likelihood justification and the impact justification each
need at least one citation that resolves. If either has none, the builder
drops the risk and lists it under "Excluded risks". Any other citation that
does not resolve, anywhere in a kept risk, fails the build. Every evidence line
needs a citation.

### Figures: placeholders only

Write every number as `{{$.path}}`. The builder fills it from analytics.json:
£ for amount keys (`gbp`, `amount`, `boundary`, …), thousands separators for
counts, percentages for `share` keys. Force a format with `|gbp`, `|int`,
`|pct`, `|num` or `|raw`, e.g. `{{$.rules_used.quote_threshold.value|gbp}}`.
Text values (supplier names) fill as they are. A placeholder that cannot be
filled fails the build. The builder warns about any figure typed in prose.
Clause, table and page numbers, risk and rule IDs, and years are allowed.
An annualised figure must be called an "annualised estimate" in the same text.

## 3. Likelihood: the rubric

Likelihood is how likely it is, over the next 12 months, that the control
weakness the indicators point to exists in the population (Table 2 frames
every level "within a 12 month period"). The builder works out the rubric level
from the **metrics cited in the likelihood justification**. Your score must
equal that level, or be lower with a cited `below_rubric_reason`. It may
never be higher.

| Level | Table 2 | Floor (checked mechanically on the cited metrics) | Meaning |
| --- | --- | --- | --- |
| 1 | Rare | no non-zero `$.tests.*` metric cited | rule-only risk: the rule exists, but the data shows no indicator (or the test could not run) |
| 2 | Unlikely | ≥1 non-zero `$.tests.*` metric | an indicator exists, but only in placements, grants, premises or agency spend, which have their own explanations (e.g. App C row F placements) |
| 3 | Likely | … and one in general procurement (path contains `general_procurement` or `non_placement`) | the indicator reaches ordinary purchasing |
| 4 | Almost Certain | … and non-zero metrics from ≥2 different tests | independent tests corroborate the same theme |
| 5 | Certain | never directly | only a 4 raised by the repeat-finding uplift |

To make two runs agree:
- Cite **every** non-zero metric that bears on the theme, from each test
  that bears on it, in the likelihood justification. Do not leave out a
  metric to get a lower score; use `below_rubric_reason` and say why.
- Use `by_tag.general_procurement.items` (or `counts.non_placement` for
  off_contract) as the general-procurement metric. Cite `counts.items` for
  the whole population.
- `$.tests.high_value_suppliers.*` is the population the notice-based tests
  run on, not an indicator. Cite it wherever it helps; it never counts
  toward the rubric level.
- Valid reasons to rate below the rubric level, each with a citation: a test
  caveat that explains most items (`$.tests.X.caveats`), a coverage limit in
  `$.warnings` (e.g. the notice export covers few suppliers), or a
  comparison band showing no excess (`ratio_band_to_comparison` near 1).

### Repeat-finding uplift (+1)

Add `"uplift": {"justification": "… [history:ID] …"}` only when a past audit
or follow-up on the **same theme** gave an adverse opinion: Limited, No or
Minimal Assurance, Weak, or an Unsatisfactory implementation opinion. The
builder rejects an uplift that cites no adverse `AUD-`/`FU-` item, and states
the uplift ("+1, base 3 → 4") in the register. Reasonable or Substantial
Assurance is never a repeat finding. Cite it in the impact or evidence text
instead.

## 4. Impact: Table 1

Pick the one Table 1 column (`impact.column`) the consequence falls in:
`financial`, `personal`, `assets`, `reputation`, `compliance`. The register
prints the Table 1 descriptor for your score and column, so it has to read
true.

- **compliance** is the usual column for procurement-rule risks:
  2 low possibility of legal challenge (below-threshold quote rules),
  3 reasonable possibility (quote/tender bands in App B; publication
  rules), 4 high possibility (spend above the procurement-legislation
  Threshold without a compliant procedure).
- **financial** only for a figure that is plausibly a loss (e.g. the value
  of duplicate-payment repeats), never total spend. Set
  `impact.financial_figure` to its `$.path`. The builder puts it in the
  Table 1 £ band and fails if your score differs.
- **reputation** when the consequence is public criticism (e.g. an external
  auditor finding, Table 1 level 3).

## 5. Indicator language

Risks describe **indicators to investigate**. Never write that the council, a
service or a supplier did wrong. The builder warns on words like fraud,
breach, deliberate and unlawful. Name suppliers only through `top20`
placeholders, and only as transactions to examine.

## 6. Build, fix, repeat

```
.venv/bin/python .claude/skills/risk-assessment/build_register.py
```

- `ERROR`: fix `risk-ratings.json` and re-run; nothing was written.
- `DROPPED`: the risk had no resolvable citation. Fix it if the evidence
  exists; otherwise leave it excluded and say so in your report.
- `WARNING`: remove typed figures and accusatory wording; resolve them all
  unless you can explain one in your report.
- Never edit the builder to get past a check.

What the builder does with the council's method: it reads the scales, the
Figure 1 matrix and the Table 4 bands from `history.json`, and computes
score = likelihood × impact, the Figure 1 label, the Table 4 band and the
Corporate Risk Register flag. Where the strategy states a threshold two ways
(`DIS-01`–`DIS-04`), it uses one, marks the other, and lists both in the
register header. A new scoring-method discrepancy without a declared
choice stops the build. If `scoring_method.status` is not `usable`, it uses
the 1–5 Very low…Very high fallback and says so in the header.

## 7. The auditor gate and the revision

The first build is revision 0. The auditor fills a Decision (`approve`,
`amend`, `reject`) and, for amend and reject, a Comment for every row of
`outputs/auditor-comments.md`. Rebuilding keeps what they wrote.

When re-run after the gate:
1. Read every decision and comment, and the general comments.
2. Change `risk-ratings.json` only as asked:
   - **approve**: change nothing on that risk;
   - **amend**: make the change the comment asks for. If it lowers the
     likelihood below the rubric level, `below_rubric_reason` cites the
     evidence and names the auditor's request;
   - **reject**: set `"status": "rejected"` and change nothing else;
   - add a risk only if the general comments ask for one.
3. Add the revision block:
   ```json
   "revision": {"number": 1, "changes": [
     {"risk_id": "R-03", "decision": "amend", "summary": "impact 3 → 4 as the auditor asked"}
   ]}
   ```
   with one entry per risk you changed. A new risk uses `"decision": "added"`.
4. Build. The builder diffs the ratings against the register the auditor
   reviewed. It fails if a decision is blank or unapplied, if anything
   changed that the auditor did not ask for (including a change to
   analytics/history/rules since the review), or if `changes` does not match
   the diff. It writes a "what changed" header and marks overrides ✱.

If you disagree with a decision, apply it anyway and put your view in that
entry's `summary`. The auditor decides.

## 8. Report

Under 200 words: the risks and their score/band, risks dropped and why, any
rating below the rubric level and why, uplifts applied, warnings left, and
(before the gate) that the auditor should complete
`outputs/auditor-comments.md`.
