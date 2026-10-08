#!/usr/bin/env python3
"""QA quote check: rules.json quotes are in the PDF, and the register quotes rules.json faithfully.

1. Runs the extract-rules verifier (.claude/skills/extract-rules/verify_quotes.py)
   on rules.json against data/contract-rules.pdf: every verbatim_quote on its
   stated page, thresholds in their quotes, every clause covered. Its ERROR
   lines are failures; its WARNING lines are passed on as notes.
2. Checks every rule excerpt in risk-register.md against rules.json:
   - each "Sources cited" line `CPR-xx: clause X, pN: <condition>` names a
     rule in rules.json with that clause, page and condition;
   - each inline reference `[CPR-xx, cl. X]` names that rule's clause;
   - any quoted text ("…") on a line naming a rule is copy-exact from that
     rule's verbatim_quote (typographic quotes, dashes and spacing aside;
     an ellipsis may join excerpts);
   - every rule ID the register mentions exists in rules.json.

Usage: check_quotes.py [--out DIR] [--inputs DIR] [--data DIR]
Exit 0 pass, 1 failures, 2 could not run.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

_s = importlib.util.spec_from_file_location("_qa", Path(__file__).resolve().parent / "_qa.py")
qa = importlib.util.module_from_spec(_s)
_s.loader.exec_module(qa)

VERIFIER = qa.ROOT / ".claude/skills/extract-rules/verify_quotes.py"
SOURCE_LINE = re.compile(r"^\s*- (CPR-\d+): clause (.+?), p(\d+): (.*)$")
INLINE = re.compile(r"\[(CPR-\d+), cl\. ([^\]]+)\]")
RULE_ID = re.compile(r"\bCPR-\d+\b")
QUOTED = re.compile(r"[\"“]([^\"”]{8,})[\"”]")
TYPO = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def norm(s):
    return re.sub(r"\s+", " ", s.translate(TYPO)).strip()


def body(c):
    a = qa.parser(__doc__).parse_args()
    out, inputs, data = Path(a.out), Path(a.inputs), Path(a.data)
    rules_path = qa.need(inputs / "rules.json")
    pdf = qa.need(data / "contract-rules.pdf")
    qa.need(VERIFIER, "extract-rules verifier")

    # 1. the extract-rules verifier
    p = subprocess.run([sys.executable, "-I", str(VERIFIER), str(rules_path), "--pdf", str(pdf)],
                       capture_output=True, text=True)
    log = (p.stdout + p.stderr).splitlines()
    if p.returncode == 2:
        raise qa.Stop("verify_quotes.py could not run: " + " / ".join(log[-3:]))
    errors = [l for l in log if l.startswith("ERROR")]
    c.ok(p.returncode == 0 and not errors,
         f"verify_quotes.py exit {p.returncode}" + (f": {len(errors)} error(s)" if errors else ""))
    for e in errors:
        c.fail(f"verify_quotes.py {e}")
    for w in (l for l in log if l.startswith("WARNING")):
        c.note(f"verify_quotes.py {w}")

    # 2. the register against rules.json
    rules = {r["rule_id"]: r for r in qa.load_json(rules_path).get("rules", [])}
    reg = qa.need(out / "risk-register.md").read_text(encoding="utf-8")
    reg = re.sub(r"<!--.*?-->", "", reg, flags=re.S)  # the register-meta block is not rendered text
    for n, line in enumerate(reg.splitlines(), start=1):
        where = f"risk-register.md:{n}"
        m = SOURCE_LINE.match(line)
        if m:
            rid, clause, page, cond = m.groups()
            r = rules.get(rid)
            if c.ok(r is not None, f"{where} {rid} is not in rules.json"):
                c.ok(r["clause"] == clause, f"{where} {rid} clause '{clause}', rules.json says '{r['clause']}'")
                c.ok(str(r["page"]) == page, f"{where} {rid} page {page}, rules.json says {r['page']}")
                c.ok(norm(r["condition"]) == norm(cond),
                     f"{where} {rid} condition '{cond[:80]}' differs from rules.json '{r['condition'][:80]}'")
        for m in INLINE.finditer(line):
            rid, clause = m.groups()
            r = rules.get(rid)
            if c.ok(r is not None, f"{where} [{rid}] is not in rules.json"):
                c.ok(r["clause"] == clause.strip(), f"{where} [{rid}, cl. {clause}] but rules.json clause is '{r['clause']}'")
        named = set(RULE_ID.findall(line))
        for rid in named - set(rules):
            c.ok(False, f"{where} mentions {rid}, which is not in rules.json")
        named &= set(rules)
        if named:
            for q in QUOTED.findall(line):
                parts = [norm(x) for x in re.split(r"…|\.\.\.", q) if norm(x)]
                found = any(all(x in norm(rules[rid]["verbatim_quote"]) for x in parts) for rid in named)
                c.ok(found, f"{where} quoted text \"{q[:80]}\" is not in the verbatim_quote of "
                            f"{', '.join(sorted(named))}")
    c.note(f"{len(rules)} rules in rules.json; register excerpts checked against them")


if __name__ == "__main__":
    sys.exit(qa.run("quotes", body))
