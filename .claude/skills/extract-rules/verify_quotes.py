#!/usr/bin/env python3
"""Verify outputs/rules.json against data/contract-rules.pdf.

Checks:
  - schema of every top-level section, rule, exclusion, parameter and note
  - rule IDs run CPR-01, CPR-02, ... with no gaps
  - every *_param a rule uses is declared in `parameters`, and every
    parameter value is null (never filled in from memory)
  - every verbatim_quote appears on its stated page (page..page_end)
  - every numeric threshold appears as a £ amount in its own quote
  - every numbered clause and appendix row in the PDF is covered by a rule
    or an exclusion, and none is both

Usage: verify_quotes.py [RULES_JSON] [--pdf PDF]
Exit codes: 0 all checks pass, 1 errors found, 2 could not run.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RULE_TYPES = {"threshold", "approval", "requirement", "anti-avoidance"}
SCOPES = {"all", "goods", "services", "works", "concessions", "light_touch"}
NOTE_KINDS = {"contradiction", "drafting-gap", "ambiguity"}
NUM = (int, float)

# field -> (allowed types, required)
RULE_FIELDS = {
    "rule_id": ((str,), True),
    "clause": ((str,), True),
    "page": ((int,), True),
    "page_end": ((int,), False),
    "type": ((str,), True),
    "scope": ((list,), True),
    "condition": ((str,), True),
    "threshold_low": (NUM + (type(None),), True),
    "threshold_low_inclusive": ((bool, type(None)), True),
    "threshold_low_param": ((str, type(None)), True),
    "threshold_high": (NUM + (type(None),), True),
    "threshold_high_inclusive": ((bool, type(None)), True),
    "threshold_high_param": ((str, type(None)), True),
    "required_action": ((str, type(None)), True),
    "approver": ((str, type(None)), True),
    "evidence_source": ((str,), True),
    "verbatim_quote": ((str,), True),
}
TOP_KEYS = {"source", "parameters", "rules", "excluded", "notes"}
NOTE_ID = re.compile(r"^App [A-Z] note( \*{1,4})?$")
PARAM_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
TYPO = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "": " ", " ": " ",
})


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


# ---------------------------------------------------------------- PDF text

def pdf_pages(pdf, layout):
    cmd = ["pdftotext", "-enc", "UTF-8"] + (["-layout"] if layout else []) + [str(pdf), "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def norm(text):
    text = text.translate(TYPO)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*\S+\.docx \d+$", "", text)  # page footer


def page_variants(raw_pages):
    """Normalised text per page, in each rendering the quote may match."""
    variants = []
    for raw in raw_pages:
        variants.append(norm(raw))
        variants.append(norm(re.sub(r"-[ \t]*\n\s*", "-", raw)))  # rejoin "Call-\nIn"
    return variants


def build_page_text(plain, layout):
    """page number (1-based) -> list of normalised renderings."""
    return {i + 1: page_variants([plain[i]]) + page_variants([layout[i]])
            for i in range(len(plain))}


def span_texts(page_text, first, last):
    n = len(page_text[first])
    return [" ".join(page_text[p][k] for p in range(first, last + 1)) for k in range(n)]


# ---------------------------------------------------------------- clause catalogue

def clause_catalogue(layout):
    """Ordered list of clause IDs found in the PDF: numbered clauses plus appendix rows."""
    order, seen = [], set()

    def add(cid):
        if cid not in seen:
            seen.add(cid)
            order.append(cid)

    appendix = None
    band_no = 0
    for raw in layout:
        head = re.search(r"Contract Rules - Appendix ([A-Z])", raw)
        if head:
            appendix, band_no = head.group(1), 0
        lines = raw.splitlines()
        if appendix is None:
            for line in lines:
                m = re.match(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,3})\s{2,}\S", line)
                if m:
                    add(m.group(1))
            continue
        labels = [m.group(1) for line in lines
                  if (m := re.match(r"^\s{1,6}([A-Z]\d?)(?=\s{2,}|\s*$)", line))]
        if labels:
            for lab in labels:
                add(f"App {appendix} row {lab}")
        else:  # unlabelled table: one row per value band
            for line in lines:
                if re.match(r"^\s{0,2}(up to\b|Above\b|£\S+ or more)", line):
                    band_no += 1
                    add(f"App {appendix} row {band_no}")
    return order


def is_numbered(cid):
    return re.fullmatch(r"\d{1,2}(\.\d{1,2})+", cid) is not None


def expand(ref, catalogue, rep, where):
    """A clause reference, or a range 'X–Y', -> list of catalogue IDs."""
    parts = re.split(r"\s*[–-]\s*", ref)
    if len(parts) == 1:
        if ref in catalogue or NOTE_ID.match(ref):
            return [ref]
        rep.err(where, f"clause '{ref}' not found in the PDF")
        return []
    if len(parts) != 2:
        rep.err(where, f"bad clause range '{ref}'")
        return []
    start, end = parts
    m = re.match(r"^(App [A-Z] row )", start)
    if m and not end.startswith("App"):
        end = m.group(1) + end
    if start not in catalogue or end not in catalogue:
        rep.err(where, f"range '{ref}' has an end not found in the PDF")
        return []
    i, j = catalogue.index(start), catalogue.index(end)
    if i > j:
        rep.err(where, f"range '{ref}' runs backwards")
        return []
    return catalogue[i:j + 1]


def covered(cid, listed, with_children):
    """listed: every clause named or inside a range; with_children: clauses
    named on their own (rule clauses, single-clause exclusions), which also
    cover their sub-clauses. A range covers only what is printed between its ends."""
    if cid in listed:
        return True
    if not is_numbered(cid):
        return False
    parts = cid.split(".")
    if any(".".join(parts[:k]) in with_children for k in range(1, len(parts))):
        return True  # an ancestor is named on its own
    return any(x.startswith(cid + ".") for x in listed)  # a sub-clause is listed


# ---------------------------------------------------------------- amounts

def amounts_in(text):
    found = set()
    for m in re.finditer(r"£\s?(\d[\d,]*(?:\.\d+)?)\s?(million|m\b|k\b)?", text, re.I):
        value = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        value *= 1_000_000 if unit in ("million", "m") else 1_000 if unit == "k" else 1
        found.add(round(value, 2))
    return found


# ---------------------------------------------------------------- checks

def check_types(obj, fields, where, rep):
    for key, (types, required) in fields.items():
        if key not in obj:
            if required:
                rep.err(where, f"missing field '{key}'")
            continue
        val = obj[key]
        if isinstance(val, bool) and bool not in types:
            rep.err(where, f"'{key}' must not be a boolean")
        elif not isinstance(val, types):
            rep.err(where, f"'{key}' has type {type(val).__name__}")
        elif isinstance(val, str) and not val.strip():
            rep.err(where, f"'{key}' is an empty string")
    for key in obj:
        if key not in fields:
            rep.err(where, f"unknown field '{key}'")


def check_threshold_side(rule, side, where, rep, used_params):
    value = rule.get(f"threshold_{side}")
    inc = rule.get(f"threshold_{side}_inclusive")
    param = rule.get(f"threshold_{side}_param")
    if value is not None and param is not None:
        rep.err(where, f"threshold_{side} and threshold_{side}_param are both set")
    present = value is not None or param is not None
    if present and not isinstance(inc, bool):
        rep.err(where, f"threshold_{side}_inclusive must be true/false when a {side} threshold is set")
    if not present and inc is not None:
        rep.err(where, f"threshold_{side}_inclusive must be null when there is no {side} threshold")
    if isinstance(value, NUM) and not isinstance(value, bool):
        if value <= 0:
            rep.err(where, f"threshold_{side} must be positive")
        if isinstance(value, float):
            if value.is_integer():
                rep.err(where, f"threshold_{side} {value} must be written as an integer")
            elif round(value, 2) != value:
                rep.err(where, f"threshold_{side} {value} has more than two decimals")
    if isinstance(param, str):
        used_params.add(param)
    return present


def check_rule(i, rule, rep, page_text, used_params):
    rid = rule.get("rule_id") if isinstance(rule, dict) else None
    where = f"rules[{i}]" + (f" {rid}" if rid else "")
    if not isinstance(rule, dict):
        rep.err(where, "is not an object")
        return
    check_types(rule, RULE_FIELDS, where, rep)
    if "clause" in rule:
        where += f" (clause {rule['clause']})"

    expected = f"CPR-{i + 1:02d}"
    if rid != expected:
        rep.err(where, f"rule_id should be {expected} (IDs run in order with no gaps)")
    if rule.get("type") not in RULE_TYPES:
        rep.err(where, f"type '{rule.get('type')}' not one of {sorted(RULE_TYPES)}")

    scope = rule.get("scope")
    if isinstance(scope, list):
        if not scope or any(s not in SCOPES for s in scope) or len(set(scope)) != len(scope):
            rep.err(where, f"scope {scope} must be a non-empty, duplicate-free subset of {sorted(SCOPES)}")
        elif "all" in scope and len(scope) > 1:
            rep.err(where, "scope 'all' must stand alone")

    low = check_threshold_side(rule, "low", where, rep, used_params)
    high = check_threshold_side(rule, "high", where, rep, used_params)
    lo, hi = rule.get("threshold_low"), rule.get("threshold_high")
    if isinstance(lo, NUM) and isinstance(hi, NUM) and not isinstance(lo, bool) \
            and not isinstance(hi, bool) and lo >= hi:
        rep.err(where, f"threshold_low {lo} is not below threshold_high {hi}")

    if not (low or high or rule.get("required_action") or rule.get("approver")):
        rep.err(where, "not testable: no threshold, required_action or approver")
    if rule.get("type") == "threshold" and not (low or high):
        rep.err(where, "type 'threshold' but no threshold set")
    if rule.get("type") == "approval" and not rule.get("approver"):
        rep.err(where, "type 'approval' but approver is null")

    quote = rule.get("verbatim_quote")
    if not isinstance(quote, str) or not quote.strip():
        return
    if "..." in quote or "…" in quote:
        rep.err(where, "verbatim_quote contains an ellipsis; quote a contiguous passage instead")

    # thresholds must be printed in the quote itself
    printed = amounts_in(quote)
    for side in ("low", "high"):
        v = rule.get(f"threshold_{side}")
        if isinstance(v, NUM) and not isinstance(v, bool) and round(float(v), 2) not in printed:
            rep.err(where, f"threshold_{side} {v} does not appear as a £ amount in the quote")
    if (rule.get("threshold_low_param") or rule.get("threshold_high_param")) \
            and "threshold" not in quote.lower():
        rep.err(where, "uses a threshold parameter but the quote never mentions a Threshold")

    first, last = rule.get("page"), rule.get("page_end", rule.get("page"))
    if not isinstance(first, int) or isinstance(first, bool) or \
            not isinstance(last, int) or isinstance(last, bool):
        return
    n = len(page_text)
    if not 1 <= first <= n or not 1 <= last <= n or last < first:
        rep.err(where, f"page range {first}..{last} invalid (PDF has {n} pages)")
        return
    if last > first + 1:
        rep.err(where, "a quote may span at most two pages (page_end = page + 1)")
    q = norm(quote)
    if any(q in t for t in span_texts(page_text, first, last)):
        return
    elsewhere = [p for p in range(1, n + 1) if any(q in t for t in page_text[p])]
    elsewhere += [f"{p}-{p + 1}" for p in range(1, n)
                  if any(q in t for t in span_texts(page_text, p, p + 1)) and
                  not any(q in t for t in page_text[p] + page_text[p + 1])]
    stated = f"page {first}" if first == last else f"pages {first}-{last}"
    if elsewhere:
        rep.err(where, f"quote not on {stated}; found on page {', '.join(map(str, elsewhere))}")
    else:
        rep.err(where, f"quote not found anywhere in the PDF (stated {stated}): \"{q[:80]}\"")


def check_parameters(params, used, rep):
    if not isinstance(params, dict):
        rep.err("parameters", "must be an object")
        return
    for name, spec in params.items():
        where = f"parameters.{name}"
        if not PARAM_NAME.match(name):
            rep.err(where, "name must be UPPER_SNAKE_CASE")
        if not isinstance(spec, dict):
            rep.err(where, "must be an object")
            continue
        check_types(spec, {"value": ((type(None), str, int, float), True),
                           "defined_in": ((str,), True),
                           "description": ((str,), True)}, where, rep)
        if spec.get("value") is not None:
            rep.err(where, "value must be null: the PDF does not state it, so it is never filled in")
    for name in sorted(used - set(params)):
        rep.err("parameters", f"'{name}' is used by a rule but not declared")
    for name in sorted(set(params) - used):
        rep.warn("parameters", f"'{name}' is declared but no rule uses it")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rules", nargs="?", default="outputs/rules.json")
    ap.add_argument("--pdf", default="data/contract-rules.pdf")
    args = ap.parse_args()

    pdf, rules_path = Path(args.pdf), Path(args.rules)
    for p in (pdf, rules_path):
        if not p.is_file():
            print(f"CANNOT RUN: {p} not found")
            return 2
    if not shutil.which("pdftotext"):
        print("CANNOT RUN: pdftotext (poppler) is not on PATH")
        return 2
    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"CANNOT RUN: {rules_path} is not valid JSON: {e}")
        return 2

    plain, layout = pdf_pages(pdf, False), pdf_pages(pdf, True)
    if len(plain) != len(layout):
        print("CANNOT RUN: plain and layout extraction disagree on page count")
        return 2
    page_text = build_page_text(plain, layout)
    catalogue = clause_catalogue(layout)
    rep = Report()

    if not isinstance(data, dict):
        print("FAIL: top level must be an object with keys " + ", ".join(sorted(TOP_KEYS)))
        return 1
    for k in sorted(TOP_KEYS - set(data)):
        rep.err("top level", f"missing '{k}'")
    for k in sorted(set(data) - TOP_KEYS):
        rep.err("top level", f"unknown key '{k}'")

    src = data.get("source")
    if isinstance(src, dict):
        check_types(src, {"file": ((str,), True), "sha256": ((str,), True),
                          "pages": ((int,), True)}, "source", rep)
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if src.get("sha256") != digest:
            rep.err("source", f"sha256 does not match {pdf} (expected {digest})")
        if src.get("pages") != len(plain):
            rep.err("source", f"pages is {src.get('pages')}, PDF has {len(plain)}")
    elif "source" in data:
        rep.err("source", "must be an object")

    used_params = set()
    rules = data.get("rules", [])
    if not isinstance(rules, list) or not rules:
        rep.err("rules", "must be a non-empty array")
        rules = []
    for i, rule in enumerate(rules):
        check_rule(i, rule, rep, page_text, used_params)
    check_parameters(data.get("parameters", {}), used_params, rep)

    rule_clauses, last_pos = set(), -1
    for i, rule in enumerate(rules):
        if isinstance(rule, dict) and isinstance(rule.get("clause"), str):
            got = expand(rule["clause"], catalogue, rep, f"rules[{i}]")
            if len(got) > 1:
                rep.err(f"rules[{i}]", "a rule cites one clause, not a range")
            rule_clauses.update(got)
            if len(got) == 1 and got[0] in catalogue:
                pos = catalogue.index(got[0])
                if pos < last_pos:
                    rep.err(f"rules[{i}]", f"clause {got[0]} is out of printed order")
                last_pos = max(last_pos, pos)

    excluded_clauses, with_children = set(), set(rule_clauses)
    excluded = data.get("excluded", [])
    if not isinstance(excluded, list):
        rep.err("excluded", "must be an array")
        excluded = []
    for i, ex in enumerate(excluded):
        where = f"excluded[{i}]"
        if not isinstance(ex, dict):
            rep.err(where, "is not an object")
            continue
        check_types(ex, {"clause": ((str,), True), "reason": ((str,), True)}, where, rep)
        reason = ex.get("reason")
        if isinstance(reason, str) and ("\n" in reason or len(reason) > 200):
            rep.err(where, "reason must be one line of at most 200 characters")
        if isinstance(ex.get("clause"), str):
            got = expand(ex["clause"], catalogue, rep, where)
            excluded_clauses.update(got)
            if got == [ex["clause"]]:
                with_children.update(got)

    for cid in sorted(rule_clauses & excluded_clauses):
        rep.err("coverage", f"clause {cid} is both a rule and excluded")
    listed = rule_clauses | excluded_clauses
    missing = [c for c in catalogue if not covered(c, listed, with_children)]
    if missing:
        rep.err("coverage", f"{len(missing)} clause(s) neither a rule nor excluded: {', '.join(missing)}")

    notes = data.get("notes", [])
    if not isinstance(notes, list):
        rep.err("notes", "must be an array")
        notes = []
    for i, note in enumerate(notes):
        where = f"notes[{i}]"
        if not isinstance(note, dict):
            rep.err(where, "is not an object")
            continue
        check_types(note, {"clauses": ((list,), True), "kind": ((str,), True),
                           "note": ((str,), True)}, where, rep)
        if note.get("kind") not in NOTE_KINDS:
            rep.err(where, f"kind '{note.get('kind')}' not one of {sorted(NOTE_KINDS)}")
        clauses = note.get("clauses")
        if isinstance(clauses, list):
            if not clauses:
                rep.err(where, "clauses must not be empty")
            for c in clauses:
                if isinstance(c, str):
                    expand(c, catalogue, rep, where)
                else:
                    rep.err(where, "clauses must be strings")

    print(f"rules: {len(rules)} | excluded entries: {len(excluded)} | "
          f"parameters: {len(data.get('parameters') or {})} | notes: {len(notes)}")
    print(f"clauses found in PDF: {len(catalogue)} | covered: {len(catalogue) - len(missing)}")
    for w in rep.warnings:
        print(f"WARNING {w}")
    for e in rep.errors:
        print(f"ERROR {e}")
    print("PASS" if not rep.errors else f"FAIL ({len(rep.errors)} error(s))")
    return 0 if not rep.errors else 1


if __name__ == "__main__":
    sys.exit(main())
