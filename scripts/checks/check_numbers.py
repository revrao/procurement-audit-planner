#!/usr/bin/env python3
"""QA number check: every figure in the pack documents is a value in the analytics or the pack's own outputs.

Scans planning-memo.md, risk-control-matrix.md and audit-program.md. A figure
is any number with a £ sign, or with three or more digits (separators and a
% sign aside). Each must equal, at the precision shown, a value in
analytics.json, pack-figures.json, rules.json or outputs/samples/*.csv
(numeric values, and numbers written inside their text values). A % figure
matches a fraction (12.3% = 0.123) or the same number. £…k / £…m are read as
thousands / millions.

Skipped, as not figures: anything inside `code` spans (paths, column names,
JSON paths); numbers joined to letters, `_`, `/`, `:`, `-` or `.` (row IDs
such as Over500_…:123, rule, risk, control, test and PBC IDs, dates, times,
page references such as p14, version-like 6.16.1); bare years 1900-2099;
numbers after a clause, section, paragraph, table, figure, appendix, row,
page or part reference word.

Usage: check_numbers.py [--out DIR] [--inputs DIR] [--data DIR]
Exit 0 pass, 1 failures, 2 could not run.
"""
import bisect
import importlib.util
import json
import re
import sys
from pathlib import Path

_s = importlib.util.spec_from_file_location("_qa", Path(__file__).resolve().parent / "_qa.py")
qa = importlib.util.module_from_spec(_s)
_s.loader.exec_module(qa)

TOKEN = re.compile(r"£\s?-?\d[\d,]*(?:\.\d+)?(?:\s?[kKmM](?![A-Za-z]))?|-?\d[\d,]*(?:\.\d+)?%?")
JOINED = set("_/:-.") | set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
CODE = re.compile(r"`[^`\n]*`")


def parse(tok):
    """(value, tolerance, is_pct) for a figure token, or None if it is not a number."""
    t = tok.replace("£", "").replace(",", "").replace(" ", "")
    pct = t.endswith("%")
    mult = {"k": 1e3, "m": 1e6}.get(t[-1].lower(), 1) if t[-1] in "kKmM" else 1
    t = t.rstrip("%kKmM")
    try:
        v = float(t)
    except ValueError:
        return None
    dec = len(t.split(".")[1]) if "." in t else 0
    return v * mult, 0.5 * 10 ** (-dec) * mult + 1e-9, pct


def figures(text):
    """Yield (token, line_no) for every figure the check applies to."""
    for n, line in enumerate(text.splitlines(), start=1):
        line = CODE.sub(lambda m: " " * len(m.group(0)), line)
        for m in TOKEN.finditer(line):
            tok, s = m.group(0).rstrip(","), m.start()
            e = s + len(tok)
            gbp = tok.startswith("£")
            first = s if gbp or not tok.startswith("-") else s + 1
            prev = line[first - 1] if first > 0 else " "
            if tok.startswith("-") and prev in JOINED:
                continue  # an ID such as CPR-13 or T-01
            if not gbp and prev in JOINED:
                continue
            nxt = line[e] if e < len(line) else " "
            if nxt in JOINED - {"."} or (nxt == "." and line[e + 1:e + 2].isdigit()):
                continue
            digits = sum(ch.isdigit() for ch in tok)
            if not gbp and digits < 3:
                continue
            if not gbp and re.fullmatch(r"(19|20)\d\d", tok):
                continue  # a year
            if not gbp and qa.br.NUM_EXEMPT_BEFORE.search(line[max(0, s - 12):s]):
                continue  # clause, page, table, row … reference
            yield tok, n


def harvest(x, vals):
    """Numeric leaves of a JSON value, and numbers written inside its strings."""
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        vals.append(float(x))
    elif isinstance(x, str):
        harvest_text(x, vals)
    elif isinstance(x, dict):
        for v in x.values():
            harvest(v, vals)
    elif isinstance(x, list):
        for v in x:
            harvest(v, vals)


def harvest_text(s, vals):
    try:
        vals.append(float(s.replace(",", "")))
        return
    except ValueError:
        pass
    for m in TOKEN.finditer(s):
        p = parse(m.group(0).rstrip(","))
        if p:
            vals.append(p[0])


def body(c):
    a = qa.parser(__doc__).parse_args()
    out, inputs = Path(a.out), Path(a.inputs)
    vals, sources = [], {}
    for path in (inputs / "analytics.json", out / "pack-figures.json", inputs / "rules.json"):
        if path.name == "pack-figures.json" and not path.exists():
            c.fail("pack-figures.json not found: the pack has not been built")
            continue
        before = len(vals)
        harvest(qa.load_json(path), vals)
        sources[path.name] = len(vals) - before
    samples = sorted((out / "samples").glob("*.csv"))
    if not samples:
        c.fail("outputs/samples/ holds no sample files")
    before = len(vals)
    for p in samples:
        for row in qa.read_csv(p):
            for v in row.values():
                if v:
                    harvest_text(v, vals)
    sources["samples/*.csv"] = len(vals) - before
    vals = sorted(set(vals))
    pcts = sorted({v * 100 for v in vals})

    def found(v, tol, pct):
        for pool in ([vals, pcts] if pct else [vals]):
            i = bisect.bisect_left(pool, v - tol)
            if i < len(pool) and pool[i] <= v + tol:
                return True
        return False

    for name in qa.PACK_DOCS:
        p = out / name
        if not c.ok(p.exists(), f"{name} not found: the pack has not been built"):
            continue
        for tok, n in figures(p.read_text(encoding="utf-8")):
            v, tol, pct = parse(tok)
            c.ok(found(v, tol, pct),
                 f"{name}:{n} '{tok}' is not a value in analytics.json, pack-figures.json, rules.json or samples/*.csv")
    c.note("values available: " + ", ".join(f"{k} {v}" for k, v in sources.items()))


if __name__ == "__main__":
    sys.exit(qa.run("numbers", body))
