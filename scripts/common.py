"""Shared helpers for the spend-analyst scripts.

Thresholds are never hard-coded here: they are derived from outputs/rules.json.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SPEND_DIR = DATA / "spend"
CONTRACTS_CSV = DATA / "contracts.csv"
OUTPUTS = ROOT / "outputs"
RULES = OUTPUTS / "rules.json"
FULL = OUTPUTS / "analytics-full"
ANALYTICS = OUTPUTS / "analytics.json"

SPEND_CLEAN = FULL / "spend_clean.csv"
EXCLUSIONS = FULL / "exclusions.csv"
CLEAN_SUMMARY = FULL / "clean_summary.json"
NOTICE_SUPPLIERS = FULL / "notice_suppliers.csv"
CONTRACTS_SUMMARY = FULL / "contracts_summary.json"

SHEET = "Data to publish"
REQUIRED_COLS = ["Service", "Expenditure category", "Narrative", "Date",
                 "Net amount", "Supplier name"]
TEXT_DATE_FORMAT = "%m/%d/%y"

LANGUAGE = "Results are risk indicators to investigate, not findings."


def ensure_full_dir():
    FULL.mkdir(parents=True, exist_ok=True)
    return FULL


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Name normalisation
# --------------------------------------------------------------------------
NORMALISATION_STEPS = [
    "1. uppercase; '&' -> ' AND '",
    "2. delete apostrophes (WOMEN'S -> WOMENS); all other punctuation -> space",
    "3. drop tokens LTD, LIMITED, PLC, LLP; drop a trailing 'CHAPS ONLY' / 'BACS ONLY'",
    "4. join runs of single-letter tokens (D J TRAVEL -> DJ TRAVEL); collapse whitespace",
]
_DROP_TOKENS = {"LTD", "LIMITED", "PLC", "LLP"}
_APOS = re.compile(r"['‘’ʼ`]")
_PUNCT = re.compile(r"[^A-Z0-9\s]")


def normalise(name):
    if name is None:
        return ""
    s = str(name)
    if s.lower() == "nan":
        return ""
    s = s.upper().replace("&", " AND ")
    s = _APOS.sub("", s)
    s = _PUNCT.sub(" ", s)
    tokens = [t for t in s.split() if t not in _DROP_TOKENS]
    while len(tokens) >= 2 and tokens[-1] == "ONLY" and tokens[-2] in ("CHAPS", "BACS"):
        tokens = tokens[:-2]
    out, run = [], []
    for t in tokens:
        if len(t) == 1 and t.isalpha():
            run.append(t)
        else:
            if run:
                out.append("".join(run))
                run = []
            out.append(t)
    if run:
        out.append("".join(run))
    return " ".join(out)


def aliases(norm):
    """Full normalised name plus the parts either side of ' T A ' / ' TRADING AS '.

    Note: step 4 of normalise joins 'T A' into 'TA', so ' TA ' is also
    treated as the trading-as separator.
    """
    out = [norm] if norm else []
    padded = f" {norm} "
    for sep in (" T A ", " TRADING AS ", " TA "):
        if sep in padded:
            before, after = padded.split(sep, 1)
            for part in (before.strip(), after.strip()):
                if part and part not in out:
                    out.append(part)
    return out


# --------------------------------------------------------------------------
# Threshold derivation from rules.json
# --------------------------------------------------------------------------
def load_rules(rules_path=RULES):
    with open(rules_path, encoding="utf-8") as fh:
        return json.load(fh)


def _param_value(params, name):
    p = params.get(name) or {}
    v = p.get("value") if isinstance(p, dict) else None
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def load_thresholds(rules_path=RULES):
    doc = load_rules(rules_path)
    rules = doc["rules"]
    params = doc.get("parameters", {})

    boundaries = {}  # value -> dict
    skipped = {}  # param -> dict
    conflicts = []

    def add(value, rule, side):
        b = boundaries.setdefault(value, {"value": value, "rule_ids": [], "scopes": [],
                                          "_low_incl": [], "_high_incl": []})
        if rule["rule_id"] not in b["rule_ids"]:
            b["rule_ids"].append(rule["rule_id"])
        for s in rule.get("scope") or []:
            if s not in b["scopes"]:
                b["scopes"].append(s)
        if side == "low":
            b["_low_incl"].append((rule["rule_id"], rule.get("threshold_low_inclusive")))
        else:
            b["_high_incl"].append((rule["rule_id"], rule.get("threshold_high_inclusive")))

    for r in rules:
        clause = str(r.get("clause", ""))
        if not (clause.startswith("App A row") or clause.startswith("App B row")):
            continue
        for side in ("low", "high"):
            val = r.get(f"threshold_{side}")
            param = r.get(f"threshold_{side}_param")
            if param:
                pv = _param_value(params, param)
                if pv is None:
                    s = skipped.setdefault(param, {"param": param, "rule_ids": [],
                                                   "reason": f"{param} is null in rules.json"})
                    if r["rule_id"] not in s["rule_ids"]:
                        s["rule_ids"].append(r["rule_id"])
                    continue
                val = pv
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                add(val, r, side)

    out = []
    for v in sorted(boundaries):
        b = boundaries[v]
        lows = [x for x in b["_low_incl"] if x[1] is not None]
        highs = [x for x in b["_high_incl"] if x[1] is not None]
        if lows:
            bsi = bool(lows[0][1])
        elif highs:
            bsi = not bool(highs[0][1])
        else:
            bsi = True
        implied = {bool(x[1]) for x in lows} | {not bool(x[1]) for x in highs}
        if len(implied) > 1:
            conflicts.append(
                f"boundary {v}: rules disagree on whether the band above starts inclusively "
                f"(low-side {lows}, high-side {highs}); used the low-side rule "
                f"({lows[0][0] if lows else highs[0][0]}) -> band_starts_inclusive={bsi}")
        out.append({"value": v, "rule_ids": b["rule_ids"], "scopes": b["scopes"],
                    "band_starts_inclusive": bsi})

    def min_low(pred):
        cands = []
        for r in rules:
            if not str(r.get("clause", "")).startswith("App B row"):
                continue
            ra = (r.get("required_action") or "").lower()
            low = r.get("threshold_low")
            if pred(ra) and isinstance(low, (int, float)) and not isinstance(low, bool):
                cands.append((low, r))
        if not cands:
            return None
        low, r = min(cands, key=lambda x: x[0])
        incl = r.get("threshold_low_inclusive")
        return {"value": low, "inclusive": True if incl is None else bool(incl),
                "rule_ids": [c[1]["rule_id"] for c in cands if c[0] == low]}

    quote = min_low(lambda ra: "at least three" in ra)
    pub = min_low(lambda ra: "cdp" in ra)
    if quote is None:
        raise ValueError("rules.json: cannot derive quote_threshold (no App B rule with "
                         "'at least three' and a numeric threshold_low)")
    if pub is None:
        raise ValueError("rules.json: cannot derive publication_threshold (no App B rule "
                         "mentioning the CDP with a numeric threshold_low)")

    def ref(clause_exact):
        ids = [r["rule_id"] for r in rules if str(r.get("clause", "")) == clause_exact]
        return ids

    refs = {
        "anti_avoidance_6_16": ref("6.16"),
        "extensions_app_c_row_d": ref("App C row D"),
        "variations_app_c_row_e": ref("App C row E"),
        "placements_app_c_row_f": ref("App C row F"),
    }
    for k, v in refs.items():
        if not v:
            raise ValueError(f"rules.json: no rule found for {k}")

    return {
        "boundaries": out,
        "skipped_tiers": list(skipped.values()),
        "quote_threshold": quote,
        "publication_threshold": pub,
        "rule_refs": refs,
        "derivation_notes": conflicts,
    }


def reaches(value, threshold, inclusive):
    return value >= threshold if inclusive else value > threshold


if __name__ == "__main__":
    print(json.dumps(load_thresholds(), indent=1))
