#!/usr/bin/env python3
"""Build the risk register from the risk-assessor's judgments.

Reads outputs/risk-ratings.json (written by the risk-assessor, see SKILL.md)
and resolves it against outputs/analytics.json, outputs/history.json and
outputs/rules.json:

- every [rule:ID], [metric:$.path] and [history:ID] citation must resolve;
- every {{$.path}} placeholder is filled from analytics.json (the agent never
  types a figure);
- score = likelihood x impact; the matrix label (Figure 1) and band (Table 4)
  come from the council's matrix in history.json, or the fallback scale when
  history.json has no usable method;
- a risk whose likelihood or impact justification has no resolvable citation
  is dropped and listed as excluded;
- the likelihood rubric, the financial-impact bands and the repeat-finding
  uplift are checked mechanically;
- figures typed into prose and accusatory wording are warned about.

Writes outputs/risk-register.md (ending with "Auditor decisions") and
outputs/auditor-comments.md (the auditor's decision template; decisions
already in it are kept). When risk-ratings.json carries a "revision" block,
the build is a post-gate revision: it checks every auditor decision was
applied and nothing else changed, and writes a revision header.

Usage:
  build_register.py [--ratings F] [--analytics F] [--history F] [--rules F]
                    [--out-dir D]
Exit 0: built (dropped risks and warnings are printed). 1: errors, nothing
written. 2: missing or malformed input.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

HISTORY_LISTS = ("audits_completed", "follow_ups", "advisory_reviews", "agreed_actions",
                 "planned_audits", "risk_themes", "discrepancies", "gaps")
OPINION_FIELDS = ("opinion", "opinion_report", "opinion_implementation")
ADVERSE_OPINION = ("limited", "no assurance", "weak", "unsatisfactory", "minimal")
FALLBACK_LABELS = {1: "Very low", 2: "Low", 3: "Medium", 4: "High", 5: "Very high"}
DECISIONS = ("approve", "amend", "reject")
STATUSES = ("proposed", "rejected")
ACCUSATORY = re.compile(r"\b(fraud\w*|corrupt\w*|wrongdoing|theft|steal\w*|misconduct|"
                        r"deliberate(?:ly)?|dishonest\w*|illegal\w*|unlawful\w*|"
                        r"breach(?:ed|es)?|abuse[ds]?)\b", re.I)

# Conflicting thresholds in the council's scoring method. Each names the
# history.json discrepancy it handles: what the builder uses, and what it marks
# but does not use. Any scoring-method discrepancy not listed here stops the
# build; it is never resolved silently.
SCORING_CHOICES = [
    {"ref": "DIS-01", "match": ("4.3", "Medium"), "topic": "Impact score of 'Medium'",
     "used": "Table 1 (p14): Medium = 3",
     "marked": "paragraph 4.3 (p14) prints 'Medium (2)'; not used"},
    {"ref": "DIS-02", "match": ("overlap",), "topic": "Financial impact bands",
     "used": "Table 1 £ ranges, which do not overlap; a figure on a shared boundary "
             "(e.g. £500k) goes in the higher band",
     "marked": "Table 1 percentage ranges (Major 0.25%-1% overlaps Medium 0.1%-0.3%); not used"},
    {"ref": "DIS-03", "match": ("Figure 1", "Table 4"), "topic": "Band names",
     "used": "Table 4 band and RAG colour as the band; the Figure 1 label is shown "
             "beside it as the matrix label",
     "marked": "Figure 1 calls the 8-12 band 'High' (Table 4: 'Medium - High')"},
    {"ref": "DIS-04", "match": ("Corporate Risk Register",), "topic": "Corporate Risk Register escalation",
     "used": "Table 4: Extreme (15-25) is added to the Corporate Risk Register",
     "marked": "Figure 4 ('Score 9 or above') and paragraph 6.3; risks scoring 9-14 are marked † "
               "because Figure 4 would also include them"},
]
SCORING_SECTIONS = ("4.2", "4.3", "4.4", "5.11", "6.3", "Table 1", "Table 2", "Table 4",
                    "Figure 1", "Figure 4")
FIG1_TO_TABLE4 = {"High": "Medium - High"}
# Tests that describe the population other tests run on, not an indicator:
# citing them never raises the likelihood rubric level.
POPULATION_TESTS = {"high_value_suppliers"}

PATH_TOKEN = re.compile(r"\.([A-Za-z0-9_\-]+)|\[(\d+)\]|\['([^']*)'\]")
PATH_RE = r"\$(?:\.[A-Za-z0-9_\-]+|\[\d+\]|\['[^']*'\])*"
CITE_RE = re.compile(r"\[(rule|history):([A-Za-z0-9_\-]+)\]|\[(metric):(" + PATH_RE + r")\]")
CITE_LOOSE = re.compile(r"\[\s*(rule|metric|history)\s*:", re.I)
PH_RE = re.compile(r"\{\{\s*(" + PATH_RE + r")\s*(?:\|\s*([a-z]+)\s*)?\}\}")
FORMATS = ("gbp", "int", "pct", "num", "raw")
TYPED_NUM = re.compile(r"£\s?\d[\d,.]*\s?[kKmM]?|\d[\d,]*(?:\.\d+)?\s?%|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|"
                       r"\b\d+\.\d+\b|\b\d{2,}\b")
NUM_EXEMPT_BEFORE = re.compile(r"(?:clauses?|cl\.|sections?|paragraphs?|paras?|§|tables?|figures?|fig\.|"
                               r"appendix|app|rows?|pages?|p\.|part|step|cpr-|r-|aud-|fu-|adv-|dis-|gap-|"
                               r"t-|\d{4}/)\s*$", re.I)


class InputError(Exception):
    pass


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_json(p, what):
    p = Path(p)
    if not p.exists():
        raise InputError(f"{what} not found: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputError(f"{what} is not valid JSON ({p}): {e}")


def resolve(doc, path):
    """Resolve a $.a.b[0]['c d'] path; KeyError with a reason if it does not exist."""
    if not path.startswith("$"):
        raise KeyError("path must start with $")
    cur, pos = doc, 1
    while pos < len(path):
        m = PATH_TOKEN.match(path, pos)
        if not m:
            raise KeyError(f"bad path syntax at '{path[pos:]}'")
        key, idx, qkey = m.groups()
        if idx is not None:
            if not isinstance(cur, list) or int(idx) >= len(cur):
                raise KeyError(f"no index [{idx}] at '{path[:m.start()]}'")
            cur = cur[int(idx)]
        else:
            k = key if key is not None else qkey
            if not isinstance(cur, dict) or k not in cur:
                raise KeyError(f"no key '{k}' at '{path[:m.start()] or '$'}'")
            cur = cur[k]
        pos = m.end()
    return cur


def last_key(path):
    toks = [m.group(1) or m.group(3) for m in PATH_TOKEN.finditer(path) if m.group(2) is None]
    return toks[-1] if toks else ""


def fmt_value(value, path, style):
    if isinstance(value, bool) or value is None or isinstance(value, (list, dict)):
        raise ValueError(f"{path} is a {type(value).__name__}, not a figure")
    if isinstance(value, str):
        if style not in (None, "raw"):
            raise ValueError(f"{path} is text; format '{style}' does not apply")
        return value
    key = last_key(path).lower()
    if style is None:
        if any(s in key for s in ("gbp", "amount", "awarded_value", "award_per_year", "boundary", "threshold")):
            style = "gbp"
        elif "share" in key:
            style = "pct"
        elif isinstance(value, int):
            style = "int"
        else:
            style = "num"
    if style == "gbp":
        return f"£{value:,.2f}"
    if style == "int":
        if value != int(value):
            raise ValueError(f"{path} = {value} is not a whole number")
        return f"{int(value):,}"
    if style == "pct":
        return f"{value * 100:.1f}%"
    if style == "num":
        return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"
    return str(value)


def nonzero(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v > 0
    return bool(v)


class Context:
    def __init__(self, analytics, history, rules):
        self.analytics, self.history = analytics, history
        self.rules = {r["rule_id"]: r for r in rules.get("rules", [])}
        self.hist = {}
        for lst in HISTORY_LISTS:
            for item in history.get(lst, []) or []:
                if "id" in item:
                    self.hist[item["id"]] = (lst, item)


def citations(text, ctx):
    """Return (resolved, unresolved) citations in text. resolved items: (kind, ref, payload)."""
    good, bad, starts = [], [], set()
    for m in CITE_RE.finditer(text):
        starts.add(m.start())
        kind, ref = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if kind == "rule":
            (good if ref in ctx.rules else bad).append(
                (kind, ref, ctx.rules.get(ref)) if ref in ctx.rules else f"[rule:{ref}] not in rules.json")
        elif kind == "history":
            (good if ref in ctx.hist else bad).append(
                (kind, ref, ctx.hist.get(ref)) if ref in ctx.hist else f"[history:{ref}] not in history.json")
        else:
            try:
                good.append((kind, ref, resolve(ctx.analytics, ref)))
            except KeyError as e:
                bad.append(f"[metric:{ref}] does not resolve in analytics.json ({e.args[0]})")
    for m in CITE_LOOSE.finditer(text):
        if m.start() not in starts:
            bad.append(f"malformed citation '{text[m.start():m.start() + 60]}'")
    return good, bad


def fill(text, ctx, errors, where):
    """Replace {{$.path}} placeholders with analytics values."""
    def sub(m):
        path, style = m.group(1), m.group(2)
        if style and style not in FORMATS:
            errors.append(f"{where}: unknown format '|{style}' in {m.group(0)} (use {', '.join(FORMATS)})")
            return m.group(0)
        try:
            return fmt_value(resolve(ctx.analytics, path), path, style)
        except (KeyError, ValueError) as e:
            errors.append(f"{where}: placeholder {m.group(0)} cannot be filled ({e.args[0]})")
            return m.group(0)
    out = PH_RE.sub(sub, text)
    for m in re.finditer(r"\{\{", PH_RE.sub("", text)):
        errors.append(f"{where}: malformed placeholder near '{PH_RE.sub('', text)[m.start():m.start() + 50]}'")
    return out


def typed_numbers(text):
    """Figures typed in prose (placeholders and citations removed)."""
    t = CITE_LOOSE.sub("[", CITE_RE.sub(" ", PH_RE.sub(" ", text)))
    hits = []
    for m in TYPED_NUM.finditer(t):
        s = m.group(0)
        before = t[max(0, m.start() - 12):m.start()]
        if NUM_EXEMPT_BEFORE.search(before):
            continue
        if re.fullmatch(r"(19|20)\d\d", s):
            continue
        hits.append(s.strip())
    return hits


def render_cites(text, ctx):
    def sub(m):
        if m.group(1) == "rule":
            r = ctx.rules.get(m.group(2))
            return f"[{m.group(2)}, cl. {r['clause']}]" if r else m.group(0)
        if m.group(1) == "history":
            return f"[{m.group(2)}]"
        return f"[`{m.group(4)}`]"
    return CITE_RE.sub(sub, text)


def opinions(item):
    return [item[f] for f in OPINION_FIELDS if isinstance(item.get(f), str)]


def is_adverse(item):
    return any(any(a in o.lower() for a in ADVERSE_OPINION) for o in opinions(item))


# ---------------------------------------------------------------- scoring

class Scoring:
    """The council's method from history.json, or the fallback scale."""

    def __init__(self, history, errors):
        sm = history.get("scoring_method") or {}
        self.usable = sm.get("status") == "usable"
        self.choices, self.notes = [], []
        if not self.usable:
            self.reason = sm.get("status", "no scoring_method in history.json")
            return
        try:
            self.lik = {e["score"]: e for e in sm["likelihood_scale"]}
            self.imp = {e["score"]: e for e in sm["impact_scale"]}
            self.columns = sm["impact_columns"]["columns"]
            self.rows = {r["impact"]: r for r in sm["matrix"]["rows"]}
            self.bands = [dict(b, range=self._range(b["score_range"])) for b in sm["bands"]]
        except (KeyError, TypeError, ValueError) as e:
            raise InputError(f"history.json scoring_method is status 'usable' but incomplete: {e}")
        if set(self.lik) != set(range(1, 6)) or set(self.imp) != set(range(1, 6)) or set(self.rows) != set(range(1, 6)):
            raise InputError("history.json scoring_method: likelihood, impact or matrix is not a 1-5 scale")
        self._check_conflicts(history, errors)
        self.fin = self._financial_bands(errors)
        fig4 = [e for e in sm.get("escalation", []) if "Figure 4" in e.get("section", "")]
        self.fig4_min = None
        for e in fig4:
            for s in e.get("includes", []):
                m = re.search(r"Score (\d+) or above", s)
                if m:
                    self.fig4_min = int(m.group(1))

    @staticmethod
    def _range(s):
        s = s.strip()
        m = re.fullmatch(r"Up to (\d+)", s, re.I)
        if m:
            return (None, int(m.group(1)))
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", s)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        raise ValueError(f"unreadable Table 4 score range '{s}'")

    def band(self, score):
        hits = [b for b in self.bands if (b["range"][0] or 0) <= score <= b["range"][1]]
        return hits[0] if len(hits) == 1 else None

    def _check_conflicts(self, history, errors):
        dis = {d["id"]: d for d in history.get("discrepancies", [])}
        declared = set()
        for c in SCORING_CHOICES:
            d = dis.get(c["ref"])
            if not d or not all(k in d.get("description", "") for k in c["match"]):
                errors.append(f"scoring choice for '{c['topic']}' expects {c['ref']} in history.json to mention "
                              f"{c['match']}; it does not. Re-map SCORING_CHOICES to the current discrepancy IDs.")
                continue
            declared.add(c["ref"])
            self.choices.append(c)
        for d in dis.values():
            secs = [r.get("section", "") for r in d.get("refs", [])
                    if "risk-management-strategy" in r.get("source", "")]
            if any(s.startswith(SCORING_SECTIONS) for s in secs) and d["id"] not in declared:
                errors.append(f"{d['id']} is a conflict in the scoring method with no declared choice: "
                              f"{d['description'][:160]} Add it to SCORING_CHOICES (use one, mark the other).")
        # Figure 1 and Table 4 must agree cell by cell (after the DIS-03 name mapping),
        # and every possible score must fall in exactly one Table 4 band.
        for i, row in self.rows.items():
            for l in range(1, 6):
                score = l * i
                if row["scores"][l - 1] != score:
                    errors.append(f"Figure 1 row {i} column {l} prints score {row['scores'][l - 1]}, not {score}")
                b = self.band(score)
                if b is None:
                    errors.append(f"score {score} falls in no Table 4 band, or in more than one")
                    continue
                fig = row["bands"][l - 1]
                if FIG1_TO_TABLE4.get(fig, fig) != b["band"]:
                    errors.append(f"conflict not declared: Figure 1 labels {l}x{i}={score} '{fig}', "
                                  f"Table 4 puts {score} in '{b['band']}'")

    def _financial_bands(self, errors):
        out = []
        amt = re.compile(r"(\d+(?:\.\d+)?)\s*([kKmM])")
        for s in range(1, 6):
            text = self.imp[s].get("financial", "")
            tail = text.split("budget", 1)[-1]
            vals = [float(a) * (1_000 if u.lower() == "k" else 1_000_000) for a, u in amt.findall(tail)]
            if len(vals) == 2:
                lo, hi = vals
            elif len(vals) == 1 and ">" in text:
                lo, hi = vals[0], None
            elif len(vals) == 1 and "less than" in text.lower():
                lo, hi = None, vals[0]
            else:
                errors.append(f"Table 1 financial cell for impact {s} has no readable £ range: '{text}'")
                return None
            out.append((s, lo, hi))
        for (s1, _, hi), (s2, lo, _) in zip(out, out[1:]):
            if hi != lo:
                errors.append(f"Table 1 £ ranges are not contiguous between impact {s1} and {s2}")
                return None
        return out

    def financial_score(self, value):
        for s, lo, hi in self.fin:
            if (lo is None or value >= lo) and (hi is None or value < hi):
                return s
        return None

    def lik_label(self, n):
        return self.lik[n]["label"] if self.usable else FALLBACK_LABELS[n]

    def imp_label(self, n):
        return self.imp[n]["label"] if self.usable else FALLBACK_LABELS[n]


