#!/usr/bin/env python3
"""Verify outputs/history.json against the committee papers in data/committee/.

Checks:
  - top-level schema; every committee PDF listed in `sources` with its true
    page count, and every item's `source` is one of them
  - every item (any object with a `quote`) has `source`, `pdf_page`
    (1-based PDF page index, not the printed folio) and a copy-exact quote
  - every quote (string, or list of table cells) and every `context_quote`
    appears on its stated page(s) in the plain or -layout text; when it is
    elsewhere, the page it was found on is named
  - `table_row: true` items: the cells sit together in the layout text
    (within ROW_WINDOW lines, or the item's row_window up to MAX_ROW_WINDOW),
    so a row was not stitched from garbled plain text that put a cell next to
    the wrong neighbour. A cell rebuilt from wrapped layout fragments is
    quoted as those fragments, in order; its recorded value must equal them
    joined
  - `layout_rows`: each listed line of cells appears, in order, on one layout
    line, and the lines come in the order given
  - recorded values (titles, opinions, labels...) are copied from the item's
    own quotes, never paraphrased
  - records, never scores: no score/rating/likelihood/impact keys outside
    `scoring_method`
  - scoring matrix: fields agree with the layout lines quoted for each row,
    and rows run top to bottom as on the page
  - every discrepancy cites at least two located quotes; every empty section
    has a gap explaining why; the Strategic Risk Register's absence is a gap
  - ids are unique

Usage: verify_history.py [HISTORY_JSON] [--pdf-dir DIR]
Exit codes: 0 all checks pass, 1 errors found, 2 could not run.
Each error line is `ERROR [code] path: message`.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROW_WINDOW = 3        # default: cells of one table row within 3 layout lines
MAX_ROW_WINDOW = 12   # tall rows (e.g. Table 1 impact bands) may set row_window up to this
TOP_KEYS = {"generated_by", "sources", "audits_completed", "follow_ups",
            "advisory_reviews", "agreed_actions", "planned_audits",
            "risk_themes", "scoring_method", "discrepancies", "gaps"}
LIST_SECTIONS = ["audits_completed", "follow_ups", "advisory_reviews",
                 "agreed_actions", "planned_audits", "risk_themes"]
VERBATIM_FIELDS = {"directorate", "service", "audit_title", "review_title",
                   "opinion", "opinion_report", "opinion_implementation",
                   "label", "band", "rag", "score_range", "probability",
                   "theme", "status_text", "due_date", "incidents",
                   "financial", "definition", "escalation", "response",
                   "appetite_level", "description_text", "period"}
SCORE_KEY = re.compile(r"score|rating|likelihood|impact|rag", re.I)
SCORING_STATUS = {"usable", "not_usable"}
TYPO = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "‐": "-", " ": " ", "­": "",
})


class Report:
    def __init__(self):
        self.errors = []

    def err(self, code, where, msg):
        self.errors.append(f"ERROR [{code}] {where}: {msg}")


# ---------------------------------------------------------------- PDF text

def pdf_pages(pdf, layout):
    cmd = ["pdftotext", "-enc", "UTF-8"] + (["-layout"] if layout else []) + [str(pdf), "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def norm(text):
    return re.sub(r"\s+", " ", text.translate(TYPO)).strip()


def renderings(raw):
    """Normalised renderings of one raw page a quote may match."""
    return [norm(raw), norm(re.sub(r"-[ \t]*\n\s*", "-", raw))]


class Papers:
    def __init__(self, pdf_dir):
        self.dir = pdf_dir
        self.cache = {}

    def files(self):
        return sorted(p.name for p in self.dir.glob("*.pdf"))

    def get(self, name):
        if name not in self.cache:
            pdf = self.dir / name
            plain, layout = pdf_pages(pdf, False), pdf_pages(pdf, True)
            self.cache[name] = {"plain": plain, "layout": layout,
                                "n": len(plain)}
        return self.cache[name]

    def span(self, name, first, last):
        d = self.get(name)
        out = []
        for kind in ("plain", "layout"):
            raw = "\n".join(d[kind][first - 1:last])
            out.extend(renderings(raw))
        return out

    def found_on(self, name, text, first, last):
        q = norm(text)
        return any(q in r for r in self.span(name, first, last))

    def pages_with(self, name, text):
        return [p for p in range(1, self.get(name)["n"] + 1)
                if self.found_on(name, text, p, p)]

    def layout_lines(self, name, first, last):
        d = self.get(name)
        lines = []
        for p in range(first, last + 1):
            lines.extend(l.translate(TYPO) for l in d["layout"][p - 1].splitlines())
        return lines


# ---------------------------------------------------------------- helpers

def cells(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(c, str) for c in value):
        return value
    return None


def walk(obj, path="$"):
    """Yield (path, dict) for every dict in the tree."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def line_hits(lines, cell):
    """Layout line indices holding the start of a cell (its first 3, 2 or 1 words)."""
    words = norm(cell).split()
    flat = [re.sub(r"\s+", " ", l) for l in lines]
    for n in (3, 2, 1):
        head = " ".join(words[:n])
        hits = [i for i, l in enumerate(flat) if head and head in l]
        if hits:
            return hits
    return []


