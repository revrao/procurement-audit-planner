#!/usr/bin/env python3
"""Test verify_history.py against fixtures built from the real committee papers.

1. fixtures/verify_history/history-good.json must PASS (no false positives).
2. history-planted.json is history-good.json with the errors in PLANTED
   applied; it is rewritten on each run so the two never drift apart. The
   verifier must report exactly the planted (code, path) pairs: nothing
   missed, nothing extra.

Usage: test_verify_history.py      Exit 0 if both hold, 1 otherwise.
"""
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERIFY = HERE / "verify_history.py"
FIX = HERE / "fixtures" / "verify_history"
GOOD, PLANTED_FILE = FIX / "history-good.json", FIX / "history-planted.json"
LINE = re.compile(r"^ERROR \[(\w+)\] (\S+): ")


def plant(d):
    """Apply each planted error; return the (code, path) pairs expected."""
    sm, aud = d["scoring_method"], d["audits_completed"]
    exp = set()

    # quote on the wrong page: Table 2 is on p15, not p14
    sm["likelihood_scale"][2]["pdf_page"] = 14
    exp.add(("wrong_page", "$.scoring_method.likelihood_scale[2]"))
    # paraphrased cell
    aud[0]["quote"][1] = "Contract Letting audit"
    exp.add(("not_found", "$.audits_completed[0]"))
    # row stitched from plain text: Public Health paired with another row's audit
    aud[1].update(audit_title="Bank Reconciliation", opinion="Substantial Assurance",
                  quote=["Public Health", "Bank Reconciliation", "Substantial Assurance"])
    exp.add(("incoherent_row", "$.audits_completed[1]"))
    # opinion not copied from its quote
    aud[3]["opinion"] = "Substantial Assurance"
    exp.add(("value_not_in_quote", "$.audits_completed[3].opinion"))
    # invented score on a history item
    aud[2]["risk_score"] = 6
    exp.add(("scoring_forbidden", "$.audits_completed[2].risk_score"))
    # source that is not a committee paper
    d["follow_ups"][0]["source"] = "audit-completed-work-2023-24.pdf"
    exp.add(("bad_source", "$.follow_ups[0]"))
    # page beyond the end of a 2-page file
    d["advisory_reviews"][0]["pdf_page"] = 3
    exp.add(("bad_page", "$.advisory_reviews[0]"))
    # wrong page count for a source
    d["sources"][1]["pages"] = 2
    exp.add(("bad_source", "$.sources[1]"))
    # discrepancy with one ref, and one "resolved"
    d["discrepancies"][0]["refs"] = d["discrepancies"][0]["refs"][:1]
    exp.add(("discrepancy_refs", "$.discrepancies[0]"))
    d["discrepancies"][1]["resolution"] = "Table 4 is correct"
    exp.add(("discrepancy_resolved", "$.discrepancies[1]"))
    # typo silently corrected: the PDF says "extrene (Red)"
    sm["escalation"] = [{
        "source": "risk-management-strategy-2024-27.pdf", "pdf_page": 21, "section": "6.3",
        "quote": "Where risk levels are considered to be extreme (Red) on the risk matrix"}]
    exp.add(("not_found", "$.scoring_method.escalation[0]"))
    # matrix bands quoted out of order
    sm["matrix"]["rows"][1]["layout_rows"][0] = ["Moderate", "High", "Extreme", "High", "Extreme"]
    sm["matrix"]["rows"][1]["bands"] = ["Moderate", "High", "Extreme", "High", "Extreme"]
    exp.add(("layout_row_not_found", "$.scoring_method.matrix.rows[1].layout_rows[0]"))
    # matrix rows swapped (Minor below Negligible)
    rows = sm["matrix"]["rows"]
    rows[3], rows[4] = rows[4], rows[3]
    exp.add(("bad_matrix", "$.scoring_method.matrix.rows[4]"))
    # rebuilt cell that does not equal its fragments joined
    sm["impact_scale"][3]["financial"] = "0.01% - 0.1% of annual WBC budget £17.5k-£175k"
    exp.add(("value_not_in_quote", "$.scoring_method.impact_scale[3].financial"))
    # Strategic Risk Register absence dropped, and the agreed_actions gap
    d["gaps"] = [g for g in d["gaps"] if g["id"] not in ("GAP-04", "GAP-01")]
    exp.add(("missing_srr_gap", "$.gaps"))
    exp.add(("missing_gap", "$.agreed_actions"))
    # duplicate id (gaps are now GAP-02, GAP-03)
    d["gaps"][1]["id"] = "GAP-02"
    exp.add(("duplicate_id", "$.gaps[1]"))
    return exp


def run(path):
    out = subprocess.run([sys.executable, "-I", str(VERIFY), str(path)],
                         capture_output=True, text=True)
    found = {(m.group(1), m.group(2)) for l in out.stdout.splitlines() if (m := LINE.match(l))}
    return out.returncode, out.stdout, found


def main():
    ok = True
    code, out, found = run(GOOD)
    if code != 0 or found:
        ok = False
        print(f"FAIL good fixture: exit {code}\n{out}")
    else:
        print("ok   good fixture passes")

    data = copy.deepcopy(json.loads(GOOD.read_text(encoding="utf-8")))
    data["generated_by"] = "fixture: history-good.json with planted errors (see test_verify_history.py)"
    expected = plant(data)
    PLANTED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    code, out, found = run(PLANTED_FILE)
    missed, extra = expected - found, found - expected
    for c, p in sorted(expected & found):
        print(f"ok   caught [{c}] {p}")
    for c, p in sorted(missed):
        print(f"FAIL missed [{c}] {p}")
    for c, p in sorted(extra):
        print(f"FAIL unexpected [{c}] {p}")
    if code != 1 or missed or extra:
        ok = False
        if code != 1:
            print(f"FAIL planted fixture exit {code}, expected 1")
    print(f"{len(expected & found)}/{len(expected)} planted errors caught, {len(extra)} unexpected")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