def rubric_level(metrics):
    """Highest likelihood level whose floor the cited metrics meet (see SKILL.md)."""
    tests, gp = set(), False
    for path, val in metrics:
        if path.startswith("$.tests.") and nonzero(val):
            test = path.split(".")[2].split("[")[0]
            if test in POPULATION_TESTS:
                continue
            tests.add(test)
            if "general_procurement" in path or "non_placement" in path:
                gp = True
    if not tests:
        return 1, "no non-zero test metric cited"
    if not gp:
        return 2, f"non-zero metric from {len(tests)} test(s), none in general procurement"
    if len(tests) < 2:
        return 3, "non-zero general-procurement metric from one test"
    return 4, f"non-zero metrics from {len(tests)} tests, including general procurement"


# ---------------------------------------------------------------- risks

def check_shape(r, i):
    errs = []
    where = f"risks[{i}]"
    if not isinstance(r, dict):
        return [f"{where} is not an object"]
    if not isinstance(r.get("risk_id"), str) or not re.fullmatch(r"R-\d{2,}", r["risk_id"]):
        errs.append(f"{where}.risk_id must look like R-01")
    for k in ("title", "proposed_focus"):
        if not isinstance(r.get(k), str) or not r[k].strip():
            errs.append(f"{where}.{k} must be non-empty text")
    if r.get("status", "proposed") not in STATUSES:
        errs.append(f"{where}.status must be one of {STATUSES}")
    for part in ("likelihood", "impact"):
        p = r.get(part)
        if not isinstance(p, dict):
            errs.append(f"{where}.{part} must be an object")
            continue
        if p.get("score") not in (1, 2, 3, 4, 5):
            errs.append(f"{where}.{part}.score must be an integer 1-5")
        if not isinstance(p.get("justification"), str):
            errs.append(f"{where}.{part}.justification must be text")
    if isinstance(r.get("impact"), dict) and not isinstance(r["impact"].get("column"), str):
        errs.append(f"{where}.impact.column must name a Table 1 column")
    ev = r.get("evidence")
    if not isinstance(ev, list) or not ev or not all(isinstance(e, str) for e in ev):
        errs.append(f"{where}.evidence must be a non-empty list of text")
    return errs


