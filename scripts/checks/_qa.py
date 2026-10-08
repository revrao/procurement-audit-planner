"""Shared helpers for the QA checks in scripts/checks/ (loaded by path, so -I works).

Every check prints one line per failure, `FAIL <check>: <item>`, notes as
`NOTE <check>: <text>`, and ends with
`RESULT <check>: PASS|FAIL · checked <n> · failures <m>`.
Exit codes: 0 pass, 1 failures, 2 could not run (an input is missing).
"""
import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK_DOCS = ("planning-memo.md", "risk-control-matrix.md", "audit-program.md")
SPEND_FILE = "spend_clean.csv"

_spec = importlib.util.spec_from_file_location(
    "build_register", ROOT / ".claude/skills/risk-assessment/build_register.py")
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)


def parser(doc):
    ap = argparse.ArgumentParser(description=doc.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / "outputs"),
                    help="the pack: register, ratings, auditor comments, audit-plan.json, the three documents, "
                         "samples/, pack-figures.json, challenges.md (default outputs/)")
    ap.add_argument("--inputs", default=str(ROOT / "outputs"),
                    help="rules.json, analytics.json, history.json and analytics-full/ (default outputs/)")
    ap.add_argument("--data", default=str(ROOT / "data"), help="the council's source files (default data/)")
    return ap


class Stop(Exception):
    pass


class Check:
    def __init__(self, name):
        self.name, self.checked, self.failures = name, 0, 0

    def fail(self, item):
        self.failures += 1
        print(f"FAIL {self.name}: {item}")

    def note(self, text):
        print(f"NOTE {self.name}: {text}")

    def ok(self, cond, item):
        self.checked += 1
        if not cond:
            self.fail(item)
        return cond

    def finish(self):
        status = "PASS" if self.failures == 0 and self.checked > 0 else "FAIL"
        if self.checked == 0:
            print(f"FAIL {self.name}: nothing was checked")
            self.failures += 1
        print(f"RESULT {self.name}: {status} · checked {self.checked} · failures {self.failures}")
        return 0 if status == "PASS" else 1


def run(name, body):
    """Run body(check); a Stop prints STOP and exits 2."""
    c = Check(name)
    try:
        body(c)
    except Stop as e:
        print(f"STOP {name}: {e}")
        print(f"RESULT {name}: ERROR · checked {c.checked} · failures {c.failures}")
        return 2
    return c.finish()


def need(path, what=None):
    p = Path(path)
    if not p.exists():
        raise Stop(f"{what or p.name} not found: {p}")
    return p


def load_json(path):
    try:
        return json.loads(need(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Stop(f"{Path(path).name} is not valid JSON: {e}")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def md_table(lines, first_header):
    """Rows (lists of cells) of the markdown table whose header's first cell is first_header."""
    rows, inside = [], False
    for line in lines:
        if line.startswith("|"):
            cells = br.split_row(line)
            if not inside and cells and cells[0] == first_header:
                inside = True
                continue
            if inside and not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
        elif inside:
            break
    return rows


def decisions(out):
    """{risk_id: (decision, comment)} from auditor-comments.md."""
    d, _, _ = br.read_comments(need(Path(out) / "auditor-comments.md"))
    return {k: (v.get("decision", ""), v.get("comment", "")) for k, v in d.items()}


if __name__ == "__main__":
    sys.exit("helper module; run run_checks.py or a check_*.py script")
