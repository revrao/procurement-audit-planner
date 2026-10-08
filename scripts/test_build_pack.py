#!/usr/bin/env python3
"""Test .claude/skills/audit-program/build_pack.py.

Runs against the real outputs/analytics.json, analytics-full/, history.json
and rules.json (read only) with fixtures/build_pack/: risk-ratings.json holds
two risks (R-01 split purchases, R-05 duplicates) and audit-plan.json a good
plan for them. Each case builds a register for the fixture with
build_register.py in a temporary directory, takes it through the auditor gate
to revision 1, then runs build_pack.py there.

Usage: test_build_pack.py      Exit 0 if every case holds, 1 otherwise.
"""
import copy
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REGISTER = ROOT / ".claude/skills/risk-assessment/build_register.py"
PACK = ROOT / ".claude/skills/audit-program/build_pack.py"
FIX = HERE / "fixtures/build_pack"
RATINGS = json.loads((FIX / "risk-ratings.json").read_text())
PLAN = json.loads((FIX / "audit-plan.json").read_text())
FULL = ROOT / "outputs/analytics-full"
OUTPUTS = ("planning-memo.md", "risk-control-matrix.md", "audit-program.md", "pack-figures.json")
failures = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)
        if detail:
            print("     " + detail.strip().replace("\n", "\n     ")[:1500])


