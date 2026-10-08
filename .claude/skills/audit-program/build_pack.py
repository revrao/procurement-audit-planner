#!/usr/bin/env python3
"""Build the audit planning pack from the planner's judgments.

Reads outputs/audit-plan.json (written by the planner, see SKILL.md) and
resolves it against the auditor-approved risk register:

- the gate: the approved scope comes from outputs/auditor-comments.md and
  outputs/risk-ratings.json; the build fails if any register risk has no
  decision, the register is not a post-gate revision, or the ratings, the
  inputs or the decisions changed since the revision was built;
- every in-scope risk is planned and nothing else is; every control cites a
  rule, every test cites a rule or a metric, every control has a test;
- every rule in rules.json is cited by an in-scope risk, a control or a test,
  or listed in rules_not_tested with a reason;
- every sample is drawn deterministically from a test's full list in
  outputs/analytics-full/ (filter, sort, top or systematic), sized by the
  risk's score, and every transaction is checked against spend_clean.csv
  (row exists, supplier, count and total reconcile) and written to
  outputs/samples/<test>.csv;
- every {{$.path}} placeholder is filled from analytics.json, or from the
  pack's own figures for $.pack.* paths; typed figures and accusatory
  wording fail the build.

Writes outputs/planning-memo.md, outputs/risk-control-matrix.md,
outputs/audit-program.md (ending with the PBC list), outputs/samples/T-*.csv
and outputs/pack-figures.json (every figure this script computed). Nothing
is written unless every check passes.

Usage:
  build_pack.py [--gate] [--plan F] [--ratings F] [--register F] [--comments F]
                [--analytics F] [--history F] [--rules F] [--full-dir D] [--out-dir D]
Exit 0: built (or, with --gate, gate passed). 1: errors, nothing written.
2: missing or malformed input.
"""
import argparse
import csv
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "build_register", ROOT / ".claude/skills/risk-assessment/build_register.py")
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)
InputError, resolve, fmt_value, esc = br.InputError, br.resolve, br.fmt_value, br.esc

# Items drawn per test, by the risk's score (likelihood x impact). The score
# ranges are the council's Table 4 bands: Extreme 15-25, Medium - High 8-12,
# Moderate 4-6, Low up to 3. An item is one row of the test's full list (a
# payment, a split group, a duplicate chain or a supplier).
SAMPLE_SIZES = [(15, 25), (8, 15), (4, 10), (1, 5)]
OPS = ("==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains")
METHODS = ("top", "systematic")
MEMO_SECTIONS = ("objective", "background", "approach", "limitations")
SPEND_FILE = "spend_clean.csv"
SPEND_COLUMNS = ("row_id", "month_file", "excel_row", "date", "Service", "Expenditure category",
                 "Narrative", "Supplier name", "supplier_norm", "Net amount", "tag")
# How a full-list row reconciles to spend_clean.csv: first column present wins.
COUNT_COLS = ("n", "payments")
SUM_COLS = ("sum_gbp", "chain_gbp", "window_gbp")
ROW_AMOUNT_COLS = ("amount_gbp", "Net amount")
# Columns shown for each sampled item in audit-program.md (first eight present).
DISPLAY_COLS = ("boundary", "supplier_names", "published_names", "Supplier name", "date", "first_date",
                "last_date", "n", "payments", "amount_gbp", "Net amount", "sum_gbp", "window_gbp",
                "annualised_gbp", "awarded_value", "ratio", "notice_id", "latest_end", "tag", "main_tag")
HEADERS = {"annualised_gbp": "Annualised estimate", "window_gbp": "Window spend", "sum_gbp": "Group total",
           "amount_gbp": "Amount", "Net amount": "Amount", "awarded_value": "Awarded value",
           "n": "Payments", "payments": "Payments", "supplier_names": "Supplier", "published_names": "Supplier",
           "Supplier name": "Supplier", "latest_end": "Latest notice end", "notice_id": "Notice",
           "main_tag": "Tag", "tag": "Tag", "boundary": "Boundary", "first_date": "First", "last_date": "Last",
           "date": "Date", "ratio": "Ratio"}
CTRL_ID, TEST_ID = re.compile(r"C-\d{2,}"), re.compile(r"T-\d{2,}")


def pbc_key(item):
    return re.sub(r"\s+", " ", item.strip().lower())


def target_size(score):
    return next(n for lo, n in SAMPLE_SIZES if score >= lo)


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Ctx(br.Context):
    """Citations resolve against analytics.json; placeholders also see $.pack.*."""

    def __init__(self, analytics, history, rules):
        super().__init__(analytics, history, rules)
        if "pack" in analytics:
            raise InputError("analytics.json has a top-level 'pack' key, which build_pack.py reserves")
        self.pack = {}
        self.placeholders = []

    def fill(self, text, errors, where):
        doc = dict(self.analytics, pack=self.pack)
        for m in br.PH_RE.finditer(text):
            try:
                v = resolve(doc, m.group(1))
                self.placeholders.append({"where": where, "path": m.group(1), "format": m.group(2),
                                          "value": v, "source": "pack" if m.group(1).startswith("$.pack")
                                          else "analytics"})
            except KeyError:
                pass
        filler = type("F", (), {"analytics": doc})()
        return br.fill(text, filler, errors, where)


