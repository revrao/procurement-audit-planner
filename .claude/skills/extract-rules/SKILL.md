---
name: extract-rules
description: Converts West Berkshire Council's Contract Procedure Rules (data/contract-rules.pdf) into outputs/rules.json, with one entry per testable rule (clause, page, thresholds, required action, approver, verbatim quote), every untestable clause excluded with a reason, named-but-unstated thresholds as null parameters, and drafting problems as notes. Verified by verify_quotes.py. Invoked by the human as /extract-rules; not run by agents.
---

# extract-rules

Turn `data/contract-rules.pdf` into `outputs/rules.json`: the criteria every
later step (spend tests, risk register, audit program, QA) is built on. Every
entry must be checkable against the PDF by `verify_quotes.py`, which sits next
to this file.

## Stop conditions

Stop and report, writing nothing, if:
- `data/contract-rules.pdf` is missing, or `pdftotext`/`pdfinfo` is not on PATH;
- the PDF no longer matches the structure described below (different page
  count from 15, clause numbering that is not 1–11, appendices not A–C).
  Describe what changed and ask before adapting.

## 1. Extract the text

Write both renderings to the session scratchpad (never into `outputs/`):

```
pdftotext data/contract-rules.pdf <scratch>/rules-plain.txt
pdftotext -layout data/contract-rules.pdf <scratch>/rules-layout.txt
```

Pages are separated by form feeds (`\f`); page N is the Nth segment. Read the
whole of both files: the document is short, and every clause needs a decision.

Which rendering to quote from:
- **Numbered clauses**: either rendering. Layout keeps the clause numbers
  aligned and is easier to read.
- **Appendix tables**: plain. Layout interleaves cells from neighbouring
  columns on the same line, so a multi-line cell is only contiguous in the
  plain rendering.
- A word hyphenated across a line (e.g. `Call-` / `In`) loses its hyphen in
  plain mode (`CallIn`); quote it as printed (`Call-In`) and the verifier
  will match it in the layout rendering.

## 2. The document's structure

- **Pages 1–10: clauses 1–11**, numbered to four levels (`10.7.9.1`). Section
  headings (`6 Buying / procuring …`) and unnumbered sub-headings
  (`Advertising`, `Contract Value & Aggregation`) are not clauses.
- **Page 11: Appendix A**, delegated authority to award by Total Contract
  Value. Four unlabelled bands → cite as `App A row 1` … `App A row 4`, in
  printed order.
- **Pages 12–13: Appendix B**, the quote/tender bands. Rows labelled A, B1,
  B2, C, D → `App B row A`, `App B row B1`, …. Columns: Total Value
  (exclusive of VAT), Award Procedure, Advertising requirements. Footnotes
  `*`, `**`, `***`, `****` follow the table on page 13 → cite as
  `App B note *` etc.
