#!/usr/bin/env python3
"""QA traceability check: rule -> risk -> control -> test is complete, and the challenges are closed.

1. Rules: every rule in rules.json is cited ([rule:ID]) by a rated, in-scope
   risk in risk-ratings.json, a control or a test step in audit-plan.json, or
   is listed in rules_not_tested with a reason; never both; and the
   risk-control matrix's rule-coverage table shows the same.
2. Risks: every risk the auditor approved (approve or amend in
   auditor-comments.md) is planned once in audit-plan.json, has at least one
   control, every control has a test, and the risk, each control and each
   test appear in risk-control-matrix.md and audit-program.md. No rejected
   risk is planned.
3. High risks: every register risk in a High band (Table 4 Extreme or
   Medium - High, i.e. score 8 or more) is in scope, or was rejected with the
   auditor's reason recorded in auditor-comments.md and shown in the memo.
4. Challenges: outputs/challenges.md exists; every row of its table cites
   evidence that resolves ([rule:ID], [metric:$.path], [history:ID] or a
   `$.pack.…` path in pack-figures.json); no row is open (Status must be
   resolved, declined or for the auditor).

Usage: check_trace.py [--out DIR] [--inputs DIR] [--data DIR]
Exit 0 pass, 1 failures, 2 could not run.
"""
import importlib.util
import re
import sys
from pathlib import Path

_s = importlib.util.spec_from_file_location("_qa", Path(__file__).resolve().parent / "_qa.py")
qa = importlib.util.module_from_spec(_s)
_s.loader.exec_module(qa)
br = qa.br

RULE_CITE = re.compile(r"\[rule:([A-Za-z0-9_\-]+)\]")
PACK_PATH = re.compile(r"\$\.pack(?:\.[A-Za-z0-9_\-]+|\[\d+\])+")
HIGH_BANDS = ("extreme", "medium - high")
CLOSED = ("resolved", "declined", "for the auditor")


def read(out, name, c):
    p = out / name
    if not c.ok(p.exists(), f"{name} not found"):
        return None
    return p.read_text(encoding="utf-8")


