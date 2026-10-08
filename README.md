# Procurement Audit Planner (West Berkshire Council)

An agentic system built with Claude Code that plans an internal audit of
procurement at West Berkshire Council using only public data. It turns the
council's Contract Procedure Rules into testable rules, analyses the whole
spend population against them, adds in past internal-audit history, rates the
risks on the council's own scoring scale, and produces a cross-checked audit
planning pack. A human auditor approves it at two gates.

The full design specification is in [`CLAUDE.md`](CLAUDE.md).

## What it does

Planning a procurement audit by hand is slow, inconsistent, and depends on a
small random sample of payments. This system:

1. **Extracts every testable rule** from the Contract Procedure Rules, each
   with its clause, page and a verbatim quote (`outputs/rules.json`: 66 rules,
   29 clauses excluded with a reason).
2. **Analyses the full spend population** of three monthly "Expenditure over
   £500" workbooks (May–July 2026: 10,607 rows loaded, 8,478 kept after
   logged exclusions). It also uses a Contracts Finder notice export, and runs
   seven risk-indicator tests in Python.
3. **Summarises audit history** (assurance opinions, open actions and the
   council's risk scoring method) from Governance Committee papers.
4. **Rates risks** on the council's 5×5 likelihood × impact matrix. Every
   rating cites a rule, a named metric or a history item.
5. **Plans the audit** for the risks the auditor approves: controls, test
   steps, targeted samples of flagged transactions, and a request (PBC) list.
6. **Cross-checks the pack** with an agent team and automated QA scripts
   before the auditor signs off.

Design principles (from `CLAUDE.md`):

- **The LLM reads and judges; Python computes every number.**
- **Everything is traceable** to a PDF quote, a script metric or a prior
  audit finding.
- **Results are "risk indicators to investigate"**, never accusations of
  wrongdoing.
- **Context discipline:** full datasets never enter an agent's context, and
  long result lists go to files.
- **Missing or malformed input means stop and report.** Nothing is
  fabricated.

## Architecture and workflow

```
data/contract-rules.pdf
        │
 (1) /extract-rules                 SKILL, run by the human
        │
   rules.json
        ├──────────────────────────────┐
 (2) spend-analyst                findings-analyst          SUB-AGENTS
     spend xlsx + contracts.csv   committee PDFs
        │                              │
   analytics.json                 history.json
        └──────────────┬───────────────┘
 (3) risk-assessor  (follows the risk-assessment SKILL)     SUB-AGENT
        │   build_register.py
   risk-register.md + auditor-comments.md
        │
 (4) HUMAN GATE 1: auditor approves / amends / rejects each risk
        │   risk-assessor re-run → register revision; build_pack.py --gate
        │
 (5) AGENT TEAM
     planner ──(audit-program SKILL, build_pack.py)──► pack v1, v2, …
     challenger ──CHALLENGE #n──► planner   (two rounds at most)
     qa-reviewer ──QA vN: FAIL/PASS──► planner   (scripts/checks/run_checks.py)
        │
   planning-memo.md, risk-control-matrix.md, audit-program.md,
   samples/T-*.csv, challenges.md, review.md
        │
 (6) HUMAN GATE 2: auditor signs off in outputs/review.md
```

In every step the agent writes its *judgments* to JSON. A deterministic Python
builder then resolves the citations, fills in every figure from the analytics
outputs, and renders the Markdown documents. Builds fail when a citation is
missing or does not resolve.

## Skills (`.claude/skills/`)

| Skill | Used by | What it does |
| --- | --- | --- |
| `extract-rules` | The human, as `/extract-rules` | Converts `data/contract-rules.pdf` into `outputs/rules.json`: one entry per testable rule, with clause, page, thresholds, required action, approver and verbatim quote. Untestable clauses go to `excluded` with a reason. Thresholds the rules name but don't state are null parameters. Verified by `verify_quotes.py`. |
| `risk-assessment` | `risk-assessor` agent | The rating method. The agent writes `outputs/risk-ratings.json` with `[rule:ID]`, `[metric:$.path]` and `[history:ID]` citations and `{{$.path}}` figure placeholders. `build_register.py` scores on the council's matrix, applies the likelihood rubric and the repeat-finding uplift, drops uncited risks, and renders `risk-register.md` and `auditor-comments.md`. |
| `audit-program` | `planner` agent | The planning method. The agent writes `outputs/audit-plan.json`. `build_pack.py` checks the auditor gate, resolves citations, and draws samples deterministically, sized by risk score. It verifies every sampled transaction and checks that every control has a test and every rule is cited or listed as not tested. It then renders the planning pack. |

## Agents (`.claude/agents/`)

| Agent | Role | Inputs → outputs |
| --- | --- | --- |
| `spend-analyst` | Sub-agent | `rules.json`, `data/spend/*.xlsx` and `data/contracts.csv` → `analytics.json` and `analytics-full/`. Writes and runs `scripts/clean.py`, `contracts.py`, `tests.py` and `self_check.py`. |
| `findings-analyst` | Sub-agent | `data/committee/*.pdf` → `history.json`, with source file, PDF page and copy-exact quote per item. Must pass `scripts/verify_history.py`. |
| `risk-assessor` | Sub-agent | `rules.json`, `analytics.json` and `history.json` → `risk-ratings.json`, `risk-register.md` and `auditor-comments.md`. Recommends only; the auditor decides scope. |
| `planner` | Team member | Approved risks → `audit-plan.json` and the pack. Announces `PACK READY vN`, answers challenges, fixes QA failures, and ends with `PLANNER DONE vN`. |
| `challenger` | Team member | Reviews the pack and sends up to eight cited challenges, then one more round of at most four. Owns `challenges.md` and ends with `CHALLENGER DONE`. Rating and scope questions are marked *for the auditor*. |
| `qa-reviewer` | Team member | Runs `scripts/checks/run_checks.py` on every pack version and reports failures to the planner. Writes `review.md` with the verdict and the sign-off block, and ends with `QA DONE vN`. Fixes nothing itself. |

Each agent keeps how-to lessons (never evidence) in
`.claude/agent-memory/<agent>/`.

### Supporting scripts

- **`scripts/`:** spend cleaning and the risk-indicator tests
  (`clean.py`, `contracts.py`, `tests.py`, `common.py`, `self_check.py`), plus
  the history verifier (`verify_history.py`).
- **`scripts/checks/`:** the four QA checks:
  - `check_quotes.py`: every rule quote is in the PDF.
  - `check_numbers.py`: every figure in the pack is in the analytics or pack
    outputs.
  - `check_trace.py`: rule → risk → control → test is complete and the
    challenges are closed.
  - `check_samples.py`: every sampled transaction is in the cleaned data and
    the council's workbook.

  `run_checks.py` runs all four and prints the verdict.
- **`scripts/test_*.py` with `scripts/fixtures/`:** self-tests for the
  builders, the QA checks and the history verifier, including planted-error
  cases.

## Spend-analysis tests

All thresholds are read from `rules.json` and never hardcoded. Results are in
`outputs/analytics.json`, with full lists in `outputs/analytics-full/`.

| Test | Indicator |
| --- | --- |
| `threshold_clustering` | Payments just under a quote or approval boundary |
| `split_purchases` | Same supplier, several payments within 30 days, together crossing a boundary each one stays under |
| `duplicates` | Same supplier, same amount, within 7 days |
| `high_value_suppliers` | Suppliers whose annualised spend reaches the £25,000 quote threshold |
| `off_contract` | Annualised supplier spend above the threshold with no matching Contracts Finder notice; only suppliers above the publication threshold are flagged |
| `expired_notice_spend` | Spend with suppliers whose every matched notice ended before the spend window |
| `spend_vs_award` | Annualised spend at least 1.25 × the annual award value |

## Human approval gates

1. **Risk register approval (gate 1).** The auditor records a decision for
   each risk (`approve`, `amend` or `reject`) in `outputs/auditor-comments.md`.
   The risk-assessor is then re-run to apply the decisions as a register
   revision. `build_pack.py --gate` must pass (every risk decided, register
   revised) before the agent team can start. In this run, R-01, R-03, R-05 and
   R-06 were approved, and R-02 and R-04 were amended (reframed as a
   documentation-verification test and a spend-to-date versus contract-value
   test).
2. **Pack sign-off (gate 2).** The auditor signs off only on a `READY FOR
   SIGN-OFF` verdict, in the sign-off block at the end of `outputs/review.md`.
   A `BLOCKED` verdict sends the pack back to the team, never to the auditor.

## Agent team workflow

Agent teams are enabled by `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in
`.claude/settings.json`. The main Claude Code session acts as the lead:

1. It runs the gate check
   (`.venv/bin/python .claude/skills/audit-program/build_pack.py --gate`).
2. It spawns `planner`, `challenger` and `qa-reviewer` as teammates from their
   agent files.
3. The teammates coordinate directly by message:
   - the planner builds the pack and announces `PACK READY vN`;
   - the challenger sends `CHALLENGE #n` (two rounds at most);
   - the qa-reviewer sends `QA vN: FAIL …` or `PASS`;
   - the planner rebuilds and re-announces.
4. On `PLANNER DONE`, `CHALLENGER DONE` and `QA DONE`, the lead shuts the team
   down and reports to the auditor.

**This run:**

- The pack went through three versions (v1–v3).
- The challenger raised 8 challenges over two rounds: 7 were accepted and
  verified in the rebuilt pack, and 1 (#6, on R-06) was referred to the
  auditor.
- QA blocked v1–v3 only on the traceability check while challenges were still
  open. The final run passed all four checks.

## Setup

Requirements:

- Claude Code
- Python 3 (developed on 3.13)
- `pdftotext` (Poppler), used by the quote and history verifiers

Then create the virtual environment and install the dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # pandas, openpyxl
```

Place the public source files in `data/`; it is read-only:

| Path | Source |
| --- | --- |
| `data/contract-rules.pdf` | Contract Procedure Rules (constitution Part 8, Sept 2025) |
| `data/spend/*.xlsx` | "Expenditure over £500" monthly workbooks, sheet "Data to publish" |
| `data/contracts.csv` | Contracts Finder export for "West Berkshire Council", awarded notices |
| `data/committee/*.pdf` | Internal audit completed-work appendices (2024/25 annual, 2025/26 Q3), Internal Audit Plan 2025–28, Risk Management Strategy 2024–27 |

## How to run

Run these from Claude Code in the project directory:

1. Run `/extract-rules`, then check the result with
   `.venv/bin/python .claude/skills/extract-rules/verify_quotes.py outputs/rules.json`.
2. Ask Claude to run the **spend-analyst** and **findings-analyst** agents.
3. Ask Claude to run the **risk-assessor** agent, which produces
   `risk-register.md` and `auditor-comments.md`.
4. **Gate 1:** fill in a decision for each risk in
   `outputs/auditor-comments.md`, then re-run the risk-assessor to apply
   them.
5. Ask Claude to run the **agent team**, following the lead procedure in
   `CLAUDE.md`.
6. **Gate 2:** review `outputs/review.md` and complete the sign-off block.

Useful checks you can run directly:

```bash
.venv/bin/python -I .claude/skills/audit-program/build_pack.py --gate   # auditor gate
.venv/bin/python -I scripts/checks/run_checks.py                        # QA checks on the pack
.venv/bin/python -I scripts/test_checks.py                              # QA self-test
```

## Main outputs (`outputs/`)

| File | Contents |
| --- | --- |
| `rules.json` | Testable rules with verbatim quotes, exclusions and notes |
| `analytics.json`, `analytics-full/` | Test parameters, counts, £ totals and top-20s; full flagged lists; cleaned spend and exclusion log |
| `history.json` | Audit opinions, open actions, risk scoring method, sources and gaps |
| `risk-ratings.json` → `risk-register.md` | Rated, cited risk register (revision 1) |
| `auditor-comments.md` | Auditor's gate 1 decisions |
| `audit-plan.json` → `planning-memo.md`, `risk-control-matrix.md`, `audit-program.md` | The planning pack: 6 risks, 9 controls, 10 tests, 21 PBC items |
| `samples/T-01.csv` … `T-10.csv` | 123 sampled items (2,412 transactions) drawn from the flagged lists |
| `pack-figures.json` | Every figure the builder computed, for the QA number check |
| `challenges.md` | The challenger's log: 8 challenges and how each was resolved |
| `review.md` | QA results, verdict and the auditor's sign-off |

## Completion statement

I completed the steps in the provided guide through final auditor sign-off.
The repository records each step:

| Step | Evidence |
| --- | --- |
| Rules extracted | `outputs/rules.json` (66 rules, 29 exclusions) |
| Spend analysed | `outputs/analytics.json` and `outputs/analytics-full/` |
| Audit history recorded | `outputs/history.json` |
| Risks rated | `outputs/risk-register.md`, revision 1 |
| Gate 1 decisions recorded | `outputs/auditor-comments.md`, reviewer Revanth Rao, 2026-10-07 |
| Agent team run | Pack v3 in `outputs/`; challenges closed in `outputs/challenges.md` |
| QA | `outputs/review.md`: quotes, numbers, trace and samples all PASS; verdict **READY FOR SIGN-OFF** |
| Final sign-off (gate 2) | `outputs/review.md`: decision *sign off*, Revanth Rao, 2026-10-08. Challenge #6 was reviewed and R-06 left unchanged |