def assess(r, ctx, sc):
    """Resolve one risk. Returns (built, drop_reason, errors, warnings)."""
    rid = r["risk_id"]
    errors, warnings = [], []
    lik, imp = r["likelihood"], r["impact"]
    lgood, lbad = citations(lik["justification"], ctx)
    igood, ibad = citations(imp["justification"], ctx)
    drop = []
    if not lgood:
        drop.append("likelihood justification has no resolvable citation"
                    + (f" ({'; '.join(lbad)})" if lbad else ""))
    if not igood:
        drop.append("impact justification has no resolvable citation"
                    + (f" ({'; '.join(ibad)})" if ibad else ""))
    if drop:
        return None, "; ".join(drop), [], []

    texts = {"title": r["title"], "likelihood.justification": lik["justification"],
             "impact.justification": imp["justification"], "proposed_focus": r["proposed_focus"]}
    for j, e in enumerate(r["evidence"]):
        texts[f"evidence[{j}]"] = e
    if lik.get("uplift"):
        texts["likelihood.uplift.justification"] = lik["uplift"].get("justification", "")
    if lik.get("below_rubric_reason"):
        texts["likelihood.below_rubric_reason"] = lik["below_rubric_reason"]

    cited = {}
    for field, text in texts.items():
        good, bad = citations(text, ctx)
        for b in bad:
            errors.append(f"{rid} {field}: {b}")
        for g in good:
            cited[(g[0], g[1])] = g[2]
        if field.startswith("evidence") and not good:
            errors.append(f"{rid} {field}: evidence line has no resolvable citation")
        for n in typed_numbers(text):
            warnings.append(f"{rid} {field}: figure typed in prose '{n}'; use a {{{{$.path}}}} placeholder")
        for m in ACCUSATORY.finditer(PH_RE.sub(" ", text)):
            warnings.append(f"{rid} {field}: '{m.group(0)}' reads as an accusation; describe a risk indicator")
        for m in PH_RE.finditer(text):
            if "annualised" in m.group(1) and "annualised estimate" not in text:
                warnings.append(f"{rid} {field}: {m.group(0)} is annualised; label it 'annualised estimate'")
    filled = {f: fill(t, ctx, errors, f"{rid} {f}") for f, t in texts.items()}

    # likelihood: rubric floor, then uplift
    base = lik["score"]
    lmetrics = [(g[1], g[2]) for g in lgood if g[0] == "metric"]
    level, why = rubric_level(lmetrics)
    if base == 5:
        errors.append(f"{rid} likelihood: base score 5 is reached only by a repeat-finding uplift on a 4")
    elif base > level:
        errors.append(f"{rid} likelihood: {base} exceeds the rubric level {level} for the evidence cited ({why})")
    elif base < level:
        reason = lik.get("below_rubric_reason") or ""
        if not citations(reason, ctx)[0]:
            errors.append(f"{rid} likelihood: {base} is below the rubric level {level} ({why}); "
                          f"give likelihood.below_rubric_reason with a citation")
    final_l, uplift = base, None
    if lik.get("uplift"):
        ugood, _ = citations(lik["uplift"].get("justification", ""), ctx)
        hits = [g for g in ugood if g[0] == "history" and g[2][0] in
                ("audits_completed", "follow_ups") and is_adverse(g[2][1])]
        if not hits:
            cited_h = [f"{g[1]} ({', '.join(opinions(g[2][1])) or 'no opinion'})" for g in ugood if g[0] == "history"]
            errors.append(f"{rid} likelihood uplift must cite an audit or follow-up with an adverse opinion "
                          f"({', '.join(ADVERSE_OPINION)}); cited: {', '.join(cited_h) or 'no history item'}")
        elif base >= 5:
            errors.append(f"{rid} likelihood uplift: base is already 5")
        else:
            final_l = base + 1
            uplift = hits
    # impact
    col = imp["column"]
    if sc.usable:
        if col not in sc.columns:
            errors.append(f"{rid} impact.column '{col}' is not a Table 1 column ({', '.join(sc.columns)})")
        elif col == "financial":
            p = imp.get("financial_figure")
            try:
                v = resolve(ctx.analytics, p) if isinstance(p, str) else None
            except KeyError as e:
                v = None
                errors.append(f"{rid} impact.financial_figure {p} does not resolve ({e.args[0]})")
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                errors.append(f"{rid} impact on the financial column needs impact.financial_figure: a $.path to a £ figure")
            elif sc.fin and sc.financial_score(v) != imp["score"]:
                errors.append(f"{rid} impact: financial figure {fmt_value(v, p, 'gbp')} falls in Table 1 band "
                              f"{sc.financial_score(v)}, not {imp['score']}")
    score = final_l * imp["score"]
    built = {"id": rid, "raw": r, "filled": filled, "final_l": final_l, "base_l": base, "impact": imp["score"],
             "column": col, "score": score, "uplift": uplift, "rubric": (level, why), "cited": cited,
             "status": r.get("status", "proposed")}
    if sc.usable:
        built["matrix_label"] = sc.rows[imp["score"]]["bands"][final_l - 1]
        built["band"] = sc.band(score)
    return built, None, errors, warnings


