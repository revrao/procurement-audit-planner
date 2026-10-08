#!/usr/bin/env python3
"""Test .claude/skills/risk-assessment/build_register.py.

Runs against the real outputs/analytics.json, history.json and rules.json
(read only) with fixtures/build_register/risk-ratings.json: R-01 is a good
risk, R-02 is broken (citations that do not resolve, a typed figure, an
uplift on a non-adverse audit). Every case writes to a temporary directory.

Usage: test_build_register.py      Exit 0 if every case holds, 1 otherwise.
"""
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = ROOT / ".claude/skills/risk-assessment/build_register.py"
FIXTURE = HERE / "fixtures/build_register/risk-ratings.json"
ANALYTICS = json.loads((ROOT / "outputs/analytics.json").read_text())
failures = []


def run(ratings, out, history=None):
    rp = Path(out) / "risk-ratings.json"
    rp.write_text(json.dumps(ratings, indent=2))
    cmd = [sys.executable, str(BUILD), "--ratings", str(rp), "--out-dir", str(out)]
    if history:
        hp = Path(out) / "history.json"
        hp.write_text(json.dumps(history))
        cmd += ["--history", str(hp)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def read(out, name):
    """The file as a reader sees it: the register-meta comment is removed."""
    f = Path(out) / name
    return re.sub(r"<!-- register-meta\n.*?\n-->\n", "", f.read_text(), flags=re.S) if f.exists() else ""


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)
        if detail:
            print("     " + detail.strip().replace("\n", "\n     ")[:1500])


def set_decision(out, rid, decision, comment=""):
    p = Path(out) / "auditor-comments.md"
    s = re.sub(rf"^(\| {rid} \|(?:[^|\n]*\|){{5}})[^|\n]*\|[^|\n]*\|$",
               lambda m: f"{m.group(1)} {decision} | {comment} |", p.read_text(), flags=re.M)
    p.write_text(s)


base = json.loads(FIXTURE.read_text())
good = base["risks"][0]
only_good = {"risks": [copy.deepcopy(good)]}

# 1. the fixture: good risk kept, broken risk dropped
with tempfile.TemporaryDirectory() as d:
    code, log = run(base, d)
    reg, com = read(d, "risk-register.md"), read(d, "auditor-comments.md")
    check("fixture builds (exit 0)", code == 0, log)
    check("broken R-02 is dropped with its unresolved citations named",
          "DROPPED R-02" in log and "CPR-99" in log and "AUD-99" in log and "expired_contracts" in log, log)
    check("R-02 listed under Excluded risks, absent from comments",
          "## Excluded risks" in reg and "| R-02 |" in reg.split("## Excluded risks")[1] and "R-02" not in com)
    gp = ANALYTICS["tests"]["split_purchases"]["by_tag"]["general_procurement"]["items"]
    tot = ANALYTICS["tests"]["split_purchases"]["gbp_total"]
    check("placeholders filled from analytics.json",
          f"{gp:,} general-procurement" in reg and f"£{tot:,.2f}" in reg and "{{" not in reg, reg[:0])
    check("R-01 scored 4 x 3 = 12, Figure 1 High, Table 4 Medium - High",
          re.search(r"\| R-01 \| .* \| 4 Almost Certain \| 3 Medium \| 12 \| High \| Medium - High \(Amber\) \| No † \|", reg)
          is not None, reg)
    check("conflicting thresholds stated in the header",
          all(f"| {x} |" in reg for x in ("DIS-01", "DIS-02", "DIS-03", "DIS-04")))
    check("register ends with Auditor decisions", reg.rstrip().split("\n## ")[-1].startswith("Auditor decisions"))
    check("comments template has a blank row for R-01",
          re.search(r"^\| R-01 \| .* \| 12 \| Medium - High \|  \|  \|$", com, re.M) is not None, com)

    # 2. decisions survive a rebuild
    set_decision(d, "R-01", "approve", "agreed")
    Path(d, "auditor-comments.md").write_text(read(d, "auditor-comments.md") + "\nAdd an agency staff risk.\n")
    code, log = run(base, d)
    com = read(d, "auditor-comments.md")
    check("decision and general comment kept on rewrite",
          code == 0 and "| approve | agreed |" in com and "Add an agency staff risk." in com, com)

# 3. repeat-finding uplift
with tempfile.TemporaryDirectory() as d:
    r = copy.deepcopy(only_good)
    r["risks"][0]["likelihood"]["uplift"] = {"justification": "Contract Letting again [history:AUD-01]"}
    code, log = run(r, d)
    check("uplift citing a Reasonable Assurance audit fails", code == 1 and "adverse" in log, log)
    r["risks"][0]["likelihood"]["uplift"] = {"justification": "Repeat theme [history:FU-03]"}
    code, log = run(r, d)
    reg = read(d, "risk-register.md")
    check("uplift citing a Limited Assurance follow-up raises 4 to 5 (score 15, Extreme, CRR)",
          code == 0 and re.search(r"\| R-01 \| .* \| 5 Certain \| 3 Medium \| 15 \| Extreme \| Extreme \(Red\) \| Yes \|", reg)
          is not None and "uplift: +1** (base 4 → 5)" in reg, log + reg[-3000:])