# ---------------------------------------------------------------- gate

def comments_revision(path):
    m = re.search(r"^Register: .*revision (\d+)\.", path.read_text(encoding="utf-8"), re.M) if path.exists() else None
    return int(m.group(1)) if m else None


def gate(ratings, meta, decisions, problems, com_rev, inputs):
    """Approved scope from the auditor's decisions. Returns (scope, errors)."""
    errors = list(problems)
    if meta is None:
        return None, ["no risk register with a register-meta block: run the risk-assessor first"]
    rev = meta.get("revision", 0)
    if rev < 1:
        errors.append(f"the register is revision {rev}: the auditor's decisions have not been applied yet. "
                      "The auditor completes auditor-comments.md and the risk-assessor rebuilds the register "
                      "as a revision")
    rrev = (ratings.get("revision") or {}).get("number")
    if rrev != rev:
        errors.append(f"risk-ratings.json is revision {rrev}, the register is revision {rev}: rebuild the register")
    if com_rev != rev:
        errors.append(f"auditor-comments.md names register revision {com_rev}, the register is revision {rev}")
    for k, v in meta["snapshot"]["inputs"].items():
        if inputs.get(k) != v:
            errors.append(f"{k} changed after the register was built; the register must be rebuilt and reviewed")
    snap = meta["snapshot"]["risks"]
    cur = {r.get("risk_id"): r for r in ratings.get("risks", []) if isinstance(r, dict)}
    scope = {"revision": rev, "in": {}, "out": {}, "not_in_register": sorted(set(cur) - set(snap))}
    for rid in sorted(snap):
        if rid not in cur:
            errors.append(f"{rid} is in the register but not in risk-ratings.json")
            continue
        if snap[rid]["raw"] != cur[rid]:
            errors.append(f"{rid} in risk-ratings.json changed after the register was built; rebuild the register")
        d = decisions.get(rid, {})
        dec, com = d.get("decision", ""), d.get("comment", "")
        status = cur[rid].get("status", "proposed")
        if not dec:
            errors.append(f"{rid}: no auditor decision in auditor-comments.md; the gate is not closed")
            continue
        if dec == "reject" and status != "rejected":
            errors.append(f"{rid}: rejected by the auditor but not marked rejected in the revision")
        if dec != "reject" and status == "rejected":
            errors.append(f"{rid}: marked rejected but the auditor's decision is '{dec}'")
        if dec == "amend" and meta.get("applied_amends", {}).get(rid) != com:
            errors.append(f"{rid}: the auditor's amend comment is not the one applied in revision {rev}; "
                          "the risk-assessor must apply it")
        m = meta["risks"].get(rid, {})
        lik = cur[rid]["likelihood"]["score"] + (1 if cur[rid]["likelihood"].get("uplift") else 0)
        score = lik * cur[rid]["impact"]["score"]
        if m.get("score") != score:
            errors.append(f"{rid}: score {score} from risk-ratings.json differs from the register's {m.get('score')}")
        entry = {"title": m.get("title", cur[rid]["title"]), "likelihood": lik, "impact": cur[rid]["impact"]["score"],
                 "score": score, "band": m.get("band"), "decision": dec, "comment": com, "raw": cur[rid]}
        (scope["out"] if dec == "reject" else scope["in"])[rid] = entry
    return scope, errors


# ---------------------------------------------------------------- plan checks

def check_text(text, ctx, where, errors):
    """Resolved citations in text; unresolved citations, typed figures, accusatory wording are errors."""
    good, bad = br.citations(text, ctx)
    errors += [f"{where}: {b}" for b in bad]
    for n in br.typed_numbers(text):
        errors.append(f"{where}: figure typed in prose '{n}'; use a {{{{$.path}}}} placeholder")
    for m in br.ACCUSATORY.finditer(br.PH_RE.sub(" ", text)):
        errors.append(f"{where}: '{m.group(0)}' reads as an accusation; describe a risk indicator to investigate")
    for m in br.PH_RE.finditer(text):
        if "annualised" in m.group(1) and "annualised estimate" not in text:
            errors.append(f"{where}: {m.group(0)} is annualised; label it 'annualised estimate'")
    return good


def nonempty(x):
    return isinstance(x, str) and x.strip()