# ---------------------------------------------------------------- auditor comments

def split_row(line):
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.strip().replace("\\|", "|") for c in cells[1:-1]]


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def read_comments(path):
    """Return (decisions {rid: {decision, comment, title}}, general_comments_text, problems)."""
    decisions, general, problems = {}, "", []
    if not path.exists():
        return decisions, general, problems
    text = path.read_text(encoding="utf-8")
    header = None
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            header = None
            continue
        cells = split_row(line)
        low = [c.lower() for c in cells]
        if "decision" in low and "risk id" in low:
            header = low
            continue
        if header is None or set("".join(cells)) <= set("-: "):
            continue
        row = dict(zip(header, cells))
        rid = row.get("risk id", "")
        if not re.fullmatch(r"R-\d{2,}", rid):
            continue
        dec = row.get("decision", "").strip().lower()
        if dec and dec not in DECISIONS:
            problems.append(f"auditor-comments.md {rid}: decision '{dec}' is not one of {', '.join(DECISIONS)}")
        decisions[rid] = {"decision": dec, "comment": row.get("comment", "").strip(), "title": row.get("risk", "")}
    m = re.search(r"^## General comments\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if m:
        general = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip()
    return decisions, general, problems


def read_signoff(path):
    """Reviewer and Date lines the auditor filled in; kept when the file is rewritten."""
    out = {"reviewer": "", "date": ""}
    if path.exists():
        for k in out:
            m = re.search(rf"^{k.capitalize()}:[ \t]*(.*)$", path.read_text(encoding="utf-8"), re.M)
            out[k] = m.group(1).strip() if m else ""
    return out


def write_comments(path, built, decisions, general, revision, sc):
    signoff = read_signoff(path)
    lines = ["# Auditor decisions on the risk register", "",
             f"Register: `outputs/risk-register.md`, revision {revision}.", "",
             f"Reviewer: {signoff['reviewer']}", f"Date: {signoff['date']}", "",
             "For each risk write a **Decision**: `approve`, `amend` or `reject`.",
             "- `amend`: say in Comment what to change (rating, wording, scope).",
             "- `reject`: say in Comment why; the risk leaves the audit scope.",
             "Avoid the `|` character in comments. Decisions here are kept when the register is rebuilt.", "",
             "| Risk ID | Risk | Likelihood | Impact | Score | Band | Decision | Comment |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    ids = set()
    for b in built:
        d = decisions.get(b["id"], {})
        ids.add(b["id"])
        band = b["band"]["band"] if sc.usable else "n/a"
        lines.append(f"| {b['id']} | {esc(b['raw']['title'])} | {b['final_l']} | {b['impact']} | {b['score']} | "
                     f"{band} | {esc(d.get('decision', ''))} | {esc(d.get('comment', ''))} |")
    orphans = {k: v for k, v in decisions.items() if k not in ids and (v["decision"] or v["comment"])}
    if orphans:
        lines += ["", "## Decisions on risks no longer in the register", "",
                  "| Risk ID | Risk | Decision | Comment |", "| --- | --- | --- | --- |"]
        for k, v in sorted(orphans.items()):
            lines.append(f"| {k} | {esc(v['title'])} | {esc(v['decision'])} | {esc(v['comment'])} |")
    lines += ["", "## General comments", "",
              "<!-- Scope, missing risks or anything else; kept when this file is rewritten. -->", ""]
    if general:
        lines += [general, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- revision

def flat(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flat(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(flat(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = d
    return out


def diff(old, new):
    a, b = flat(old), flat(new)
    return [(k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def read_meta(path):
    if not path.exists():
        return None
    m = re.search(r"<!-- register-meta\n(.*?)\n-->", path.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else None


def check_revision(rev, built, dropped, meta, decisions, general, inputs, errors):
    """Validate a post-gate revision. Returns (base_snapshot, change_rows, overrides, applied_amends)."""
    if not isinstance(rev, dict) or not isinstance(rev.get("number"), int) or rev["number"] < 1:
        errors.append("revision.number must be an integer >= 1")
        return None
    if meta is None:
        errors.append("revision build needs the register the auditor reviewed (outputs/risk-register.md "
                      "with its register-meta block); it is missing")
        return None
    n = rev["number"]
    if meta["revision"] == n:
        base, prior = meta["base_snapshot"], meta.get("prior_applied_amends", {})
        overrides = dict(meta.get("prior_overrides", {}))
    elif meta["revision"] == n - 1:
        base, prior = meta["snapshot"], meta.get("applied_amends", {})
        overrides = dict(meta.get("overrides", {}))
    else:
        errors.append(f"revision.number {n} does not follow the reviewed register's revision {meta['revision']}")
        return None
    for k, v in inputs.items():
        if base["inputs"].get(k) != v:
            errors.append(f"{k} changed since the auditor reviewed the register; the auditor did not ask for "
                          f"that. Rebuild without a revision block and send the register back for review.")
    changes = rev.get("changes", [])
    if not isinstance(changes, list):
        errors.append("revision.changes must be a list")
        changes = []
    claimed = {}
    for c in changes:
        if not isinstance(c, dict) or not c.get("risk_id") or not c.get("summary"):
            errors.append(f"revision.changes entry needs risk_id and summary: {c}")
            continue
        claimed[c["risk_id"]] = c
    cur = {b["id"]: b for b in built}
    rows, applied = [], dict(prior)
    for rid, snap in base["risks"].items():
        d = decisions.get(rid, {})
        dec, com = d.get("decision", ""), d.get("comment", "")
        if not dec:
            errors.append(f"{rid}: no auditor decision in auditor-comments.md; the gate is not closed")
            continue
        if rid in dropped:
            errors.append(f"{rid}: no longer builds ({dropped[rid]})")
            continue
        if rid not in cur:
            errors.append(f"{rid}: removed from risk-ratings.json; keep it (status 'rejected' if the auditor rejected it)")
            continue
        ds = diff(snap["raw"], cur[rid]["raw"])
        c = claimed.pop(rid, None)
        if c and c.get("decision") != dec:
            errors.append(f"{rid}: revision.changes says decision '{c.get('decision')}', the auditor wrote '{dec}'")
        if dec == "approve":
            if ds:
                errors.append(f"{rid}: approved by the auditor but changed ({', '.join(k for k, _, _ in ds)}); "
                              f"the auditor did not ask for that")
        elif dec == "reject":
            if not com:
                errors.append(f"{rid}: rejected without a comment; ask the auditor for the reason")
            if cur[rid]["status"] != "rejected":
                errors.append(f"{rid}: rejected by the auditor but status is not 'rejected' (decision unapplied)")
            extra = [k for k, _, _ in ds if k != "status"]
            if extra:
                errors.append(f"{rid}: rejected; only status may change, but {', '.join(extra)} changed")
            if cur[rid]["status"] == "rejected":
                overrides[rid] = [f"Rejected by the auditor: {com}"]
        elif dec == "amend":
            if not com:
                errors.append(f"{rid}: amend without a comment; ask the auditor what to change")
            if cur[rid]["status"] == "rejected":
                errors.append(f"{rid}: the auditor asked to amend, not reject")
            if not ds and applied.get(rid) != com:
                errors.append(f"{rid}: the auditor asked to amend ('{com}') but nothing changed (decision unapplied)")
            if ds:
                applied[rid] = com
                labels = {"likelihood.score": "Likelihood", "impact.score": "Impact", "impact.column": "Impact column"}
                ov = [f"{labels[k]} {new} (auditor override; was {old})" for k, old, new in ds if k in labels]
                overrides[rid] = ov + [f"Amended at the auditor's request: {com}"]
        if ds and not c:
            errors.append(f"{rid}: changed ({', '.join(k for k, _, _ in ds)}) but not listed in revision.changes")
        if c and not ds:
            errors.append(f"{rid}: listed in revision.changes but nothing changed")
        if ds or c:
            rows.append((rid, dec, com, ds, c["summary"] if c else ""))
    for rid, b in cur.items():
        if rid in base["risks"]:
            continue
        c = claimed.pop(rid, None)
        if not (c and c.get("decision") == "added" and general):
            errors.append(f"{rid}: new risk not in the reviewed register; allowed only when the auditor's "
                          f"general comments ask for it and revision.changes lists it with decision 'added'")
        else:
            rows.append((rid, "added", general[:120], [("risk", None, "added")], c["summary"]))
            overrides[rid] = [f"Added at the auditor's request (general comments)"]
    for rid in claimed:
        errors.append(f"revision.changes lists {rid}, which is not in the reviewed register")
    return base, rows, overrides, applied


# ---------------------------------------------------------------- render

def render(ctx, sc, built, dropped_rows, warnings, decisions, inputs, rev_info, ratings_path):
    revision, rows, overrides = rev_info["revision"], rev_info["rows"], rev_info["overrides"]
    L = ["# Risk register: procurement audit planning, West Berkshire Council", ""]
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L.append(f"**Revision {revision}** · built {when} by `build_register.py` from `{ratings_path}`")
    L += ["", f"*{ctx.analytics.get('language', 'Results are risk indicators to investigate, not findings.')}* "
          "Nothing in this register states wrongdoing by the council, a department or a supplier.", ""]
    if revision:
        L += [f"## Revision {revision}: what changed", "",
              "Changes made in response to the auditor's decisions in `outputs/auditor-comments.md`. "
              "The builder checked every decision was applied and nothing else changed.", "",
              "| Risk | Auditor decision | Auditor comment | Fields changed | Assessor's note |",
              "| --- | --- | --- | --- | --- |"]
        for rid, dec, com, ds, summ in rows:
            fields = "; ".join(f"`{k}`: {esc(o)} → {esc(n)}" if not isinstance(o, str) or len(str(o)) < 40
                               else f"`{k}`" for k, o, n in ds)
            L.append(f"| {rid} | {dec} | {esc(com)} | {fields} | {esc(summ)} |")
        if not rows:
            L.append("| — | all approved | | none | |")
        L.append("")

    L += ["## Scoring method", ""]
    if sc.usable:
        L += ["The council's own method, from the Risk Management Strategy 2024-27 as extracted into "
              "`outputs/history.json`: likelihood (Table 2, p15) × impact (Table 1, p14) on 1-5 scales; "
              "matrix label from Figure 1 (p18); band, escalation and response from Table 4 (p19).", "",
              "| Score | Likelihood (Table 2) | Impact (Table 1) |", "| --- | --- | --- |"]
        for n in range(5, 0, -1):
            li = sc.lik[n]
            L.append(f"| {n} | {li['label']}: {li['incidents']} ({li['probability']}) | {sc.imp[n]['label']} |")
        L += ["", "| Band (Table 4) | Score | Escalation | Response |", "| --- | --- | --- | --- |"]
        for b in sc.bands:
            L.append(f"| {(b['band'] + ' ' + b.get('rag', '')).strip()} | {b['score_range']} | {esc(b['escalation'])} | {esc(b['response'])} |")
        L += ["", "### Conflicting thresholds in the scoring method", "",
              "The strategy states some thresholds two ways (recorded as discrepancies in history.json). "
              "This register uses one and marks the other; none is resolved silently.", "",
              "| Ref | Topic | Used | Marked, not used |", "| --- | --- | --- | --- |"]
        for c in sc.choices:
            L.append(f"| {c['ref']} | {c['topic']} | {c['used']} | {c['marked']} |")
    else:
        L += [f"**Fallback scale.** history.json reports no usable council scoring method ({sc.reason}), "
              "so likelihood and impact use 1-5 Very low…Very high and score = likelihood × impact. "
              "There is no council matrix, so no matrix label or band is given.", ""]
    L += ["", "### Likelihood rubric", "",
          "The builder checks each likelihood against the metrics cited in its justification "
          "(see the risk-assessment skill): 1 = no non-zero test metric; 2 = a non-zero test metric; "
          "3 = a non-zero metric in general procurement; 4 = non-zero metrics from two or more tests "
          "including general procurement; 5 = only a 4 raised by a repeat-finding uplift. A score below "
          "the rubric level carries a cited reason.", ""]

    L += ["## Inputs", "", "| File | sha256 |", "| --- | --- |"]
    for k, v in inputs.items():
        L.append(f"| `{k}` | `{v[:16]}…` |")
    L.append("")

    active = [b for b in built if b["status"] != "rejected"]
    L += ["## Summary", "",
          f"{len(active)} risk(s) rated" + (f", {len(built) - len(active)} rejected by the auditor" if len(active) < len(built) else "")
          + (f", {len(dropped_rows)} excluded for want of a citation" if dropped_rows else "") + ".", ""]
    if sc.usable:
        L += ["| ID | Risk | Likelihood | Impact | Score | Matrix label (Fig 1) | Band (Table 4) | Corporate Risk Register (Table 4) |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    else:
        L += ["| ID | Risk | Likelihood | Impact | Score |", "| --- | --- | --- | --- | --- |"]
    for b in sorted(built, key=lambda b: (b["status"] == "rejected", -b["score"], b["id"])):
        mark = " ✱" if b["id"] in overrides else ""
        title = esc(b["filled"]["title"]) + (" *(rejected by auditor)*" if b["status"] == "rejected" else "")
        cells = f"| {b['id']}{mark} | {title} | {b['final_l']} {sc.lik_label(b['final_l'])} | {b['impact']} {sc.imp_label(b['impact'])} | {b['score']} |"
        if sc.usable:
            crr = "Yes" if b["band"]["band"] == "Extreme" else "No"
            if crr == "No" and sc.fig4_min and b["score"] >= sc.fig4_min:
                crr = "No †"
            cells += f" {b['matrix_label']} | {b['band']['band']} {b['band'].get('rag', '')} | {crr} |"
        L.append(cells)
    L.append("")
    if overrides:
        L.append("✱ auditor override: see the risk's entry and the revision table.")
    if sc.usable and any(sc.fig4_min and 9 <= b["score"] < 15 for b in built):
        L.append(f"† Figure 4 ('Score {sc.fig4_min} or above') would also place this risk on the Corporate Risk "
                 "Register; Table 4 is used (DIS-04).")
    L.append("")

    L += ["## Risks", ""]
    for b in sorted(built, key=lambda b: (b["status"] == "rejected", -b["score"], b["id"])):
        f, r = b["filled"], b["raw"]
        L += [f"### {b['id']} · {render_cites(f['title'], ctx)}", ""]
        for o in overrides.get(b["id"], []):
            L.append(f"> **Auditor override.** {o}")
        if b["id"] in overrides:
            L.append("")
        lj = render_cites(f["likelihood.justification"], ctx)
        L.append(f"- **Likelihood: {b['final_l']} {sc.lik_label(b['final_l'])}.** {lj}")
        L.append(f"  - Rubric level {b['rubric'][0]} ({b['rubric'][1]}).")
        if "likelihood.below_rubric_reason" in f:
            L.append(f"  - Rated below the rubric level: {render_cites(f['likelihood.below_rubric_reason'], ctx)}")
        if b["uplift"]:
            ids = ", ".join(g[1] for g in b["uplift"])
            L.append(f"  - **Repeat-finding uplift: +1** (base {b['base_l']} → {b['final_l']}), citing {ids}: "
                     f"{render_cites(f['likelihood.uplift.justification'], ctx)}")
        col = sc.columns.get(b["column"], b["column"]) if sc.usable else b["column"]
        L.append(f"- **Impact: {b['impact']} {sc.imp_label(b['impact'])} ({col}).** "
                 f"{render_cites(f['impact.justification'], ctx)}")
        if sc.usable and b["column"] in sc.columns:
            L.append(f"  - Table 1, {col}, {b['impact']}: \"{sc.imp[b['impact']].get(b['column'], '')}\"")
        if sc.usable:
            bd = b["band"]
            L.append(f"- **Score: {b['score']}** → Figure 1: {b['matrix_label']} · Table 4: {bd['band']} "
                     f"{bd.get('rag', '')}".rstrip() + f". Escalation: {bd['escalation'].rstrip('.')}. Response: {bd['response']}")
        else:
            L.append(f"- **Score: {b['score']}** (fallback scale; no band)")
        L.append("- **Evidence:**")
        for j in range(len(r["evidence"])):
            L.append(f"  - {render_cites(f[f'evidence[{j}]'], ctx)}")
        L.append(f"- **Proposed focus:** {render_cites(f['proposed_focus'], ctx)}")
        L.append("- **Sources cited:**")
        for (kind, ref), val in sorted(b["cited"].items()):
            if kind == "rule":
                L.append(f"  - {ref}: clause {val['clause']}, p{val['page']}: {val['condition']}")
            elif kind == "metric":
                try:
                    shown = fmt_value(val, ref, None)
                except ValueError:
                    shown = f"{type(val).__name__} of {len(val)}" if isinstance(val, (list, dict)) else repr(val)
                L.append(f"  - `{ref}` = {shown}")
            else:
                lst, item = val
                desc = item.get("audit_title") or item.get("review_title") or item.get("what") or item.get("description", "")
                ops = ", ".join(opinions(item))
                L.append(f"  - {ref} ({lst}): {desc[:140]}" + (f": {ops}" if ops else "")
                         + (f" ({item.get('period')})" if item.get("period") else "")
                         + f", {item.get('source', 'history.json')}" + (f" p{item['pdf_page']}" if item.get("pdf_page") else ""))
        L.append("")

    if dropped_rows:
        L += ["## Excluded risks", "",
              "Dropped by the builder: a likelihood or impact justification with no resolvable citation "
              "cannot be rated (hard rule).", "", "| ID | Risk | Reason |", "| --- | --- | --- |"]
        for rid, title, reason in dropped_rows:
            L.append(f"| {rid} | {esc(title)} | {esc(reason)} |")
        L.append("")
    if warnings:
        L += ["## Builder warnings", ""] + [f"- {w}" for w in warnings] + [""]

    L += ["## Auditor decisions", ""]
    if revision:
        L.append(f"Decisions from `outputs/auditor-comments.md`, applied in revision {revision}.")
    else:
        L.append("Pending. Record `approve`, `amend` or `reject` for every risk in `outputs/auditor-comments.md`, "
                 "with a comment for amend and reject. The risk-assessor then rebuilds this register as a revision; "
                 "audit planning starts only after that.")
    L += ["", "| Risk | Decision | Comment |", "| --- | --- | --- |"]
    for b in sorted(built, key=lambda b: b["id"]):
        d = decisions.get(b["id"], {})
        L.append(f"| {b['id']} | {d.get('decision') or '*pending*'} | {esc(d.get('comment', ''))} |")
    L.append("")
    return L


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ratings", default=str(ROOT / "outputs/risk-ratings.json"))
    ap.add_argument("--analytics", default=str(ROOT / "outputs/analytics.json"))
    ap.add_argument("--history", default=str(ROOT / "outputs/history.json"))
    ap.add_argument("--rules", default=str(ROOT / "outputs/rules.json"))
    ap.add_argument("--out-dir", default=str(ROOT / "outputs"))
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    reg_path, com_path = out / "risk-register.md", out / "auditor-comments.md"

    try:
        ratings = load_json(a.ratings, "risk-ratings.json")
        ctx = Context(load_json(a.analytics, "analytics.json"), load_json(a.history, "history.json"),
                      load_json(a.rules, "rules.json"))
        if (ctx.analytics.get("self_check") or {}).get("passed") is not True:
            raise InputError("analytics.json self_check did not pass; re-run the spend-analyst first")
        if not isinstance(ratings, dict) or not isinstance(ratings.get("risks"), list) or not ratings["risks"]:
            raise InputError("risk-ratings.json must be an object with a non-empty 'risks' list")
        errors = []
        sc = Scoring(ctx.history, errors)
    except InputError as e:
        print(f"STOP: {e}")
        return 2
    inputs = {"outputs/analytics.json": sha256(a.analytics), "outputs/history.json": sha256(a.history),
              "outputs/rules.json": sha256(a.rules)}

    for i, r in enumerate(ratings["risks"]):
        errors += check_shape(r, i)
    ids = [r.get("risk_id") for r in ratings["risks"] if isinstance(r, dict)]
    errors += [f"duplicate risk_id {x}" for x in sorted({x for x in ids if ids.count(x) > 1})]
    if errors:
        return report(errors, [], [])

    built, dropped, dropped_rows, warnings = [], {}, [], []
    for r in ratings["risks"]:
        b, drop, errs, warns = assess(r, ctx, sc)
        if drop:
            dropped[r["risk_id"]] = drop
            dropped_rows.append((r["risk_id"], r["title"], drop))
            continue
        built.append(b)
        errors += errs
        warnings += warns

    decisions, general, problems = read_comments(com_path)
    rev = ratings.get("revision")
    meta = read_meta(reg_path)
    rev_info = {"revision": 0, "rows": [], "overrides": {}, "applied": {}, "base": None}
    if rev:
        errors += problems
        res = check_revision(rev, built, dropped, meta, decisions, general, inputs, errors)
        if res:
            base, rows, overrides, applied = res
            rev_info.update(revision=rev["number"], rows=rows, overrides=overrides, applied=applied, base=base)
    else:
        warnings += problems
        if meta and meta.get("revision"):
            warnings.append(f"the existing register is revision {meta['revision']}; this build has no revision "
                            f"block, so it replaces it with revision 0 and the auditor must review it again")
        for b in built:
            if b["status"] == "rejected":
                errors.append(f"{b['id']}: status 'rejected' is set only in a revision, after an auditor reject")
    if errors:
        return report(errors, warnings, dropped_rows)

    try:
        shown = str(Path(a.ratings).resolve().relative_to(ROOT))
    except ValueError:
        shown = a.ratings
    lines = render(ctx, sc, built, dropped_rows, warnings, decisions, inputs, rev_info, shown)
    # What the previous revision had already applied, so a re-run of the same
    # revision checks against the same starting point.
    if rev and meta["revision"] == rev["number"]:
        prior_applied, prior_overrides = meta.get("prior_applied_amends", {}), meta.get("prior_overrides", {})
    elif rev:
        prior_applied, prior_overrides = meta.get("applied_amends", {}), meta.get("overrides", {})
    else:
        prior_applied, prior_overrides = {}, {}
    snapshot = {"inputs": inputs, "risks": {b["id"]: {"raw": b["raw"]} for b in built}}
    new_meta = {"revision": rev_info["revision"], "snapshot": snapshot,
                "base_snapshot": rev_info["base"],
                "applied_amends": rev_info["applied"], "overrides": rev_info["overrides"],
                "prior_applied_amends": prior_applied, "prior_overrides": prior_overrides,
                "risks": {b["id"]: {"likelihood": b["final_l"], "impact": b["impact"], "score": b["score"],
                                    "band": b["band"]["band"] if sc.usable else None, "status": b["status"],
                                    "title": b["filled"]["title"]} for b in built},
                "scoring": "council" if sc.usable else "fallback"}
    out.mkdir(parents=True, exist_ok=True)
    reg_path.write_text("<!-- register-meta\n" + json.dumps(new_meta, ensure_ascii=False) + "\n-->\n"
                        + "\n".join(lines), encoding="utf-8")
    write_comments(com_path, built, decisions, general, rev_info["revision"], sc)
    return report([], warnings, dropped_rows, built=len(built), revision=rev_info["revision"])


def report(errors, warnings, dropped_rows, built=None, revision=None):
    for e in errors:
        print(f"ERROR {e}")
    for rid, _, why in dropped_rows:
        print(f"DROPPED {rid}: {why}")
    for w in warnings:
        print(f"WARNING {w}")
    if errors:
        print(f"FAIL: {len(errors)} error(s); nothing written")
        return 1
    print(f"BUILT revision {revision}: {built} risk(s) in the register, {len(dropped_rows)} dropped, "
          f"{len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