- **Pages 14–15: Appendix C**, exclusions from competition, rows A–F →
  `App C row A` …; each row pairs a Circumstance with a Written record and
  approval. The closing sentence on page 15 ("In the interests of clarity
  …") → `App C note`.
- **Noise, never quoted**: the page footer `$3inav0bz.docx N`, the
  placeholder title `Part []`, and bullet glyphs (U+F0B7).

## 3. Decide: rule or excluded

Go through the clauses in printed order. Every numbered clause and every
appendix row ends up either as (part of) a rule or in `excluded`. The verifier
checks this against the clause list it reads from the PDF.

A clause is a **testable rule** when an auditor could check a transaction,
contract or record against it. It must state at least one of:
- a **threshold**: a value band that triggers or relaxes a requirement;
- a **required action** that leaves a checkable record (quotes sought,
  notice published, report written, approval recorded, contract sealed);
- an **approver**: who must authorise.

Otherwise **exclude** it with a one-line reason (≤200 characters), for
example: definition, statement of purpose, legal background, advice to seek
guidance without a recorded outcome, or out of procurement scope (e.g.
sealing a mortgage). Untestable or ambiguous clauses are also excluded,
never guessed into rules. Consecutive excluded clauses with the same reason
may share an entry as a range, `"11.12–11.14"`. A range covers exactly the
clauses printed between its ends, inclusive. Sub-clauses printed after the
last end are not covered, so end the range on the last sub-clause. A clause
named on its own, as a rule or a single exclusion, also covers its
sub-clauses.

Granularity:
- One entry per rule, not per sentence. A parent clause whose sub-clauses
  together make one requirement (e.g. a list of things every waiver must
  have) can be one rule citing the parent. A sub-clause that sets its own
  band or approver is its own rule.
- One appendix row → one rule per testable column. App B row B1's award
  procedure and its advertising requirement are two rules.
- A clause appears in `rules` or `excluded`, never both.
- Number rules `CPR-01`, `CPR-02`, … in printed order, with no gaps.

## 4. Fields of a rule

```json
{
  "rule_id": "CPR-07",
  "clause": "App B row B1",
  "page": 12,
  "type": "threshold",
  "scope": ["goods", "services"],
  "condition": "goods or services contract, total value £25,000 or more and less than the Threshold",
  "threshold_low": 25000,
  "threshold_low_inclusive": true,
  "threshold_low_param": null,
  "threshold_high": null,
  "threshold_high_inclusive": false,
  "threshold_high_param": "THRESHOLD_GOODS_SERVICES",
  "required_action": "send invitations to quote via the Procurement Portal to at least three appropriate sources",
  "approver": null,
  "evidence_source": "Procurement Portal invitation-to-quote records",
  "verbatim_quote": "…exact text from page 12…"
}
```

This example only shows the shape. Take every value from the PDF.

| Field | Rule |
| --- | --- |
| `clause` | A clause number exactly as printed (`7.4.2`) or an appendix ID from section 2. One clause, not a range. |
| `page` | The PDF page the quote is on. If the quote crosses a page break, add `page_end` (= `page` + 1). |
| `type` | `threshold` (a value band decides the procedure), `approval` (who authorises is the point), `requirement` (an action or record, whatever the value), `anti-avoidance` (no splitting / disaggregation to dodge the rules). |
| `scope` | Subset of `goods`, `services`, `works`, `concessions`, `light_touch`, or `["all"]` alone. Use what the clause or row says; if it names no contract type, `["all"]`. |
| `condition` | One plain-English line: when the rule applies. |
| `threshold_*` | See section 5. All six fields are always present. |
| `required_action` | What must be done, in the PDF's terms; null if the rule is only an approval. |
| `approver` | The role(s) as printed ("S.151 Officer and Monitoring Officer"); null if none. |
| `evidence_source` | The record an auditor would inspect to test the rule. Prefer a record the PDF names (Procurement Portal, CDP notice, Contract Register, exception report, written report); otherwise the obvious one. |
| `verbatim_quote` | Contiguous text copied exactly from the stated page. No ellipses and no stitching of separate passages. Line breaks and spacing don't matter, because the verifier collapses whitespace and treats curly and straight quotes, and en/em dashes and hyphens, as equal. Must contain every £ amount used in `threshold_low`/`threshold_high`. |

A rule must have at least one of a threshold, a `required_action`, or an
`approver`. `type: threshold` needs a threshold; `type: approval` needs an
approver.

## 5. Thresholds: as printed

Record each band boundary exactly as the PDF prints it. Don't shift it to make
bands meet.

| Printed wording | Value | `_inclusive` |
| --- | --- | --- |
| "above £X", "over £X", "more than £X", "exceeds £X", "in excess of £X" | X (low) | false |
| "£X or more" | X (low) | true |
| "less than £X", "below £X" | X (high) | false |
| "up to £X" | X (high) | true, and add a `notes` entry if the inclusive/exclusive reading matters |

- Amounts are GBP integers (`500000`, and £2.5million → `2500000`). If the PDF
  prints pence, keep them exactly (`24999.99`). Never round.
- No lower bound → `threshold_low` null and `threshold_low_inclusive` null
  (same for the upper bound).
- A boundary the PDF names without a figure ("the Threshold", "the relevant
  Threshold", "the relevant Procurement Legislation financial threshold")
  goes in `threshold_low_param`/`threshold_high_param`, with the value null.
  Value and param are never both set.

## 6. Parameters: named, never filled in

```json
"parameters": {
  "THRESHOLD_GOODS_SERVICES": {
    "value": null,
    "defined_in": "1.4",
    "description": "relevant Threshold for Goods & Services contracts under the applicable Procurement Legislation; published on the Procurement intranet, not in this PDF"
  }
}
```

- Declare one parameter per threshold category the PDF distinguishes
  (see clause 1.4 and App B note `***`), named UPPER_SNAKE_CASE.
- `value` is always null. The PDF doesn't state these figures. Don't fill
  them in from memory, from legislation or from any other source. Someone
  enters them later from the intranet page.
- Every parameter a rule uses must be declared. Where the PDF says "the
  relevant Threshold" without saying which, use the parameter matching the
  rule's `scope`, and record the ambiguity in `notes`.

## 7. Notes: contradictions and drafting gaps

`notes` records problems in the PDF itself, for the auditor and the risk
assessor. Report them; don't resolve them.

```json
{"clauses": ["6.15", "App B row A"], "kind": "contradiction", "note": "one line on what conflicts"}
```

`kind` is `contradiction`, `drafting-gap` or `ambiguity`. `clauses` cites
real clause IDs. Look in particular for:
- bands that overlap, or leave a value range with no rule (compare Appendix
  A, Appendix B and clauses 4.3 and 7.2–7.4 against each other);
- inconsistent value bases (VAT inclusive vs exclusive, total vs annual);
- lists of threshold categories that differ between clauses and footnotes;
- conflicting statements of who may approve or waive;
- placeholders (`[]`), broken cross-references, mis-numbered clauses or
  headings numbered as clauses, sentences that don't parse.

## 8. Write and verify

The top level of `outputs/rules.json` is one object:

```json
{
  "source": {"file": "data/contract-rules.pdf", "sha256": "<shasum -a 256>", "pages": 15},
  "parameters": { },
  "rules": [ ],
  "excluded": [ {"clause": "1.1", "reason": "statutory background; no requirement"} ],
  "notes": [ ]
}
```

Then run, from the project root:

```
.venv/bin/python .claude/skills/extract-rules/verify_quotes.py outputs/rules.json
```

Fix every `ERROR` and re-run until it prints `PASS`. Resolve `WARNING`s
(an unused parameter) or explain them in your report. Never edit the verifier
to make a check pass.

## 9. Report

Tell the user, in under 200 words:
- how many rules (by type), excluded entries, parameters and notes;
- that the verifier passed;
- the notes marked `contradiction`, one line each;
- that the parameter values are null and must be entered from the
  Procurement intranet page before the spend tests run.
