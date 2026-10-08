#!/usr/bin/env python3
"""Run the four QA checks on the audit planning pack and print one results table and a verdict.

Runs check_quotes.py, check_numbers.py, check_trace.py and check_samples.py
(in that order, each in its own process, with the same --out/--inputs/--data)
and prints:
  - the pack it checked (build time from pack-figures.json, sha256 of audit-plan.json);
  - one table: check, result (PASS / FAIL / ERROR), items checked, failures;
  - each check's failure lines (the first 25 per check, with the total);
  - VERDICT: READY FOR SIGN-OFF only if all four PASS, otherwise BLOCKED.

Usage: run_checks.py [--out DIR] [--inputs DIR] [--data DIR]
Exit 0 READY FOR SIGN-OFF, 1 BLOCKED.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("_qa", HERE / "_qa.py")
qa = importlib.util.module_from_spec(_s)
_s.loader.exec_module(qa)

CHECKS = [
    ("quotes", "check_quotes.py", "rules.json quotes are in the PDF; register rule excerpts match rules.json"),
    ("numbers", "check_numbers.py", "every figure in the three documents is a value in the analytics or pack outputs"),
    ("trace", "check_trace.py", "rule → risk → control → test complete; High risks in scope or excluded with "
                                "a reason; challenges cited and closed"),
    ("samples", "check_samples.py", "every sampled transaction is in spend_clean.csv and at its workbook row"),
]
RESULT = re.compile(r"^RESULT (\w+): (PASS|FAIL|ERROR) · checked (\d+) · failures (\d+)$")
SHOWN = 25


def main():
    a = qa.parser(__doc__).parse_args()
    args = ["--out", a.out, "--inputs", a.inputs, "--data", a.data]
    out = Path(a.out)
    fig, plan = out / "pack-figures.json", out / "audit-plan.json"
    built = json.loads(fig.read_text(encoding="utf-8")).get("built", "?") if fig.exists() else "not built"
    plan_hash = hashlib.sha256(plan.read_bytes()).hexdigest()[:16] + "…" if plan.exists() else "no audit-plan.json"
    print(f"QA checks on {out}: pack built: {built}; audit-plan.json sha256: {plan_hash}")
    print()

    rows, details = [], []
    for name, script, what in CHECKS:
        p = subprocess.run([sys.executable, "-I", str(HERE / script)] + args, capture_output=True, text=True)
        log = (p.stdout + p.stderr).splitlines()
        m = next((RESULT.match(l) for l in reversed(log) if RESULT.match(l)), None)
        if m:
            status, checked, failed = m.group(2), m.group(3), m.group(4)
        else:
            status, checked, failed = "ERROR", "0", "?"
        if status == "PASS" and p.returncode != 0:
            status = "ERROR"
        rows.append((name, status, checked, failed, what))
        bad = [l for l in log if l.startswith(("FAIL ", "STOP "))]
        if status == "ERROR" and not bad:
            bad = [f"STOP {name}: {script} exited {p.returncode}: " + " / ".join(log[-3:])]
        if bad:
            details.append((name, bad))

    print("| Check | Result | Checked | Failures | What it checks |")
    print("| --- | --- | --- | --- | --- |")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    print()
    for name, bad in details:
        print(f"{name}: {len(bad)} failure line(s)" + (f", first {SHOWN} shown (all: "
              f"scripts/checks/check_{name}.py)" if len(bad) > SHOWN else ""))
        for l in bad[:SHOWN]:
            print(f"  {l}")
        print()
    failed = [r[0] for r in rows if r[1] != "PASS"]
    if failed:
        print(f"VERDICT: BLOCKED ({len(failed)} of {len(rows)} checks not passed: {', '.join(failed)})")
        return 1
    print(f"VERDICT: READY FOR SIGN-OFF (all {len(rows)} checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