def check_plan(plan, scope, ctx, errors):
    """Shape, scope, citations and control-test links. Returns the cited-rule map {rule: [places]}."""
    cited = {}

    def cite(good, place):
        for kind, ref, _ in good:
            if kind == "rule":
                cited.setdefault(ref, []).append(place)

    if plan.get("register_revision") != scope["revision"]:
        errors.append(f"audit-plan.json register_revision is {plan.get('register_revision')}, the approved "
                      f"register is revision {scope['revision']}")
    memo = plan.get("memo")
    if not isinstance(memo, dict):
        errors.append("memo must be an object with " + ", ".join(MEMO_SECTIONS))
        memo = {}
    for k in MEMO_SECTIONS:
        if not nonempty(memo.get(k)):
            errors.append(f"memo.{k} must be non-empty text")
        else:
            check_text(memo[k], ctx, f"memo.{k}", errors)
    for k in set(memo) - set(MEMO_SECTIONS):
        errors.append(f"memo.{k} is not a memo section ({', '.join(MEMO_SECTIONS)})")

    for rid, s in scope["in"].items():
        cite(br.citations(json.dumps(s["raw"]), ctx)[0], rid)
    risks = plan.get("risks")
    if not isinstance(risks, list):
        errors.append("risks must be a list")
        risks = []
    planned = [r.get("risk_id") for r in risks if isinstance(r, dict)]
    for rid in scope["in"]:
        if rid not in planned:
            errors.append(f"{rid} is approved by the auditor but missing from audit-plan.json")
    for rid in planned:
        if rid in scope["out"]:
            errors.append(f"{rid} was rejected by the auditor; it cannot be planned")
        elif rid not in scope["in"]:
            errors.append(f"{rid} is planned but is not an approved risk in the register")
    errors += [f"{rid} is planned more than once" for rid in sorted({x for x in planned if planned.count(x) > 1})]

    ctrl_ids, test_ids = [], []
    for i, r in enumerate(risks):
        if not isinstance(r, dict):
            errors.append(f"risks[{i}] is not an object")
            continue
        rid = r.get("risk_id")
        controls, tests = r.get("controls"), r.get("tests")
        if not isinstance(controls, list) or not controls:
            errors.append(f"{rid}: controls must be a non-empty list")
            controls = []
        if not isinstance(tests, list) or not tests:
            errors.append(f"{rid}: tests must be a non-empty list")
            tests = []
        own = set()
        for c in controls:
            cid = c.get("control_id") if isinstance(c, dict) else None
            if not isinstance(cid, str) or not CTRL_ID.fullmatch(cid):
                errors.append(f"{rid}: control_id must look like C-01 ({c!r:.80})")
                continue
            ctrl_ids.append(cid)
            own.add(cid)
            if not nonempty(c.get("control")):
                errors.append(f"{cid}: control must be non-empty text")
                continue
            good = check_text(c["control"], ctx, cid, errors)
            if not any(k == "rule" for k, _, _ in good):
                errors.append(f"{cid}: the expected control cites no rule; cite the [rule:ID] it rests on")
            cite(good, cid)
        tested = set()
        for t in tests:
            tid = t.get("test_id") if isinstance(t, dict) else None
            if not isinstance(tid, str) or not TEST_ID.fullmatch(tid):
                errors.append(f"{rid}: test_id must look like T-01 ({t!r:.80})")
                continue
            test_ids.append(tid)
            tc = t.get("controls")
            if not isinstance(tc, list) or not tc:
                errors.append(f"{tid}: controls must list the control(s) this test tests")
                tc = []
            for cid in tc:
                if cid not in own:
                    errors.append(f"{tid}: control {cid} is not a control of {rid}")
                tested.add(cid)
            if not nonempty(t.get("step")):
                errors.append(f"{tid}: step must be non-empty text")
            else:
                good = check_text(t["step"], ctx, f"{tid} step", errors)
                if not any(k in ("rule", "metric") for k, _, _ in good):
                    errors.append(f"{tid}: the test step cites no rule or metric")
                cite(good, tid)
            pbc = t.get("pbc")
            if not isinstance(pbc, list) or not pbc or not all(nonempty(p) for p in pbc):
                errors.append(f"{tid}: pbc must be a non-empty list of the items the test needs")
            else:
                for j, p in enumerate(pbc):
                    check_text(p, ctx, f"{tid} pbc[{j}]", errors)
            if not isinstance(t.get("sample"), dict):
                errors.append(f"{tid}: sample must be a recipe object")
        for cid in sorted(own - tested):
            errors.append(f"{cid}: no test tests this control")
    errors += [f"duplicate control_id {x}" for x in sorted({x for x in ctrl_ids if ctrl_ids.count(x) > 1})]
    errors += [f"duplicate test_id {x}" for x in sorted({x for x in test_ids if test_ids.count(x) > 1})]
    return cited


def check_rules(plan, cited, ctx, errors):
    """Every rule cited or listed as not tested. Returns the not-tested map {rule: reason}."""
    nt = plan.get("rules_not_tested")
    if not isinstance(nt, list):
        errors.append("rules_not_tested must be a list of {rule_id, reason}")
        nt = []
    out = {}
    for e in nt:
        rid = e.get("rule_id") if isinstance(e, dict) else None
        if rid not in ctx.rules:
            errors.append(f"rules_not_tested: {rid!r} is not a rule in rules.json")
            continue
        if rid in out:
            errors.append(f"rules_not_tested lists {rid} twice")
        if not nonempty(e.get("reason")):
            errors.append(f"rules_not_tested {rid}: give the reason it is not tested")
            continue
        check_text(e["reason"], ctx, f"rules_not_tested {rid}", errors)
        if rid in cited:
            errors.append(f"{rid} is cited by {', '.join(sorted(set(cited[rid])))} and also listed as not tested")
        out[rid] = e["reason"]
    for rid, r in ctx.rules.items():
        if rid not in cited and rid not in out:
            errors.append(f"{rid} (clause {r['clause']}) is not cited by an in-scope risk, control or test "
                          f"and not listed in rules_not_tested")
    return out