def row_line(lines, row, start=0):
    """First layout line index >= start where the cells appear in order."""
    pat = re.compile(r"(?<!\S)" + r"\s+".join(re.escape(norm(c)) for c in row) + r"(?!\S)")
    for i in range(start, len(lines)):
        if pat.search(lines[i]):
            return i
    return None


# ---------------------------------------------------------------- item checks

def check_item(rep, papers, sources, path, item):
    src, page = item.get("source"), item.get("pdf_page")
    if not isinstance(src, str) or src not in sources:
        rep.err("bad_source", path, f"source {src!r} is not a listed committee paper")
        return
    n = papers.get(src)["n"]
    if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= n:
        rep.err("bad_page", path, f"pdf_page {page!r} outside 1..{n} for {src}")
        return
    last = item.get("pdf_page_end", page)
    if not isinstance(last, int) or not page <= last <= n:
        rep.err("bad_page", path, f"pdf_page_end {last!r} invalid")
        return
    where = f"{src} p{page}" + (f"-{last}" if last != page else "")

    quote = cells(item.get("quote"))
    if not quote or not all(c.strip() for c in quote):
        rep.err("bad_quote", path, "quote must be a non-empty string or list of non-empty strings")
        return
    context = item.get("context_quote", [])
    if cells(context) is None:
        rep.err("bad_quote", path, "context_quote must be a list of strings")
        context = []
    else:
        context = cells(context)

    located = True
    for c in quote + context:
        if not papers.found_on(src, c, page, last):
            located = False
            elsewhere = papers.pages_with(src, c)
            hint = f"; found on p{elsewhere}" if elsewhere else "; not found anywhere in the file"
            rep.err("wrong_page" if elsewhere else "not_found", path,
                    f"{c[:70]!r} not on {where}{hint}")

    text = norm(" ".join(quote + context))
    for k in VERBATIM_FIELDS & item.keys():
        v = item[k]
        if isinstance(v, str) and norm(v) not in text:
            rep.err("value_not_in_quote", f"{path}.{k}",
                    f"{v!r} is not copied from the item's quotes")

    lines = papers.layout_lines(src, page, last)
    if item.get("table_row") and located:
        if len(quote) < 2:
            rep.err("bad_quote", path, "table_row needs a list of at least two cells")
        else:
            win = item.get("row_window", ROW_WINDOW)
            if not isinstance(win, int) or not 0 <= win <= MAX_ROW_WINDOW:
                rep.err("bad_quote", path, f"row_window must be an int 0..{MAX_ROW_WINDOW}")
                win = ROW_WINDOW
            hits = [line_hits(lines, c) for c in quote]
            anchors = sorted({i for h in hits for i in h})
            if not any(all(any(a <= i <= a + win for i in h) for h in hits)
                       for a in anchors):
                rep.err("incoherent_row", path,
                        f"cells {[c[:30] for c in quote]} are not within {win} "
                        f"layout lines of each other on {where}")

    if "layout_rows" in item:
        rows = item["layout_rows"]
        if not isinstance(rows, list) or not all(cells(r) and isinstance(r, list) for r in rows):
            rep.err("bad_layout_rows", path, "layout_rows must be a list of lists of strings")
            return
        start = 0
        for j, row in enumerate(rows):
            i = row_line(lines, row, start)
            if i is None:
                rep.err("layout_row_not_found", f"{path}.layout_rows[{j}]",
                        f"{row} not found in order on one layout line of {where}"
                        + (" after the previous row" if start else ""))
                return
            start = i + 1
        item["_line"] = row_line(lines, rows[0])


# ---------------------------------------------------------------- whole-file checks

def check_sources(rep, papers, data):
    listed = {}
    for i, s in enumerate(data.get("sources") or []):
        f = s.get("file") if isinstance(s, dict) else None
        if not isinstance(f, str) or not (papers.dir / f).is_file():
            rep.err("bad_source", f"$.sources[{i}]", f"file {f!r} not in {papers.dir}")
            continue
        n = papers.get(f)["n"]
        if s.get("pages") != n:
            rep.err("bad_source", f"$.sources[{i}]", f"pages {s.get('pages')!r}, PDF has {n}")
        listed[f] = s
    for f in papers.files():
        if f not in listed:
            rep.err("source_missing", "$.sources", f"{f} is in the committee folder but not listed")
    return set(listed)