def sh(cmd):
    p = subprocess.run([sys.executable, "-I"] + [str(c) for c in cmd], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def set_decision(d, rid, decision, comment=""):
    p = Path(d) / "auditor-comments.md"
    s = re.sub(rf"^(\| {rid} \|(?:[^|\n]*\|){{5}})[^|\n]*\|[^|\n]*\|$",
               lambda m: f"{m.group(1)} {decision} | {comment} |", p.read_text(), flags=re.M)
    p.write_text(s)


def register(d, decisions=None, rejected=()):
    """Build the fixture register to revision 0, record decisions, rebuild as revision 1."""
    ratings = copy.deepcopy(RATINGS)
    rp = Path(d) / "risk-ratings.json"
    rp.write_text(json.dumps(ratings, indent=2))
    code, log = sh([REGISTER, "--ratings", rp, "--out-dir", d])
    assert code == 0, log
    if decisions is None:
        return
    for rid, (dec, com) in decisions.items():
        set_decision(d, rid, dec, com)
    changes = []
    for r in ratings["risks"]:
        if r["risk_id"] in rejected:
            r["status"] = "rejected"
            changes.append({"risk_id": r["risk_id"], "decision": "reject", "summary": "rejected as the auditor asked"})
    ratings["revision"] = {"number": 1, "changes": changes}
    rp.write_text(json.dumps(ratings, indent=2))
    code, log = sh([REGISTER, "--ratings", rp, "--out-dir", d])
    assert code == 0, log


APPROVE = {"R-01": ("approve", ""), "R-05": ("approve", "")}


def pack(d, plan=None, gate=False, full_dir=FULL):
    args = [PACK, "--ratings", Path(d) / "risk-ratings.json", "--register", Path(d) / "risk-register.md",
            "--comments", Path(d) / "auditor-comments.md", "--out-dir", d, "--full-dir", full_dir]
    if gate:
        args.append("--gate")
    else:
        pp = Path(d) / "audit-plan.json"
        pp.write_text(json.dumps(plan if plan is not None else PLAN, indent=2))
        args += ["--plan", pp]
    return sh(args)


def written(d):
    return [f for f in OUTPUTS if (Path(d) / f).exists()] + [p.name for p in (Path(d) / "samples").glob("*.csv")]


def failing(name, plan, expect, full_dir=FULL):
    """A broken plan fails with the expected error and writes nothing."""
    with tempfile.TemporaryDirectory() as d:
        register(d, APPROVE)
        code, log = pack(d, plan, full_dir=full_dir)
        check(f"{name}: fails naming it", code == 1 and re.search(expect, log) is not None, log)
        check(f"{name}: nothing written", not written(d), str(written(d)))


# 1. the gate
with tempfile.TemporaryDirectory() as d:
    register(d)
    code, log = pack(d, gate=True)
    check("gate fails on a revision-0 register", code == 1 and "revision 0" in log, log)
    register(d, {"R-01": ("approve", ""), "R-05": ("approve", "")})
    code, log = pack(d, gate=True)
    check("gate passes once both risks are decided and revised", code == 0 and "GATE PASSED" in log, log)
    set_decision(d, "R-05", "", "")
    code, log = pack(d, gate=True)
    check("gate fails when a register risk is undecided", code == 1 and "R-05: no auditor decision" in log, log)
    code, log = pack(d)
    check("full build also stops at the gate", code == 1 and "GATE FAILED" in log and not written(d), log)

# 2. the good fixture
with tempfile.TemporaryDirectory() as d:
    register(d, APPROVE)
    code, log = pack(d)
    check("fixture builds (exit 0)", code == 0 and "BUILT pack" in log, log)
    memo = (Path(d) / "planning-memo.md").read_text() if code == 0 else ""
    prog = (Path(d) / "audit-program.md").read_text() if code == 0 else ""
    rcm = (Path(d) / "risk-control-matrix.md").read_text() if code == 0 else ""
    fig = json.loads((Path(d) / "pack-figures.json").read_text()) if code == 0 else {"tests": {}, "totals": {}}
    check("three documents, three sample files and pack-figures.json written",
          sorted(written(d)) == sorted(list(OUTPUTS) + ["T-01.csv", "T-02.csv", "T-03.csv"]), str(written(d)))
    check("no unfilled placeholder in any document", "{{" not in memo + prog + rcm)
    check("audit program ends with the PBC list", prog.rstrip().split("\n## ")[-1].startswith("PBC list"))
    check("score 9 sizes each test at 15 items", all(t["target_size"] == 15 for t in fig["tests"].values()), str(fig["tests"]))
    spend = {r["row_id"]: r for r in csv.DictReader(open(FULL / "spend_clean.csv", newline=""))}
    rows = [r for t in ("T-01", "T-02", "T-03") if (Path(d) / f"samples/{t}.csv").exists()
            for r in csv.DictReader(open(Path(d) / f"samples/{t}.csv", newline=""))]
    check("every sampled transaction is in spend_clean.csv with the same amount",
          rows and all(r["row_id"] in spend and r["Net amount"] == spend[r["row_id"]]["Net amount"] for r in rows))
    check("pack-figures totals match the sample files",
          fig["totals"].get("sampled_transactions") == len(rows)
          and abs(fig["totals"].get("sampled_gbp", 0) - sum(float(r["Net amount"]) for r in rows)) < 0.01)
    t1 = [r for r in rows if r["test_id"] == "T-01"]
    check("T-01 follows its recipe (general procurement, quote threshold, largest first)",
          t1 and all(r["item_tag"] == "general_procurement" and r["item_boundary"] == "25000" for r in t1)
          and [float(r["item_sum_gbp"]) for r in t1] == sorted((float(r["item_sum_gbp"]) for r in t1), reverse=True))
    check("memo figures filled from analytics and pack figures",
          f"{fig['totals'].get('sampled_items')} items covering {fig['totals'].get('sampled_transactions', 0):,} transactions" in memo, memo[:0])
    check("every rule accounted for in the matrix", all(f"| {r} |" in rcm for r in ("CPR-01", "CPR-13", "CPR-66")))
    check("placeholders recorded in pack-figures.json",
          any(p["path"] == "$.pack.totals.sampled_items" for p in fig.get("placeholders", [])))
    snap = {f: (Path(d) / "samples" / f).read_bytes() for f in ("T-01.csv", "T-02.csv", "T-03.csv")}
    pack(d)
    check("rebuild draws identical samples",
          all((Path(d) / "samples" / f).read_bytes() == b for f, b in snap.items()))

# 3. the three named failures
p = copy.deepcopy(PLAN)
p["risks"] = [r for r in p["risks"] if r["risk_id"] != "R-05"]
failing("missing risk (R-05 approved but not planned)", p, r"R-05 is approved by the auditor but missing")

p = copy.deepcopy(PLAN)
p["risks"][1]["controls"][0]["control"] = "Every payment is supported by written evidence of the purchase."
failing("uncited control (C-03)", p, r"C-03: the expected control cites no rule")

p = copy.deepcopy(PLAN)
p["rules_not_tested"] = [e for e in p["rules_not_tested"] if e["rule_id"] != "CPR-01"]
failing("unaccounted rule (CPR-01)", p, r"CPR-01 \(clause 3\.5\) is not cited")

# 4. other checks
p = copy.deepcopy(PLAN)
p["risks"][0]["tests"][1]["controls"] = ["C-01"]
p["risks"][0]["tests"][0]["controls"] = ["C-01"]
failing("control with no test (C-02)", p, r"C-02: no test tests this control")

p = copy.deepcopy(PLAN)
p["risks"][0]["tests"][0]["step"] = "Check the groups against the quote route."
failing("test step with no rule or metric", p, r"T-01: the test step cites no rule or metric")

p = copy.deepcopy(PLAN)
p["memo"]["approach"] += " About 45 items will be examined."
failing("typed figure in the memo", p, r"memo\.approach: figure typed in prose '45'")

p = copy.deepcopy(PLAN)
p["memo"]["objective"] += " It will show where suppliers committed fraud."
failing("accusatory wording", p, r"'fraud' reads as an accusation")

p = copy.deepcopy(PLAN)
p["risks"][0]["tests"][0]["sample"]["size"] = 5
failing("sample smaller than the score requires", p, r"T-01: sample\.size 5 is below 15")

p = copy.deepcopy(PLAN)
p["risks"][0]["tests"][0]["sample"]["file"] = "spend_clean.csv"
failing("sample from a file that is not a flagged list", p, r"T-01: sample file 'spend_clean.csv' is not a test's full list")

p = copy.deepcopy(PLAN)
p["rules_not_tested"].append({"rule_id": "CPR-13", "reason": "duplicate"})
failing("rule both cited and listed as not tested", p, r"CPR-13 is cited by .* and also listed as not tested")

with tempfile.TemporaryDirectory() as fd:
    for f in FULL.iterdir():
        shutil.copy(f, fd)
    dup = list(csv.DictReader(open(Path(fd) / "duplicates.csv", newline="")))
    top = max((r for r in dup if r["tag"] == "general_procurement"), key=lambda r: float(r["repeat_gbp"]))
    top["row_ids"] = top["row_ids"].replace(top["row_ids"].split(";")[0], "Over500_2026_P99_-_published:1", 1)
    with open(Path(fd) / "duplicates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dup[0]))
        w.writeheader()
        w.writerows(dup)
    failing("sampled transaction not in spend_clean.csv", PLAN, r"T-03 item at line \d+: 1 transaction\(s\) not in spend_clean\.csv",
            full_dir=fd)

# 5. a rejected risk leaves scope
with tempfile.TemporaryDirectory() as d:
    register(d, {"R-01": ("approve", ""), "R-05": ("reject", "Covered by the accounts payable audit")}, rejected=("R-05",))
    code, log = pack(d)
    check("planning a rejected risk fails", code == 1 and "R-05 was rejected by the auditor" in log, log)
    p = copy.deepcopy(PLAN)
    p["risks"] = p["risks"][:1]
    p["rules_not_tested"].append({"rule_id": "CPR-32", "reason": "Its only risk (R-05) was rejected by the auditor."})
    code, log = pack(d, p)
    memo = (Path(d) / "planning-memo.md").read_text() if code == 0 else ""
    check("without it the pack builds and lists R-05 as out of scope",
          code == 0 and "Out of scope (rejected by the auditor)" in memo and "Covered by the accounts payable audit" in memo, log)

print(f"\n{'PASS' if not failures else 'FAIL'}: {len(failures)} failing case(s)")
sys.exit(1 if failures else 0)