def body(c):
    a = qa.parser(__doc__).parse_args()
    out, inputs = Path(a.out), Path(a.inputs)
    rules_doc = qa.load_json(inputs / "rules.json")
    ctx = br.Context(qa.load_json(inputs / "analytics.json"), qa.load_json(inputs / "history.json"), rules_doc)
    rules = ctx.rules
    ratings = {r["risk_id"]: r for r in qa.load_json(out / "risk-ratings.json").get("risks", [])}
    dec = qa.decisions(out)
    in_scope = {rid for rid, (d, _) in dec.items() if d in ("approve", "amend")}
    rejected = {rid for rid, (d, _) in dec.items() if d == "reject"}
    plan = qa.load_json(out / "audit-plan.json") if (out / "audit-plan.json").exists() else None
    c.ok(plan is not None, "audit-plan.json not found: the pack has not been planned")
    plan = plan or {"risks": [], "rules_not_tested": []}
    matrix = read(out, "risk-control-matrix.md", c) or ""
    program = read(out, "audit-program.md", c) or ""
    memo = read(out, "planning-memo.md", c) or ""

    # 1. rules
    cited = {}
    for rid in in_scope:
        if rid in ratings and ratings[rid].get("status") != "rejected":
            for x in RULE_CITE.findall(str(ratings[rid])):
                cited.setdefault(x, set()).add(rid)
    for r in plan.get("risks", []):
        for ctl in r.get("controls", []):
            for x in RULE_CITE.findall(ctl.get("control", "")):
                cited.setdefault(x, set()).add(ctl.get("control_id"))
        for t in r.get("tests", []):
            for x in RULE_CITE.findall(t.get("step", "")):
                cited.setdefault(x, set()).add(t.get("test_id"))
    not_tested = {}
    for e in plan.get("rules_not_tested", []):
        rid = e.get("rule_id")
        c.ok(rid in rules, f"rules_not_tested lists {rid!r}, which is not in rules.json")
        not_tested[rid] = (e.get("reason") or "").strip()
    for x in sorted(set(cited) - set(rules)):
        c.ok(False, f"[rule:{x}] cited by {', '.join(sorted(cited[x]))} is not in rules.json")
    cov = {row[0]: row for row in qa.md_table(matrix.splitlines(), "Rule")}
    for rid in rules:
        by, reason = cited.get(rid), not_tested.get(rid)
        if by and rid in not_tested:
            c.ok(False, f"{rid} is cited by {', '.join(sorted(by))} and also listed as not tested")
        elif by:
            c.ok(True, "")
        else:
            c.ok(bool(reason), f"{rid} is not cited by an in-scope risk, control or test"
                               + (" and its not-tested reason is blank" if rid in not_tested else
                                  " and not listed as not tested"))
        row = cov.get(rid)
        if c.ok(row is not None and len(row) >= 5, f"{rid} has no row in the matrix's rule-coverage table"):
            c.ok(bool(row[3]) == bool(by) and bool(row[4]) == (not by and bool(reason)),
                 f"{rid}: matrix shows cited by '{row[3]}', not tested '{row[4][:40]}'; the plan says "
                 + (f"cited by {', '.join(sorted(by))}" if by else "not tested"))

    # 2. approved risks
    planned = [r.get("risk_id") for r in plan.get("risks", [])]
    for rid in sorted(set(planned) & rejected):
        c.ok(False, f"{rid} was rejected by the auditor but is planned")
    for rid in sorted(set(planned) - in_scope - rejected):
        c.ok(False, f"{rid} is planned but not approved in auditor-comments.md")
    by_id = {r.get("risk_id"): r for r in plan.get("risks", [])}
    m_rows = qa.md_table(matrix.splitlines(), "Risk")
    for rid in sorted(in_scope):
        if not c.ok(planned.count(rid) == 1, f"{rid} is approved but planned {planned.count(rid)} times"):
            continue
        r = by_id[rid]
        ctl_ids = [x.get("control_id") for x in r.get("controls", [])]
        tests = r.get("tests", [])
        c.ok(bool(ctl_ids), f"{rid} has no control")
        c.ok(bool(tests), f"{rid} has no test")
        tested = {cid for t in tests for cid in t.get("controls", [])}
        for cid in ctl_ids:
            c.ok(cid in tested, f"{rid} control {cid} has no test")
            row = next((x for x in m_rows if x[0].startswith(f"{rid}:") and f"**{cid}**" in x[2]), None)
            c.ok(row is not None and bool(row[3].strip()),
                 f"{rid} control {cid} " + ("is not in the risk-control matrix" if row is None
                                            else "shows no test in the matrix"))
        c.ok(re.search(rf"^## {re.escape(rid)} · ", program, re.M) is not None,
             f"{rid} has no section in audit-program.md")
        for t in tests:
            tid = t.get("test_id")
            c.ok(re.search(rf"^### {re.escape(tid)} · ", program, re.M) is not None,
                 f"{rid} test {tid} is not in audit-program.md")
    for rid in sorted(rejected):
        c.ok(not re.search(rf"^## {re.escape(rid)} · ", program, re.M), f"rejected {rid} appears in audit-program.md")

    # 3. high risks
    reg = read(out, "risk-register.md", c) or ""
    summary = qa.md_table(reg.splitlines(), "ID")
    hdr = next((br.split_row(l) for l in reg.splitlines() if l.startswith("| ID |")), [])
    band_col = next((i for i, h in enumerate(hdr) if h.startswith("Band")), None)
    c.ok(band_col is not None and summary, "risk-register.md has no Summary table with a Band column")
    for row in summary if band_col is not None else []:
        rid = row[0].split()[0]
        if not row[band_col].lower().startswith(HIGH_BANDS):
            continue
        d, com = dec.get(rid, ("", ""))
        if d in ("approve", "amend"):
            c.ok(True, "")
        elif d == "reject":
            c.ok(bool(com.strip()), f"High risk {rid} ({row[band_col]}) was rejected with no reason recorded")
            c.ok(re.search(rf"^\| {re.escape(rid)} \|", memo, re.M) is not None,
                 f"High risk {rid} is out of scope but the planning memo does not record its exclusion")
        else:
            c.ok(False, f"High risk {rid} ({row[band_col]}) has no auditor decision")

    # 4. challenges
    ch = read(out, "challenges.md", c)
    if ch is not None:
        lines = ch.splitlines()
        head = next((br.split_row(l) for l in lines if l.startswith("| # |")), None)
        if c.ok(head is not None, "challenges.md has no challenge table (header starting '| # |')"):
            low = [h.lower() for h in head]
            ci = next((i for i, h in enumerate(low) if h.startswith("challenge")), None)
            si = low.index("status") if "status" in low else None
            c.ok(ci is not None and si is not None, "challenges.md table needs Challenge and Status columns")
            figs = qa.load_json(out / "pack-figures.json") if (out / "pack-figures.json").exists() else {}
            rows = qa.md_table(lines, "#")
            if not rows:
                c.note("challenges.md records no challenges")
            for row in rows if ci is not None and si is not None else []:
                n = row[0]
                text = " ".join(row)
                good, bad = br.citations(text, ctx)
                packs = PACK_PATH.findall(text)
                pack_ok = []
                for p in packs:
                    try:
                        br.resolve({"pack": figs}, p)
                        pack_ok.append(p)
                    except KeyError:
                        bad.append(f"{p} does not resolve in pack-figures.json")
                for b in bad:
                    c.ok(False, f"challenge #{n}: {b}")
                c.ok(bool(good or pack_ok), f"challenge #{n} cites no evidence ([rule:], [metric:], [history:] "
                                            "or a $.pack path)")
                st = row[si].strip().lower()
                c.ok(st in CLOSED, f"challenge #{n} status is '{row[si]}'" + (" (still open)" if st == "open" else
                                   f"; must be one of {', '.join(CLOSED)}"))


if __name__ == "__main__":
    sys.exit(qa.run("trace", body))
