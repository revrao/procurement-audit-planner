#!/usr/bin/env python3
"""Test the QA checks in scripts/checks/.

1. Current outputs: runs run_checks.py on outputs/ as it stands and shows the
   table; the quote check must pass, and with no pack built yet the other
   three must fail naming the missing pack (never pass on nothing).
2. A fixture pack: builds the build_pack fixture (fixtures/build_pack: R-01
   and R-05, both approved) through the gate in a temporary directory,
   adds fixtures/checks/challenges.md, and expects all four checks to pass.
3. Planted faults, each on a fresh copy of the fixture pack:
   - a bad figure in planning-memo.md            -> numbers FAIL naming it
   - a sampled row missing from spend_clean.csv  -> samples FAIL naming it
   - a sample row_id that does not exist         -> samples FAIL
   - a sample amount that differs from the data  -> samples FAIL
   - a row ID in audit-program.md not in the data -> samples FAIL
   - a register rule excerpt with a wrong clause  -> quotes FAIL
   - a rule dropped from rules_not_tested        -> trace FAIL
   - a challenge left open                       -> trace FAIL
   and in each case every other check still passes and the verdict is BLOCKED.

Usage: test_checks.py      Exit 0 if every case holds, 1 otherwise.
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
CHECKS = HERE / "checks"
REGISTER = ROOT / ".claude/skills/risk-assessment/build_register.py"
PACK = ROOT / ".claude/skills/audit-program/build_pack.py"
FIX = HERE / "fixtures/build_pack"
CHALLENGES = HERE / "fixtures/checks/challenges.md"
OUTPUTS = ROOT / "outputs"
NAMES = ("quotes", "numbers", "trace", "samples")
failures = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)
        if detail:
            print("     " + detail.strip().replace("\n", "\n     ")[:2000])


def sh(cmd):
    p = subprocess.run([sys.executable, "-I"] + [str(x) for x in cmd], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def run_checks(out, inputs=OUTPUTS):
    code, log = sh([CHECKS / "run_checks.py", "--out", out, "--inputs", inputs])
    table = {m.group(1): m.group(2) for m in re.finditer(r"^\| (\w+) \| (PASS|FAIL|ERROR) \|", log, re.M)}
    return code, log, table


def build_fixture(d):
    """The build_pack fixture through the auditor gate to a built pack, plus a closed challenges.md."""
    ratings = json.loads((FIX / "risk-ratings.json").read_text())
    rp = Path(d) / "risk-ratings.json"
    rp.write_text(json.dumps(ratings, indent=2))
    code, log = sh([REGISTER, "--ratings", rp, "--out-dir", d])
    assert code == 0, log
    cp = Path(d) / "auditor-comments.md"
    s = cp.read_text()
    for rid in ("R-01", "R-05"):
        s = re.sub(rf"^(\| {rid} \|(?:[^|\n]*\|){{5}})[^|\n]*\|[^|\n]*\|$", lambda m: f"{m.group(1)} approve |  |",
                   s, flags=re.M)
    cp.write_text(s)
    ratings["revision"] = {"number": 1, "changes": []}
    rp.write_text(json.dumps(ratings, indent=2))
    code, log = sh([REGISTER, "--ratings", rp, "--out-dir", d])
    assert code == 0, log
    pp = Path(d) / "audit-plan.json"
    shutil.copy(FIX / "audit-plan.json", pp)
    code, log = sh([PACK, "--ratings", rp, "--register", Path(d) / "risk-register.md", "--comments", cp,
                    "--plan", pp, "--out-dir", d])
    assert code == 0 and "BUILT pack" in log, log
    shutil.copy(CHALLENGES, Path(d) / "challenges.md")


def planted(name, plant, expect_check, expect_text):
    """Copy the fixture pack, plant one fault, expect exactly one check to fail naming it."""
    with tempfile.TemporaryDirectory() as d:
        shutil.copytree(BASE, d, dirs_exist_ok=True)
        inputs = plant(Path(d)) or OUTPUTS
        code, log, table = run_checks(d, inputs)
        others = {k: v for k, v in table.items() if k != expect_check}
        check(f"{name}: {expect_check} FAIL naming it",
              table.get(expect_check) == "FAIL" and re.search(expect_text, log) is not None, log)
        check(f"{name}: the other checks still PASS", others and all(v == "PASS" for v in others.values()),
              str(table) + "\n" + log)
        check(f"{name}: verdict BLOCKED, exit 1", code == 1 and "VERDICT: BLOCKED" in log, log[-300:])


def read_rows(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(p, rows):
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# 1. current outputs
code, log, table = run_checks(OUTPUTS)
print(log)
check("current outputs: the four checks ran", sorted(table) == sorted(NAMES), str(table))
check("current outputs: quote check PASS", table.get("quotes") == "PASS", log)
if not (OUTPUTS / "audit-plan.json").exists():
    check("current outputs, no pack yet: numbers, trace, samples FAIL and the verdict is BLOCKED",
          all(table.get(k) == "FAIL" for k in ("numbers", "trace", "samples")) and code == 1
          and "has not been built" in log, log)
else:
    print(f"     (current pack verdict: {'READY FOR SIGN-OFF' if code == 0 else 'BLOCKED'})")

with tempfile.TemporaryDirectory() as BASE:
    build_fixture(BASE)

    # 2. the good fixture
    code, log, table = run_checks(BASE)
    check("fixture pack: all four checks PASS", table == {k: "PASS" for k in NAMES}, log)
    check("fixture pack: verdict READY FOR SIGN-OFF, exit 0", code == 0 and "VERDICT: READY FOR SIGN-OFF" in log, log)

    # 3. planted faults
    def bad_figure(d):
        p = d / "planning-memo.md"
        s = p.read_text()
        m = re.search(r"In total \d+ items, [\d,]+ transactions, £([\d,]+\.\d\d)", s)
        assert m, "memo total line not found"
        v = float(m.group(1).replace(",", "")) + 1
        p.write_text(s[:m.start(1)] + f"{v:,.2f}" + s[m.end(1):])
    planted("bad figure in the memo", bad_figure, "numbers", r"FAIL numbers: planning-memo\.md:\d+ '£[\d,]+\.\d\d' is not")

    def missing_spend_row(d):
        inp = d / "_inputs"
        (inp / "analytics-full").mkdir(parents=True)
        for f in ("analytics.json", "rules.json", "history.json"):
            (inp / f).symlink_to(OUTPUTS / f)
        gone = read_rows(d / "samples/T-01.csv")[0]["row_id"]
        rows = [r for r in read_rows(OUTPUTS / "analytics-full/spend_clean.csv") if r["row_id"] != gone]
        write_rows(inp / "analytics-full/spend_clean.csv", rows)
        return inp
    planted("sampled row missing from spend_clean.csv", missing_spend_row, "samples",
            r"FAIL samples: samples/T-01\.csv:2: \S+ is not in spend_clean\.csv")

    def bad_row_id(d):
        p = d / "samples/T-02.csv"
        rows = read_rows(p)
        rows[0]["row_id"] = rows[0]["month_file"] + ":999999"
        write_rows(p, rows)
    planted("sample row_id that does not exist", bad_row_id, "samples", r"samples/T-02\.csv:2: \S+:999999 is not in")

    def bad_amount(d):
        p = d / "samples/T-03.csv"
        rows = read_rows(p)
        rows[0]["Net amount"] = f"{float(rows[0]['Net amount']) + 10:.2f}"
        write_rows(p, rows)
    planted("sample amount differs from the data", bad_amount, "samples", r"samples/T-03\.csv:2: \S+ amount")

    def bad_program_id(d):
        p = d / "audit-program.md"
        stem = read_rows(d / "samples/T-01.csv")[0]["month_file"]
        p.write_text(p.read_text().replace("**Test step.**", f"**Test step.** (see {stem}:999999)", 1))
    planted("row ID in audit-program.md not in the data", bad_program_id, "samples",
            r"FAIL samples: audit-program\.md:\d+: \S+:999999 is not in spend_clean\.csv")

    def bad_excerpt(d):
        p = d / "risk-register.md"
        s, n = re.subn(r"^(\s*- CPR-13: clause )6\.16(,)", r"\g<1>6.17\2", p.read_text(), count=1, flags=re.M)
        assert n == 1, "CPR-13 source line not found in the fixture register"
        p.write_text(s)
    planted("register rule excerpt with a wrong clause", bad_excerpt, "quotes",
            r"FAIL quotes: risk-register\.md:\d+ CPR-13 clause '6\.17', rules\.json says '6\.16'")

    def dropped_rule(d):
        p = d / "audit-plan.json"
        plan = json.loads(p.read_text())
        gone = plan["rules_not_tested"].pop(0)["rule_id"]
        p.write_text(json.dumps(plan, indent=2))
    planted("rule dropped from rules_not_tested", dropped_rule, "trace",
            r"FAIL trace: CPR-\d+ is not cited by an in-scope risk, control or test and not listed as not tested")

    def open_challenge(d):
        p = d / "challenges.md"
        p.write_text(p.read_text().replace("| declined | | |", "| open | | |", 1))
    planted("challenge left open", open_challenge, "trace", r"FAIL trace: challenge #3 status is 'open' \(still open\)")

print()
if failures:
    print(f"{len(failures)} case(s) failed")
    sys.exit(1)
print("all cases hold")