def check_scoring(rep, sm):
    if not isinstance(sm, dict):
        rep.err("bad_scoring", "$.scoring_method", "must be an object")
        return
    status = sm.get("status")
    if status not in SCORING_STATUS:
        rep.err("bad_scoring", "$.scoring_method.status", f"{status!r} not in {sorted(SCORING_STATUS)}")
        return
    if status != "usable":
        return
    for key in ("likelihood_scale", "impact_scale"):
        scale = sm.get(key)
        if not isinstance(scale, list) or sorted(e.get("score") for e in scale
                                                   if isinstance(e, dict)) != [1, 2, 3, 4, 5]:
            rep.err("bad_scoring", f"$.scoring_method.{key}", "needs one entry per score 1..5")
    if not isinstance(sm.get("bands"), list) or not sm["bands"]:
        rep.err("bad_scoring", "$.scoring_method.bands", "usable method needs its bands")
    rows = (sm.get("matrix") or {}).get("rows")
    if not isinstance(rows, list) or len(rows) != 5:
        rep.err("bad_scoring", "$.scoring_method.matrix.rows", "needs 5 impact rows")
        return
    prev = -1
    for i, r in enumerate(rows):
        p = f"$.scoring_method.matrix.rows[{i}]"
        lr = r.get("layout_rows")
        if not (isinstance(lr, list) and len(lr) == 2):
            rep.err("bad_matrix", p, "layout_rows must be [band line, score line]")
            continue
        if lr[0] != r.get("bands") or lr[1] != [str(s) for s in r.get("scores", [])]:
            rep.err("bad_matrix", p, "bands/scores differ from the layout lines quoted for this row")
        line = r.get("_line")
        if line is not None:
            if line <= prev:
                rep.err("bad_matrix", p, "row is above the previous row on the page")
            prev = line


def check(data, papers):
    rep = Report()
    missing, extra = TOP_KEYS - data.keys(), data.keys() - TOP_KEYS
    if missing:
        rep.err("schema", "$", f"missing keys {sorted(missing)}")
    if extra:
        rep.err("schema", "$", f"unexpected keys {sorted(extra)}")
    sources = check_sources(rep, papers, data)

    ids = {}
    for path, d in walk(data):
        if "id" in d:
            if d["id"] in ids:
                rep.err("duplicate_id", path, f"id {d['id']!r} also at {ids[d['id']]}")
            ids.setdefault(d["id"], path)
        if "quote" in d:
            check_item(rep, papers, sources, path, d)
        if not path.startswith("$.scoring_method"):
            for k in d:
                if SCORE_KEY.search(k):
                    rep.err("scoring_forbidden", f"{path}.{k}",
                            "history records, never scores: remove this field")

    for key in LIST_SECTIONS:
        if not isinstance(data.get(key), list):
            rep.err("schema", f"$.{key}", "must be a list")
    gaps = data.get("gaps") if isinstance(data.get("gaps"), list) else []
    gap_sections = set()
    for i, g in enumerate(gaps):
        if not (isinstance(g, dict) and all(isinstance(g.get(k), str) and g[k].strip()
                                            for k in ("id", "section", "what", "reason"))):
            rep.err("bad_gap", f"$.gaps[{i}]", "needs non-empty id, section, what, reason")
            continue
        gap_sections.add(g["section"])
    for key in LIST_SECTIONS:
        if data.get(key) == [] and key not in gap_sections:
            rep.err("missing_gap", f"$.{key}", "section is empty but no gap explains why")
    if (data.get("scoring_method") or {}).get("status") == "not_usable" \
            and "scoring_method" not in gap_sections:
        rep.err("missing_gap", "$.scoring_method", "not_usable but no gap explains why")
    if not any("strategic risk register" in (g.get("what", "") + g.get("reason", "")).lower()
               for g in gaps if isinstance(g, dict)):
        rep.err("missing_srr_gap", "$.gaps", "the Strategic Risk Register's absence must be recorded")

    check_scoring(rep, data.get("scoring_method"))

    for i, d in enumerate(data.get("discrepancies") or []):
        p = f"$.discrepancies[{i}]"
        refs = d.get("refs") if isinstance(d, dict) else None
        if not isinstance(d, dict) or not str(d.get("description", "")).strip():
            rep.err("bad_discrepancy", p, "needs a description")
        if not isinstance(refs, list) or len(refs) < 2 or \
                not all(isinstance(r, dict) and "quote" in r for r in refs):
            rep.err("discrepancy_refs", p, "needs at least two refs, each with source, pdf_page and quote")
        if isinstance(d, dict) and any(k in d for k in ("resolution", "resolved", "correct_value")):
            rep.err("discrepancy_resolved", p, "record discrepancies, never resolve them")
    return rep


def main():
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("history", nargs="?", default=root / "outputs" / "history.json", type=Path)
    ap.add_argument("--pdf-dir", default=root / "data" / "committee", type=Path)
    args = ap.parse_args()
    if not shutil.which("pdftotext"):
        print("CANNOT RUN: pdftotext not on PATH")
        return 2
    if not args.pdf_dir.is_dir() or not list(args.pdf_dir.glob("*.pdf")):
        print(f"CANNOT RUN: no PDFs in {args.pdf_dir}")
        return 2
    try:
        data = json.loads(args.history.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"CANNOT RUN: {args.history}: {e}")
        return 2
    if not isinstance(data, dict):
        print("CANNOT RUN: top level must be an object")
        return 2
    rep = check(data, Papers(args.pdf_dir))
    for e in rep.errors:
        print(e)
    print("PASS" if not rep.errors else f"FAIL: {len(rep.errors)} error(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