# ---------------------------------------------------------------- samples

def filter_value(v, ctx):
    if isinstance(v, str):
        m = br.PH_RE.fullmatch(v.strip())
        if m:
            return resolve(ctx.analytics, m.group(1))
    return v


def matches(row, cond, value):
    cell, op = row[cond["column"]], cond["op"]
    if op in ("in", "not_in"):
        hit = cell in [str(x) for x in value]
        return hit if op == "in" else not hit
    if op == "contains":
        return str(value).lower() in cell.lower()
    a, b = num(cell), num(value) if not isinstance(value, bool) else None
    if op in ("==", "!="):
        eq = (a == b) if (a is not None and b is not None and not isinstance(value, str)) else cell == str(value)
        return eq if op == "==" else not eq
    if a is None:
        return False
    return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]


def draw(tid, recipe, size, full_dir, allowed, ctx, errors):
    """Apply the recipe. Returns (population, after_filter, picked [(line, row)]) or None."""
    f = recipe.get("file")
    if f not in allowed:
        errors.append(f"{tid}: sample file {f!r} is not a test's full list in analytics-full "
                      f"({', '.join(sorted(allowed))})")
        return None
    rows = read_csv(full_dir / f)
    cols = set(rows[0]) if rows else set()
    pop = list(enumerate(rows, start=2))  # source line numbers (header is line 1)
    for j, c in enumerate(recipe.get("filter") or []):
        if not isinstance(c, dict) or c.get("op") not in OPS or c.get("column") not in cols or "value" not in c:
            errors.append(f"{tid}: filter[{j}] needs column (one of the file's), op ({', '.join(OPS)}) and value: {c}")
            return None
        try:
            v = filter_value(c["value"], ctx)
        except KeyError as e:
            errors.append(f"{tid}: filter[{j}] placeholder {c['value']} does not resolve ({e.args[0]})")
            return None
        if c["op"] in (">", ">=", "<", "<=") and num(v) is None:
            errors.append(f"{tid}: filter[{j}] compares {c['op']} with a non-number {v!r}")
            return None
        if c["op"] in ("in", "not_in") and not isinstance(v, list):
            errors.append(f"{tid}: filter[{j}] op {c['op']} needs a list value")
            return None
        pop = [(ln, r) for ln, r in pop if matches(r, c, v)]
    after = len(pop)
    sort = recipe.get("sort") or []
    for j, s in enumerate(sort):
        if not isinstance(s, dict) or s.get("column") not in cols or s.get("order") not in ("asc", "desc"):
            errors.append(f"{tid}: sort[{j}] needs column (one of the file's) and order asc or desc: {s}")
            return None
    for s in reversed(sort):  # stable multi-key sort; ties keep file order; blanks last
        col, desc = s["column"], s["order"] == "desc"
        vals = [r[col] for _, r in pop if r[col] != ""]
        numeric = all(num(v) is not None for v in vals)
        full = [(ln, r) for ln, r in pop if r[col] != ""]
        blank = [(ln, r) for ln, r in pop if r[col] == ""]
        full.sort(key=lambda x: num(x[1][col]) if numeric else x[1][col], reverse=desc)
        pop = full + blank
    n = min(size, len(pop))
    if recipe.get("method") == "top":
        picked = pop[:n]
    else:
        picked = [pop[(i * len(pop)) // n] for i in range(n)]
    return len(rows), after, picked


def transactions(tid, line, row, spend, errors):
    """The spend rows behind one flagged item, reconciled to the item. None if any check fails."""
    ids = row["row_ids"].split(";") if row.get("row_ids") else ([row["row_id"]] if row.get("row_id") else [])
    where = f"{tid} item at line {line}"
    if not ids:
        errors.append(f"{where}: no row_id or row_ids; its transactions cannot be identified")
        return None
    missing = [i for i in ids if i not in spend]
    if missing:
        errors.append(f"{where}: {len(missing)} transaction(s) not in {SPEND_FILE}: {', '.join(missing[:5])}")
        return None
    tx = [spend[i] for i in dict.fromkeys(ids)]
    ok = True
    if row.get("supplier_norm") and any(t["supplier_norm"] != row["supplier_norm"] for t in tx):
        errors.append(f"{where}: transaction supplier differs from the item's supplier {row['supplier_norm']}")
        ok = False
    cc = next((c for c in COUNT_COLS if c in row), None)
    if cc and num(row[cc]) != len(tx):
        errors.append(f"{where}: {cc} = {row[cc]} but {len(tx)} distinct transactions")
        ok = False
    sc = next((c for c in SUM_COLS if c in row), None)
    total = round(sum(float(t["Net amount"]) for t in tx), 2)
    if sc and abs(total - float(row[sc])) > 0.01:
        errors.append(f"{where}: {sc} = {row[sc]} but its transactions total {total:.2f}")
        ok = False
    ac = next((c for c in ROW_AMOUNT_COLS if c in row), None)
    if ac and any(abs(float(t["Net amount"]) - float(row[ac])) > 0.005 for t in tx):
        errors.append(f"{where}: a transaction amount differs from the item's {ac} {row[ac]}")
        ok = False
    return sorted(tx, key=lambda t: (t["date"], t["row_id"])) if ok else None


# ---------------------------------------------------------------- render helpers

def cell(col, v):
    x = num(v)
    if x is not None and any(k in col.lower() for k in ("gbp", "amount", "value", "boundary")):
        return f"£{x:,.2f}"
    return esc(v if len(v) <= 60 else v[:57] + "…")


def describe_recipe(r, ctx):
    parts = []
    for c in r.get("filter") or []:
        v = c["value"]
        if isinstance(v, list):
            shown = ", ".join(map(str, v))
        elif isinstance(v, str) and br.PH_RE.fullmatch(v.strip()):
            path = br.PH_RE.fullmatch(v.strip()).group(1)
            shown = f"{fmt_value(filter_value(v, ctx), path, None)} (`{path}`)"
        else:
            shown = str(v)
        parts.append(f"`{c['column']}` {c['op']} {shown}")
    sort = ", ".join(f"`{s['column']}` {s['order']}" for s in r.get("sort") or [])
    return ("; ".join(parts) or "none"), (sort or "file order")


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gate", action="store_true", help="run only the auditor-gate check")
    ap.add_argument("--plan", default=str(ROOT / "outputs/audit-plan.json"))
    ap.add_argument("--ratings", default=str(ROOT / "outputs/risk-ratings.json"))
    ap.add_argument("--register", default=str(ROOT / "outputs/risk-register.md"))
    ap.add_argument("--comments", default=str(ROOT / "outputs/auditor-comments.md"))
    ap.add_argument("--analytics", default=str(ROOT / "outputs/analytics.json"))
    ap.add_argument("--history", default=str(ROOT / "outputs/history.json"))
    ap.add_argument("--rules", default=str(ROOT / "outputs/rules.json"))
    ap.add_argument("--full-dir", default=str(ROOT / "outputs/analytics-full"))
    ap.add_argument("--out-dir", default=str(ROOT / "outputs"))
    a = ap.parse_args(argv)
    out, full_dir = Path(a.out_dir), Path(a.full_dir)

    try:
        ratings = br.load_json(a.ratings, "risk-ratings.json")
        rules_doc = br.load_json(a.rules, "rules.json")
        ctx = Ctx(br.load_json(a.analytics, "analytics.json"), br.load_json(a.history, "history.json"), rules_doc)
        if (ctx.analytics.get("self_check") or {}).get("passed") is not True:
            raise InputError("analytics.json self_check did not pass; re-run the spend-analyst first")
        if not isinstance(ratings, dict) or not isinstance(ratings.get("risks"), list):
            raise InputError("risk-ratings.json must be an object with a 'risks' list")
        if not Path(a.comments).exists():
            raise InputError(f"auditor-comments.md not found: {a.comments}")
        meta = br.read_meta(Path(a.register))
    except InputError as e:
        print(f"STOP: {e}")
        return 2
    inputs = {"outputs/analytics.json": br.sha256(a.analytics), "outputs/history.json": br.sha256(a.history),
              "outputs/rules.json": br.sha256(a.rules)}
    decisions, _, problems = br.read_comments(Path(a.comments))
    scope, errors = gate(ratings, meta, decisions, problems, comments_revision(Path(a.comments)), inputs)

    if a.gate or errors:
        for e in errors:
            print(f"ERROR {e}")
        if errors:
            print(f"GATE FAILED: {len(errors)} error(s); the pack cannot be built")
            return 1
        print(f"GATE PASSED: register revision {scope['revision']}; in scope: "
              + (", ".join(f"{k} (score {v['score']})" for k, v in scope["in"].items()) or "none")
              + "; rejected: " + (", ".join(scope["out"]) or "none"))
        return 0

    try:
        plan = br.load_json(a.plan, "audit-plan.json")
        if not isinstance(plan, dict):
            raise InputError("audit-plan.json must be an object")
        if not (full_dir / SPEND_FILE).exists():
            raise InputError(f"{SPEND_FILE} not found in {full_dir}")
    except InputError as e:
        print(f"STOP: {e}")
        return 2
    cited = check_plan(plan, scope, ctx, errors)
    not_tested = check_rules(plan, cited, ctx, errors)
    if errors:
        return report(errors)

    # samples
    spend = {r["row_id"]: r for r in read_csv(full_dir / SPEND_FILE)}
    allowed = {}
    for name, t in ctx.analytics["tests"].items():
        fl = t.get("full_list")
        if isinstance(fl, str) and (full_dir / Path(fl).name).exists():
            allowed[Path(fl).name] = name
    tests_fig, samples, plan_risks = {}, {}, {r["risk_id"]: r for r in plan["risks"]}
    for rid, risk in plan_risks.items():
        score = scope["in"][rid]["score"]
        for t in risk["tests"]:
            tid, rec = t["test_id"], t["sample"]
            target = target_size(score)
            if rec.get("method") not in METHODS:
                errors.append(f"{tid}: sample.method must be one of {', '.join(METHODS)}")
                continue
            if not nonempty(rec.get("rationale")):
                errors.append(f"{tid}: sample.rationale must say why these items")
            else:
                check_text(rec["rationale"], ctx, f"{tid} sample.rationale", errors)
            size = rec.get("size")
            if size is None:
                size = target
            elif not isinstance(size, int) or isinstance(size, bool) or size < target:
                errors.append(f"{tid}: sample.size {size!r} is below {target}, the size for score {score}")
                continue
            elif size > target and not nonempty(rec.get("size_reason")):
                errors.append(f"{tid}: sample.size {size} exceeds {target} (score {score}); give size_reason")
                continue
            res = draw(tid, rec, size, full_dir, allowed, ctx, errors)
            if not res:
                continue
            population, after, picked = res
            items = []
            for k, (line, row) in enumerate(picked, start=1):
                tx = transactions(tid, line, row, spend, errors)
                if tx is not None:
                    items.append((k, line, row, tx))
            if not picked:
                errors.append(f"{tid}: the filter leaves no items to sample")
            n_tx = sum(len(i[3]) for i in items)
            gbp = round(sum(float(x["Net amount"]) for i in items for x in i[3]), 2)
            tests_fig[tid] = {"risk_id": rid, "source_file": rec["file"], "test": allowed[rec["file"]],
                              "population_items": population, "after_filter": after, "target_size": target,
                              "requested_size": size, "sampled_items": len(picked), "sampled_transactions": n_tx,
                              "sampled_gbp": gbp, "population_short": after < size}
            samples[tid] = items
    if errors:
        return report(errors)

    # figures computed here, available to placeholders as $.pack.*
    pbc, pbc_order = {}, []
    for rid, risk in plan_risks.items():
        for t in risk["tests"]:
            for p in t["pbc"]:
                key = pbc_key(p)
                if key not in pbc:
                    pbc[key] = {"item": p.strip(), "tests": [], "risks": []}
                    pbc_order.append(key)
                if t["test_id"] not in pbc[key]["tests"]:
                    pbc[key]["tests"].append(t["test_id"])
                if rid not in pbc[key]["risks"]:
                    pbc[key]["risks"].append(rid)
    pbc_ids = {k: f"PBC-{i:02d}" for i, k in enumerate(pbc_order, start=1)}
    risk_fig = {}
    for rid, s in scope["in"].items():
        ts = [t["test_id"] for t in plan_risks[rid]["tests"]]
        risk_fig[rid] = {"likelihood": s["likelihood"], "impact": s["impact"], "score": s["score"],
                         "band": s["band"], "decision": s["decision"], "sample_size_per_test": target_size(s["score"]),
                         "controls": len(plan_risks[rid]["controls"]), "tests": len(ts),
                         "sampled_items": sum(tests_fig[t]["sampled_items"] for t in ts),
                         "sampled_transactions": sum(tests_fig[t]["sampled_transactions"] for t in ts),
                         "sampled_gbp": round(sum(tests_fig[t]["sampled_gbp"] for t in ts), 2)}
    ctx.pack.update({
        "scope": {"register_revision": scope["revision"], "risks_in_register": len(scope["in"]) + len(scope["out"]),
                  "in_scope": len(scope["in"]), "rejected": len(scope["out"])},
        "risks": risk_fig,
        "tests": tests_fig,
        "totals": {"controls": sum(r["controls"] for r in risk_fig.values()), "tests": len(tests_fig),
                   "sampled_items": sum(t["sampled_items"] for t in tests_fig.values()),
                   "sampled_transactions": sum(t["sampled_transactions"] for t in tests_fig.values()),
                   "sampled_gbp": round(sum(t["sampled_gbp"] for t in tests_fig.values()), 2),
                   "pbc_items": len(pbc)},
        "rules": {"total": len(ctx.rules), "cited": len(cited), "not_tested": len(not_tested)},
        "sample_sizes": [{"min_score": lo, "items_per_test": n} for lo, n in SAMPLE_SIZES],
    })

    # fill every planner text
    F = {}
    for k in MEMO_SECTIONS:
        F[f"memo.{k}"] = ctx.fill(plan["memo"][k], errors, f"memo.{k}")
    for rid, risk in plan_risks.items():
        for c in risk["controls"]:
            F[c["control_id"]] = ctx.fill(c["control"], errors, c["control_id"])
        for t in risk["tests"]:
            F[f"{t['test_id']} step"] = ctx.fill(t["step"], errors, f"{t['test_id']} step")
            F[f"{t['test_id']} rationale"] = ctx.fill(t["sample"]["rationale"], errors, f"{t['test_id']} sample.rationale")
    for k in pbc:
        pbc[k]["filled"] = ctx.fill(pbc[k]["item"], errors, pbc_ids[k])
    for rid, reason in not_tested.items():
        F[f"nt {rid}"] = ctx.fill(reason, errors, f"rules_not_tested {rid}")
    if errors:
        return report(errors)

    rc = lambda s: br.render_cites(s, ctx)  # noqa: E731
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lang = ctx.analytics.get("language", "Results are risk indicators to investigate, not findings.")
    banner = [f"*{lang}* Nothing in this pack is a finding against the council, a department or a "
              "supplier; sampled items are flagged for examination.", ""]
    stamp = (f"Built {when} by `build_pack.py` from `outputs/audit-plan.json` and register revision "
             f"{scope['revision']}; every figure the builder computed is in `outputs/pack-figures.json`.")
    sized = "; ".join(f"score {lo}+: {n}" for lo, n in SAMPLE_SIZES)

    # planning memo
    M = ["# Planning memo: procurement audit, West Berkshire Council", "", stamp, ""] + banner
    M += ["## Objective", "", rc(F["memo.objective"]), "", "## Background", "", rc(F["memo.background"]), ""]
    M += ["## Scope", "",
          f"The auditor approved {len(scope['in'])} of the {len(scope['in']) + len(scope['out'])} risks in register "
          f"revision {scope['revision']} (`outputs/auditor-comments.md`).", "",
          "| Risk | Title | Score | Band | Auditor decision | Controls | Tests | Items sampled | Transactions |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for rid, s in sorted(scope["in"].items(), key=lambda x: (-x[1]["score"], x[0])):
        f = risk_fig[rid]
        M.append(f"| {rid} | {esc(s['title'])} | {s['score']} | {s['band'] or 'n/a'} | {s['decision']} | "
                 f"{f['controls']} | {f['tests']} | {f['sampled_items']} | {f['sampled_transactions']} |")
    M.append("")
    if scope["out"]:
        M += ["Out of scope (rejected by the auditor):", "", "| Risk | Title | Score | Auditor comment |",
              "| --- | --- | --- | --- |"]
        M += [f"| {rid} | {esc(s['title'])} | {s['score']} | {esc(s['comment'])} |" for rid, s in scope["out"].items()]
        M.append("")
    M += ["## Approach", "", rc(F["memo.approach"]), "",
          "## Sampling", "",
          "Samples are targeted, not random: each test draws from the full list of items a spend-analytics test "
          "flagged, using the filter, order and method in the audit program. Every draw is deterministic, so a "
          "rebuild gives the same sample. Items per test are set by the risk's score on the council's Table 4 "
          f"ranges ({sized}). Every sampled transaction was matched to `outputs/analytics-full/{SPEND_FILE}`, and "
          "each item's payment count and total were reconciled to its transactions.", "",
          "| Test | Risk | Flagged list | Items flagged | After filter | Sample size | Items drawn | Transactions | Value drawn |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for tid, t in tests_fig.items():
        short = " (all available)" if t["population_short"] else ""
        M.append(f"| {tid} | {t['risk_id']} | `{t['source_file']}` | {t['population_items']:,} | {t['after_filter']:,} | "
                 f"{t['requested_size']} | {t['sampled_items']}{short} | {t['sampled_transactions']:,} | "
                 f"£{t['sampled_gbp']:,.2f} |")
    tot = ctx.pack["totals"]
    M += ["", f"In total {tot['sampled_items']} items, {tot['sampled_transactions']:,} transactions, "
              f"£{tot['sampled_gbp']:,.2f}. The transactions for each test are in `outputs/samples/<test>.csv`.", "",
          "## Rule coverage", "",
          f"All {len(ctx.rules)} rules in `outputs/rules.json` are accounted for: {len(cited)} are cited by an in-scope "
          f"risk, control or test, and {len(not_tested)} are not tested, each with a reason "
          "(`outputs/risk-control-matrix.md`).", "",
          "## Limitations", "", rc(F["memo.limitations"]), "",
          "## Sign-off", "",
          "Draft for the auditor. The pack is cross-checked by the challenger and the QA reviewer; sign-off is "
          "recorded in `outputs/review.md`.", ""]

    # risk-control matrix
    R = ["# Risk-control matrix: procurement audit, West Berkshire Council", "", stamp, ""] + banner
    R += ["| Risk | Score | Expected control | Tested by |", "| --- | --- | --- | --- |"]
    for rid, risk in plan_risks.items():
        s = scope["in"][rid]
        for c in risk["controls"]:
            by = ", ".join(t["test_id"] for t in risk["tests"] if c["control_id"] in t["controls"])
            R.append(f"| {rid}: {esc(s['title'])} | {s['score']} ({s['band'] or 'n/a'}) | "
                     f"**{c['control_id']}** {esc(rc(F[c['control_id']]))} | {by} |")
    R += ["", "## Rule coverage", "",
          f"Every rule in `outputs/rules.json` ({len(ctx.rules)}) is cited by an in-scope risk, a control or a test, "
          "or is listed as not tested with the planner's reason.", "",
          "| Rule | Clause | Condition | Cited by | Not tested: reason |", "| --- | --- | --- | --- | --- |"]
    for rid, r in ctx.rules.items():
        by = ", ".join(dict.fromkeys(cited.get(rid, [])))
        R.append(f"| {rid} | {esc(r['clause'])} | {esc(r['condition'])} | {by} | "
                 f"{esc(rc(F['nt ' + rid])) if rid in not_tested else ''} |")
    R.append("")

    # audit program
    P = ["# Audit program: procurement audit, West Berkshire Council", "", stamp, ""] + banner
    for rid, risk in sorted(plan_risks.items(), key=lambda x: (-scope["in"][x[0]]["score"], x[0])):
        s = scope["in"][rid]
        P += [f"## {rid} · {s['title']}", "",
              f"Score {s['score']} (likelihood {s['likelihood']} × impact {s['impact']}), {s['band'] or 'n/a'}; "
              f"auditor decision: {s['decision']}. Sample size per test: {target_size(s['score'])} items.", "",
              "Expected controls:", ""]
        P += [f"- **{c['control_id']}** {rc(F[c['control_id']])}" for c in risk["controls"]]
        P.append("")
        for t in risk["tests"]:
            tid, rec, tf = t["test_id"], t["sample"], tests_fig[t["test_id"]]
            flt, srt = describe_recipe(rec, ctx)
            P += [f"### {tid} · tests {', '.join(t['controls'])}", "",
                  f"**Test step.** {rc(F[tid + ' step'])}", "",
                  f"**Sample.** {rc(F[tid + ' rationale'])}", "",
                  f"- Flagged list: `outputs/analytics-full/{rec['file']}` ({tf['test']}), "
                  f"{tf['population_items']:,} items; filter: {flt}; {tf['after_filter']:,} after the filter",
                  f"- Order: {srt}; method: {rec['method']}; size: {tf['requested_size']}"
                  + (f" ({esc(rec['size_reason'])})" if rec.get("size_reason") else f" (score {s['score']})")
                  + (f"; only {tf['sampled_items']} available" if tf["population_short"] else ""),
                  f"- Drawn: {tf['sampled_items']} items, {tf['sampled_transactions']:,} transactions, "
                  f"£{tf['sampled_gbp']:,.2f}; transactions in `outputs/samples/{tid}.csv`",
                  f"- PBC: {', '.join(pbc_ids[pbc_key(p)] for p in t['pbc'])}", ""]
            items = samples[tid]
            if items:
                cols = [c for c in DISPLAY_COLS if c in items[0][2]][:8]
                P += ["Items to examine (risk indicators, not findings):", "",
                      "| # | " + " | ".join(HEADERS.get(c, c) for c in cols) + " | Transactions |",
                      "| --- | " + " | ".join("---" for _ in cols) + " | --- |"]
                for k, line, row, tx in items:
                    P.append(f"| {k} | " + " | ".join(cell(c, row[c]) for c in cols) + f" | {len(tx)} |")
                P.append("")
    P += ["## PBC list", "", "Items to request from the council before fieldwork, derived from the test steps.", "",
          "| Ref | Item | For tests | Risks |", "| --- | --- | --- | --- |"]
    for k in pbc_order:
        P.append(f"| {pbc_ids[k]} | {esc(rc(pbc[k]['filled']))} | {', '.join(pbc[k]['tests'])} | "
                 f"{', '.join(pbc[k]['risks'])} |")
    P.append("")

    docs = {"planning-memo.md": M, "risk-control-matrix.md": R, "audit-program.md": P}
    for name, lines in docs.items():
        text = "\n".join(lines)
        if "{{" in text:
            errors.append(f"{name}: an unfilled placeholder remains")
        for m in br.ACCUSATORY.finditer(text):
            errors.append(f"{name}: '{m.group(0)}' reads as an accusation")
    if errors:
        return report(errors)

    figures = dict(ctx.pack, built=when, placeholders=ctx.placeholders,
                   inputs=dict(inputs, **{"outputs/audit-plan.json": br.sha256(a.plan),
                                          "outputs/risk-ratings.json": br.sha256(a.ratings),
                                          "outputs/auditor-comments.md": br.sha256(a.comments),
                                          f"outputs/analytics-full/{SPEND_FILE}": br.sha256(full_dir / SPEND_FILE)}),
                   pbc=[{"ref": pbc_ids[k], "item": pbc[k]["filled"], "tests": pbc[k]["tests"]} for k in pbc_order],
                   rules_not_tested=sorted(not_tested))
    sdir = out / "samples"
    sdir.mkdir(parents=True, exist_ok=True)
    for old in sdir.glob("T-*.csv"):
        old.unlink()
    for tid, items in samples.items():
        rows = []
        for k, line, row, tx in items:
            key = {f"item_{c}": v for c, v in row.items() if c not in ("row_ids", "row_id")}
            for x in tx:
                rows.append(dict({"test_id": tid, "risk_id": tests_fig[tid]["risk_id"], "item": k,
                                  "source_file": tests_fig[tid]["source_file"], "source_line": line},
                                 **key, **{c: x[c] for c in SPEND_COLUMNS}))
        with open(sdir / f"{tid}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["test_id"])
            w.writeheader()
            w.writerows(rows)
    for name, lines in docs.items():
        (out / name).write_text("\n".join(lines), encoding="utf-8")
    (out / "pack-figures.json").write_text(json.dumps(figures, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"BUILT pack: {len(scope['in'])} risk(s) in scope, {tot['controls']} controls, {tot['tests']} tests, "
          f"{tot['sampled_items']} items / {tot['sampled_transactions']} transactions sampled, {len(pbc)} PBC items, "
          f"{len(cited)} rules cited, {len(not_tested)} not tested")
    return 0


def report(errors):
    for e in errors:
        print(f"ERROR {e}")
    print(f"FAIL: {len(errors)} error(s); nothing written")
    return 1


if __name__ == "__main__":
    sys.exit(main())