# 4. likelihood rubric
with tempfile.TemporaryDirectory() as d:
    r = copy.deepcopy(only_good)
    r["risks"][0]["likelihood"]["justification"] = (
        "Clustering under thresholds [metric:$.tests.threshold_clustering.by_tag.general_procurement.items]")
    code, log = run(r, d)
    check("likelihood 4 on one test's evidence fails the rubric", code == 1 and "exceeds the rubric level 3" in log, log)
    r["risks"][0]["likelihood"]["justification"] += (
        " Population [metric:$.tests.high_value_suppliers.by_tag.general_procurement.items]")
    code, log = run(r, d)
    check("high_value_suppliers (population) does not raise the rubric level",
          code == 1 and "exceeds the rubric level 3" in log, log)
    r["risks"][0]["likelihood"]["score"] = 2
    code, log = run(r, d)
    check("likelihood below the rubric level without a reason fails", code == 1 and "below_rubric_reason" in log, log)
    r["risks"][0]["likelihood"]["below_rubric_reason"] = (
        "most clustered items are low-value placements [metric:$.tests.threshold_clustering.by_tag.placement.items]")
    code, log = run(r, d)
    check("likelihood below the rubric level with a cited reason builds", code == 0, log)

# 5. typed figures and a bad placeholder
with tempfile.TemporaryDirectory() as d:
    r = copy.deepcopy(only_good)
    r["risks"][0]["proposed_focus"] += " Start with payments over £12,000 and the 45% share."
    code, log = run(r, d)
    check("typed figures warned, build still succeeds",
          code == 0 and "typed in prose '£12,000'" in log and "'45%'" in log, log)
    r["risks"][0]["evidence"].append("{{$.tests.split_purchases.nope}} [metric:$.tests.split_purchases.counts.items]")
    code, log = run(r, d)
    check("unfillable placeholder in a kept risk fails", code == 1 and "cannot be filled" in log, log)

# 6. a scoring-method conflict with no declared choice stops the build
with tempfile.TemporaryDirectory() as d:
    h = json.loads((ROOT / "outputs/history.json").read_text())
    h["discrepancies"].append({"id": "DIS-99", "description": "Table 2 gives two probabilities for Likely.",
                               "refs": [{"source": "risk-management-strategy-2024-27.pdf", "pdf_page": 15,
                                         "section": "Table 2. Likelihood Ratings"}]})
    code, log = run(only_good, d, history=h)
    check("undeclared scoring conflict fails", code == 1 and "DIS-99 is a conflict" in log, log)
    h = json.loads((ROOT / "outputs/history.json").read_text())
    h["scoring_method"] = {"status": "not usable: the strategy has no scale"}
    code, log = run(only_good, d, history=h)
    reg = read(d, "risk-register.md")
    check("no usable method: fallback scale stated in the header",
          code == 0 and "**Fallback scale.**" in reg and "| 4 High | 3 Medium | 12 |" in reg, log + reg[:1500])

# 7. revision after the gate
with tempfile.TemporaryDirectory() as d:
    code, log = run(only_good, d)
    rev = copy.deepcopy(only_good)
    rev["revision"] = {"number": 1, "changes": []}
    code, log = run(rev, d)
    check("revision with an undecided risk fails", code == 1 and "no auditor decision" in log, log)

    set_decision(d, "R-01", "approve")
    r = copy.deepcopy(rev)
    r["risks"][0]["title"] = "Purchases split under thresholds"
    code, log = run(r, d)
    check("approved risk changed without request fails", code == 1 and "did not ask" in log, log)

    set_decision(d, "R-01", "reject", "Covered by the Accounts Payable audit")
    code, log = run(rev, d)
    check("rejected risk left in scope fails as unapplied", code == 1 and "decision unapplied" in log, log)

    set_decision(d, "R-01", "amend", "Lower likelihood to 3: much of the signal is small values")
    code, log = run(rev, d)
    check("amend with nothing changed fails as unapplied", code == 1 and "nothing changed" in log, log)

    r = copy.deepcopy(rev)
    r["risks"][0]["likelihood"]["score"] = 3
    r["risks"][0]["likelihood"]["below_rubric_reason"] = (
        "auditor judged much of the signal to be small values [metric:$.tests.threshold_clustering.by_tag.placement.items]")
    code, log = run(r, d)
    check("change not listed in revision.changes fails", code == 1 and "not listed in revision.changes" in log, log)

    r["revision"]["changes"] = [{"risk_id": "R-01", "decision": "amend", "summary": "likelihood 4 → 3 as asked"}]
    code, log = run(r, d)
    reg = read(d, "risk-register.md")
    check("applied amend builds revision 1 with header and override mark",
          code == 0 and "**Revision 1**" in reg and "## Revision 1: what changed" in reg
          and "Likelihood 3 (auditor override; was 4)" in reg and "| R-01 ✱ |" in reg, log + reg[:2500])
    code, log = run(r, d)
    check("re-running the same revision is stable", code == 0 and "Likelihood 3 (auditor override; was 4)" in read(d, "risk-register.md"), log)

print()
print("PASS" if not failures else f"FAIL: {len(failures)} case(s)")
sys.exit(1 if failures else 0)
