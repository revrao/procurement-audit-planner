"""Run the risk-indicator tests on the cleaned spend and write outputs/analytics.json.

Full lists go to outputs/analytics-full/<test>.csv. Prints short aggregates only.
All thresholds come from outputs/rules.json via common.load_thresholds().
"""
import difflib
import json
import sys
from datetime import datetime, timezone

import pandas as pd

from common import (ANALYTICS, CLEAN_SUMMARY, CONTRACTS_CSV, CONTRACTS_SUMMARY, FULL, LANGUAGE,
                    NORMALISATION_STEPS, NOTICE_SUPPLIERS, RULES, SPEND_CLEAN, aliases, ensure_full_dir,
                    load_thresholds, reaches, sha256)

ANN_LABEL = "annualised estimate"
CAND_RATIO = 0.85
CAND_MIN_CONTAIN = 8
SPLIT_WINDOW_DAYS = 30
DUP_DAYS = 7
CLUSTER_BAND = 0.9
COMPARE_BAND = 0.8
RATIO_FLAG = 1.25
COVERAGE_WARN = 0.25
TOP = 20


def rel(p):
    return str(p.relative_to(FULL.parent.parent))


def gbp(pence):
    return round(int(pence) / 100, 2)


def ids(series):
    return ";".join(series.tolist())


def main_tag(g):
    s = g.groupby("tag")["pence"].sum().sort_values(ascending=False)
    return s.index[0]


def tag_mix(g):
    s = g.groupby("tag")["pence"].sum().sort_values(ascending=False)
    return "; ".join(f"{t}={gbp(v)}" for t, v in s.items())


def by_tag_from(df, tag_col, gbp_col):
    out = {}
    for t, g in df.groupby(tag_col):
        out[t] = {"items": int(len(g)), "gbp": round(float(g[gbp_col].sum()), 2)}
    return out


def entry(rule_ids, parameters, counts, gbp_total, by_tag, top, full_path, caveats, **extra):
    e = {"status": "run", "rule_ids": rule_ids, "parameters": parameters, "counts": counts,
         "gbp_total": gbp_total, "by_tag": by_tag, "top20": top,
         "full_list": rel(full_path) if full_path else None, "caveats": caveats}
    e.update(extra)
    return e


def skipped(reason, rule_ids):
    return {"status": "skipped", "reason": reason, "rule_ids": rule_ids, "parameters": {}, "counts": {},
            "gbp_total": 0, "by_tag": {}, "top20": [], "full_list": None, "caveats": []}


def records(df, cols):
    out = []
    for r in df[cols].to_dict("records"):
        out.append({k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()})
    return out


# ---------------------------------------------------------------------------
def load_spend():
    df = pd.read_csv(SPEND_CLEAN, dtype={"row_id": str, "Supplier name": str, "supplier_norm": str,
                                         "tag": str, "Narrative": str, "Service": str},
                     keep_default_na=False)
    df["date"] = pd.to_datetime(df["date"].str[:10], format="%Y-%m-%d")
    df["Net amount"] = pd.to_numeric(df["Net amount"])
    df["pence"] = (df["Net amount"] * 100).round().astype("int64")
    return df


def t_clustering(df, th):
    rows, per_b = [], []
    for b in th["boundaries"]:
        T = b["value"]
        lo, cmp_lo = CLUSTER_BAND * T, COMPARE_BAND * T
        a = df["Net amount"]
        in_band = (a >= lo) & ((a < T) if b["band_starts_inclusive"] else (a <= T))
        comp = (a >= cmp_lo) & (a < lo)
        n_in, n_cmp = int(in_band.sum()), int(comp.sum())
        per_b.append({"boundary": T, "band": f"[{lo:g}, {T:g}{')' if b['band_starts_inclusive'] else ']'}",
                      "comparison_band": f"[{cmp_lo:g}, {lo:g})", "in_band": n_in,
                      "in_band_gbp": round(float(a[in_band].sum()), 2), "comparison": n_cmp,
                      "ratio_band_to_comparison": round(n_in / n_cmp, 4) if n_cmp else None,
                      "rule_ids": b["rule_ids"], "scopes": b["scopes"],
                      "by_tag": by_tag_from(df[in_band], "tag", "Net amount")})
        sub = df[in_band].copy()
        sub["boundary"] = T
        rows.append(sub)
    full = pd.concat(rows, ignore_index=True) if rows else df.iloc[0:0]
    cols = ["boundary", "row_id", "Supplier name", "supplier_norm", "date", "Net amount", "tag", "Service",
            "Narrative"]
    full = full.sort_values(["Net amount", "row_id"], ascending=[False, True])
    path = FULL / "threshold_clustering.csv"
    full[cols].to_csv(path, index=False)
    top = full.head(TOP).copy()
    top["date"] = top["date"].dt.strftime("%Y-%m-%d")
    top["row_ids"] = top["row_id"].map(lambda x: [x])
    top = records(top, ["boundary", "row_ids", "Supplier name", "supplier_norm", "date", "Net amount", "tag"])
    rule_ids = sorted({r for b in th["boundaries"] for r in b["rule_ids"]})
    return entry(rule_ids,
                 {"boundaries": [b["value"] for b in th["boundaries"]], "band_low_factor": CLUSTER_BAND,
                  "comparison_band_factors": [COMPARE_BAND, CLUSTER_BAND],
                  "band_upper": "exclusive of T when the band above starts inclusively, else inclusive"},
                 {"items": int(len(full)), "by_boundary": per_b},
                 round(float(full["Net amount"].sum()), 2), by_tag_from(full, "tag", "Net amount"), top, path,
                 ["Bands in the rules apply to contract value, not to individual payments; a payment just under "
                  "a boundary is an indicator to investigate, not evidence about the contract's value.",
                  "The scope of App B rows (goods/services vs works/concessions/light touch) cannot be told "
                  "from spend data, so every boundary is applied to every payment.",
                  "A payment in more than one boundary's band would be counted once per boundary."])


def t_split(df, th):
    groups = []
    for b in th["boundaries"]:
        T = b["value"]
        Tp = int(round(T * 100))
        incl = b["band_starts_inclusive"]
        under = df[(df["pence"] < Tp) if incl else (df["pence"] <= Tp)]
        for sup, g in under.groupby("supplier_norm"):
            if len(g) < 2:
                continue
            g = g.sort_values(["date", "row_id"])
            dates = g["date"].tolist()
            pence = g["pence"].tolist()
            rids = g["row_id"].tolist()
            tags = g["tag"].tolist()
            names = g["Supplier name"].tolist()
            i, n = 0, len(g)
            while i < n:
                j = i
                while j + 1 < n and (dates[j + 1] - dates[i]).days <= SPLIT_WINDOW_DAYS - 1:
                    j += 1
                total = sum(pence[i:j + 1])
                if j > i and reaches(total, Tp, incl):
                    sub = g.iloc[i:j + 1]
                    groups.append({"boundary": T, "supplier_norm": sup, "supplier_names": "; ".join(sorted(set(names[i:j + 1]))),
                                   "first_date": dates[i].strftime("%Y-%m-%d"),
                                   "last_date": dates[j].strftime("%Y-%m-%d"),
                                   "span_days": (dates[j] - dates[i]).days, "n": j - i + 1,
                                   "sum_gbp": gbp(total), "max_single_gbp": gbp(max(pence[i:j + 1])),
                                   "tag": main_tag(sub), "row_ids": ";".join(rids[i:j + 1])})
                    i = j + 1
                else:
                    i += 1
    full = pd.DataFrame(groups)
    path = FULL / "split_purchases.csv"
    if full.empty:
        full = pd.DataFrame(columns=["boundary", "supplier_norm", "supplier_names", "first_date", "last_date",
                                     "span_days", "n", "sum_gbp", "max_single_gbp", "tag", "row_ids"])
    full = full.sort_values(["boundary", "sum_gbp"], ascending=[False, False])
    full.to_csv(path, index=False)
    distinct = set(r for s in full["row_ids"] for r in s.split(";"))
    gbp_distinct = round(float(df.loc[df["row_id"].isin(distinct), "Net amount"].sum()), 2)
    by_b = []
    for b in th["boundaries"]:
        fb = full[full["boundary"] == b["value"]]
        by_b.append({"boundary": b["value"], "groups": int(len(fb)), "gbp": round(float(fb["sum_gbp"].sum()), 2),
                     "suppliers": int(fb["supplier_norm"].nunique()),
                     "by_tag": by_tag_from(fb, "tag", "sum_gbp")})
    top = full.sort_values("sum_gbp", ascending=False).head(TOP).copy()
    top["row_ids"] = top["row_ids"].map(lambda s: s.split(";"))
    top = records(top, list(top.columns))
    ref = th["rule_refs"]["anti_avoidance_6_16"]
    return entry(ref + sorted({r for b in th["boundaries"] for r in b["rule_ids"]}),
                 {"boundaries": [b["value"] for b in th["boundaries"]], "window_days_inclusive": SPLIT_WINDOW_DAYS,
                  "min_payments": 2,
                  "method": "per supplier and boundary: payments each under T sorted by date; from each payment "
                            "look forward 29 days; if >=2 payments and the sum reaches the band above T record a "
                            "group and continue after its last payment (no overlap)"},
                 {"items": int(len(full)), "distinct_payments": len(distinct), "by_boundary": by_b},
                 gbp_distinct, by_tag_from(full, "tag", "sum_gbp"), top, path,
                 ["gbp_total is the £ of distinct payments in any group; by_boundary £ sums group totals and a "
                  "payment can sit in groups for several boundaries.",
                  "Regular instalments under one contract (e.g. weekly care placements, monthly fees) produce "
                  "groups that are expected; read results by tag.",
                  "Groups are indicators to investigate under clause 6.16, not evidence that a requirement was "
                  "divided."])


def t_duplicates(df, clean):
    chains = []
    for (sup, p), g in df.groupby(["supplier_norm", "pence"]):
        if len(g) < 2:
            continue
        g = g.sort_values(["date", "row_id"])
        cur = [g.iloc[0]]
        for k in range(1, len(g)):
            r = g.iloc[k]
            if (r["date"] - cur[-1]["date"]).days <= DUP_DAYS:
                cur.append(r)
            else:
                if len(cur) >= 2:
                    chains.append(cur)
                cur = [r]
        if len(cur) >= 2:
            chains.append(cur)
    rows = []
    for c in chains:
        sub = pd.DataFrame(c)
        rows.append({"supplier_norm": c[0]["supplier_norm"],
                     "supplier_names": "; ".join(sorted(set(sub["Supplier name"]))),
                     "amount_gbp": gbp(c[0]["pence"]), "n": len(c),
                     "first_date": c[0]["date"].strftime("%Y-%m-%d"), "last_date": c[-1]["date"].strftime("%Y-%m-%d"),
                     "max_gap_days": int(sub["date"].diff().dt.days.max()),
                     "chain_gbp": gbp(sub["pence"].sum()), "repeat_gbp": gbp(sub["pence"].sum() - c[0]["pence"]),
                     "tag": main_tag(sub), "row_ids": ";".join(sub["row_id"])})
    cols = ["supplier_norm", "supplier_names", "amount_gbp", "n", "first_date", "last_date", "max_gap_days",
            "chain_gbp", "repeat_gbp", "tag", "row_ids"]
    full = pd.DataFrame(rows, columns=cols).sort_values(["repeat_gbp", "supplier_norm"], ascending=[False, True])
    path = FULL / "duplicates.csv"
    full.to_csv(path, index=False)
    top = full.head(TOP).copy()
    top["row_ids"] = top["row_ids"].map(lambda s: s.split(";"))
    top = records(top, cols)
    ident = clean["identical_rows"]
    return entry([], {"same": "supplier_norm and Net amount to the penny", "max_gap_days": DUP_DAYS,
                      "chaining": "consecutive payments <= 7 days apart join one chain"},
                 {"items": int(len(full)), "payments_in_chains": int(full["n"].sum()),
                  "chain_gbp": round(float(full["chain_gbp"].sum()), 2),
                  "identical_rows_from_cleaning": {"rows": ident["count_rows"], "groups": ident["groups"],
                                                   "note": "all six source columns equal, across all loaded rows "
                                                           "(kept and excluded); row_ids in clean_summary.json"}},
                 round(float(full["repeat_gbp"].sum()), 2), by_tag_from(full, "tag", "repeat_gbp"), top, path,
                 ["gbp_total is the £ of repeat payments (each chain less its first payment).",
                  "Fixed recurring fees and per-placement weekly rates produce expected pairs; read results by tag.",
                  "No CPR rule addresses duplicate payment directly; this is a payment-control indicator."])


# ---------------------------------------------------------------------------
def supplier_table(df, factor):
    rows = []
    for sup, g in df.groupby("supplier_norm"):
        tot = int(g["pence"].sum())
        rows.append({"supplier_norm": sup, "published_names": "; ".join(sorted(set(g["Supplier name"]))),
                     "window_gbp": gbp(tot), "annualised_gbp": round(tot * factor / 100, 2),
                     "payments": int(len(g)), "main_tag": main_tag(g),
                     "placement_share": round(float(g.loc[g["tag"] == "placement", "pence"].sum()) / tot, 4) if tot else 0.0,
                     "tag_mix": tag_mix(g), "services": "; ".join(sorted(set(g["Service"]))),
                     "row_ids": ids(g.sort_values(["date", "row_id"])["row_id"])})
    return pd.DataFrame(rows)


def build_matcher(ns):
    by_name, by_alias = {}, {}
    for i, r in ns.iterrows():
        by_name.setdefault(r["supplier_norm"], []).append(i)
        for a in str(r["aliases"]).split("|"):
            if a:
                by_alias.setdefault(a, []).append(i)
    names = sorted(set(ns["supplier_norm"]))

    def match(norm):
        if norm in by_name:
            return "name", sorted(set(by_name[norm]))
        hits = set()
        for a in aliases(norm):
            hits.update(by_alias.get(a, []))
        if hits:
            return "alias", sorted(hits)
        return None, []

    def candidates(norm):
        out = []
        for n in names:
            score = difflib.SequenceMatcher(None, norm, n).ratio()
            short, long_ = (norm, n) if len(norm) <= len(n) else (n, norm)
            contained = len(short) >= CAND_MIN_CONTAIN and short in long_
            if score >= CAND_RATIO or contained:
                out.append({"notice_supplier_norm": n, "score": round(score, 4), "contained": contained})
        return sorted(out, key=lambda x: -x["score"])

    return match, candidates


def main():
    ensure_full_dir()
    th = load_thresholds()
    clean = json.load(open(CLEAN_SUMMARY, encoding="utf-8"))
    df = load_spend()
    months = int(clean["window"]["months"])
    factor = 12 / months
    w_start, w_end = df["date"].min(), df["date"].max()
    warnings = list(clean.get("warnings", [])) + list(th.get("derivation_notes", []))
    for s_ in th["skipped_tiers"]:
        warnings.append(f"tier skipped: {s_['reason']} (rules {', '.join(s_['rule_ids'])})")

    use_contracts = CONTRACTS_CSV.exists()
    tests = {}
    tests["threshold_clustering"] = t_clustering(df, th)
    tests["split_purchases"] = t_split(df, th)
    tests["duplicates"] = t_duplicates(df, clean)

    sup = supplier_table(df, factor)
    qt, pt = th["quote_threshold"], th["publication_threshold"]
    sup["reaches_quote"] = [reaches(v, qt["value"], qt["inclusive"]) for v in sup["annualised_gbp"]]
    sup["reaches_publication"] = [reaches(v, pt["value"], pt["inclusive"]) for v in sup["annualised_gbp"]]

    if use_contracts:
        csum = json.load(open(CONTRACTS_SUMMARY, encoding="utf-8"))
        warnings += list(csum.get("warnings", []))
        ns = pd.read_csv(NOTICE_SUPPLIERS, dtype=str, keep_default_na=False)
        ns["awarded_value"] = pd.to_numeric(ns["awarded_value"], errors="coerce")
        ns["n_suppliers_on_notice"] = ns["n_suppliers_on_notice"].astype(int)
        for c in ("live_in_window", "ended_before_window"):
            ns[c] = ns[c] == "True"
        match, candidates = build_matcher(ns)
        mt, mi, cands = [], [], []
        for norm in sup["supplier_norm"]:
            t, idx = match(norm)
            mt.append(t)
            mi.append(idx)
        sup["match_type"] = mt
        sup["_idx"] = mi
        sup["matched_notices"] = [";".join(sorted(set(ns.loc[i, "notice_id"]))) for i in mi]
        status = []
        cand_map = {}
        for norm, t, rq in zip(sup["supplier_norm"], sup["match_type"], sup["reaches_quote"]):
            if isinstance(t, str):  # NaN (no match) is truthy, so test the type
                status.append(t)
                continue
            if rq:
                c = candidates(norm)
                cand_map[norm] = c
                status.append("candidate only" if c else "none")
            else:
                status.append("none")
        sup["notice_match"] = status
    else:
        csum = {"status": "not provided"}
        sup["notice_match"] = "not checked"
        sup["match_type"] = None
        sup["matched_notices"] = ""

    # 4. high_value_suppliers
    hv = sup[sup["reaches_quote"]].sort_values("annualised_gbp", ascending=False)
    hv_cols = ["supplier_norm", "published_names", "window_gbp", "annualised_gbp", "payments", "main_tag",
               "tag_mix", "services", "notice_match", "matched_notices", "row_ids"]
    p_hv = FULL / "high_value_suppliers.csv"
    hv[hv_cols].to_csv(p_hv, index=False)
    top = hv.head(TOP).copy()
    top["row_ids"] = top["row_ids"].map(lambda s: s.split(";"))
    hv_counts = {"items": int(len(hv)), "suppliers_in_window": int(len(sup)),
                 "notice_match": {k: int(v) for k, v in hv["notice_match"].value_counts().items()}}
    tests["high_value_suppliers"] = entry(
        qt["rule_ids"], {"quote_threshold": qt["value"], "inclusive": qt["inclusive"],
                         "annualisation_factor": factor, "basis": ANN_LABEL},
        hv_counts, round(float(hv["window_gbp"].sum()), 2), by_tag_from(hv, "main_tag", "window_gbp"),
        records(top, hv_cols), p_hv,
        [f"annualised_gbp is an {ANN_LABEL} (window £ x {factor:g}); seasonal or one-off spend distorts it.",
         "This is the population for which to request contract evidence; by_tag counts suppliers by their "
         "main tag (by £) and window £."],
        annualised_gbp_total=round(float(hv["annualised_gbp"].sum()), 2))

    if not use_contracts:
        reason = "data/contracts.csv not provided"
        tests["off_contract"] = skipped(reason, pt["rule_ids"])
        tests["expired_notice_spend"] = skipped(reason, th["rule_refs"]["extensions_app_c_row_d"])
        tests["spend_vs_award"] = skipped(reason, th["rule_refs"]["variations_app_c_row_e"])
    else:
        # coverage
        exact = hv["match_type"].notna()
        cov_n = float(exact.mean()) if len(hv) else 0.0
        cov_gbp = float(hv.loc[exact, "window_gbp"].sum() / hv["window_gbp"].sum()) if len(hv) else 0.0
        coverage = {"high_value_suppliers": int(len(hv)), "exact_matched": int(exact.sum()),
                    "share_by_count": round(cov_n, 4), "share_by_gbp": round(cov_gbp, 4)}
        oc_caveats = [
            "Contracts Finder only shows contracts from about £25k, so this test never applies to smaller "
            "suppliers and must never be used to question them.",
            "Joins are by normalised name only (spend data carries no company number); a supplier contracted "
            "under a different legal or trading name shows as unmatched.",
            "Contracts may predate the 2021 export start or use routes that publish no notice (frameworks run by "
            "other bodies, call-offs, social care spot purchasing).",
            f"Candidates (difflib ratio >= {CAND_RATIO} or containment of >= {CAND_MIN_CONTAIN} characters) are "
            "listed for the auditor in off_contract_candidates.csv; they stay flagged and are never counted as "
            "matched."]
        if cov_n < COVERAGE_WARN:
            msg = (f"notice export covers only {cov_n:.0%} of high-value suppliers; this test reflects gaps in "
                   f"the export as much as contracting practice")
            oc_caveats.insert(0, msg)
            warnings.append("off_contract: " + msg)
        # 5. off_contract
        oc = sup[sup["reaches_publication"] & sup["match_type"].isna()].sort_values("annualised_gbp", ascending=False).copy()
        oc["mainly_placement"] = oc["placement_share"] > 0.5
        oc["candidates"] = oc["supplier_norm"].map(
            lambda n: "; ".join(f"{c['notice_supplier_norm']} ({c['score']})" for c in cand_map.get(n, [])))
        oc_cols = ["supplier_norm", "published_names", "window_gbp", "annualised_gbp", "payments", "main_tag",
                   "placement_share", "mainly_placement", "notice_match", "candidates", "services", "row_ids"]
        p_oc = FULL / "off_contract.csv"
        oc[oc_cols].to_csv(p_oc, index=False)
        crow = []
        for n in oc["supplier_norm"]:
            for c in cand_map.get(n, []):
                hits = ns[ns["supplier_norm"] == c["notice_supplier_norm"]]
                crow.append({"spend_supplier_norm": n, "notice_supplier_norm": c["notice_supplier_norm"],
                             "notice_supplier_names": "; ".join(sorted(set(hits["supplier_name"]))),
                             "notice_ids": ";".join(sorted(set(hits["notice_id"]))),
                             "score": c["score"], "contained": c["contained"], "counted_as_matched": False})
        p_cand = FULL / "off_contract_candidates.csv"
        pd.DataFrame(crow, columns=["spend_supplier_norm", "notice_supplier_norm", "notice_supplier_names",
                                    "notice_ids", "score", "contained", "counted_as_matched"]).to_csv(p_cand, index=False)
        nonp, plc = oc[~oc["mainly_placement"]], oc[oc["mainly_placement"]]
        top = nonp.head(TOP).copy()
        top["row_ids"] = top["row_ids"].map(lambda s: s.split(";"))
        placement_ref = th["rule_refs"]["placements_app_c_row_f"]
        tests["off_contract"] = entry(
            pt["rule_ids"], {"publication_threshold": pt["value"], "inclusive": pt["inclusive"],
                             "basis": ANN_LABEL, "annualisation_factor": factor,
                             "exact_match": "normalised name or trading-as alias equality",
                             "candidate_ratio": CAND_RATIO, "candidate_min_contained_chars": CAND_MIN_CONTAIN},
            {"items": int(len(oc)), "non_placement": int(len(nonp)), "mainly_placement": int(len(plc)),
             "with_candidates": int((oc["notice_match"] == "candidate only").sum()),
             "candidate_pairs": len(crow)},
            round(float(oc["window_gbp"].sum()), 2), by_tag_from(oc, "main_tag", "window_gbp"),
            records(top, oc_cols), p_oc, oc_caveats,
            coverage=coverage,
            annualised_gbp_total=round(float(oc["annualised_gbp"].sum()), 2),
            placements={"rule_ids": placement_ref,
                        "note": "Suppliers whose window £ is mainly (>50%) tagged placement are reported "
                                "separately: social care placements are excluded from competition (App C row F).",
                        "items": int(len(plc)), "gbp": round(float(plc["window_gbp"].sum()), 2),
                        "annualised_gbp": round(float(plc["annualised_gbp"].sum()), 2)},
            candidates_list=rel(p_cand),
            top20_basis="non-placement suppliers, by annualised estimate")

        # 6. expired_notice_spend
        rows = []
        for _, r in sup[sup["match_type"].notna()].iterrows():
            nsub = ns.loc[r["_idx"]]
            if nsub["ended_before_window"].all():
                rows.append({"supplier_norm": r["supplier_norm"], "published_names": r["published_names"],
                             "window_gbp": r["window_gbp"], "annualised_gbp": r["annualised_gbp"],
                             "payments": r["payments"], "main_tag": r["main_tag"], "match_type": r["match_type"],
                             "matched_notices": r["matched_notices"],
                             "latest_end": max(nsub["end"]), "row_ids": r["row_ids"]})
        ecols = ["supplier_norm", "published_names", "window_gbp", "annualised_gbp", "payments", "main_tag",
                 "match_type", "matched_notices", "latest_end", "row_ids"]
        ex = pd.DataFrame(rows, columns=ecols).sort_values("window_gbp", ascending=False)
        p_ex = FULL / "expired_notice_spend.csv"
        ex.to_csv(p_ex, index=False)
        top = ex.head(TOP).copy()
        top["row_ids"] = top["row_ids"].map(lambda s: s.split(";"))
        tests["expired_notice_spend"] = entry(
            th["rule_refs"]["extensions_app_c_row_d"],
            {"window_start": str(w_start.date()), "condition": "every exact-matched notice has an end date before "
                                                               "the window start (blank end date = not ended)"},
            {"items": int(len(ex)), "suppliers_with_exact_match": int(sup["match_type"].notna().sum())},
            round(float(ex["window_gbp"].sum()), 2), by_tag_from(ex, "main_tag", "window_gbp"),
            records(top, ecols), p_ex,
            ["A newer contract or an approved extension may exist that has no notice in the export.",
             "Applies to suppliers of any size that have an exact notice match."])

        # 7. spend_vs_award
        rows, skipped_years = [], 0
        considered = 0
        for _, r in sup[sup["match_type"].notna()].iterrows():
            nsub = ns.loc[r["_idx"]]
            live = nsub[nsub["live_in_window"]].drop_duplicates("notice_id")
            if len(live) != 1:
                continue
            n = live.iloc[0]
            if n["n_suppliers_on_notice"] != 1 or not (n["awarded_value"] > 0):
                continue
            considered += 1
            if not n["start"] or not n["end"]:
                skipped_years += 1
                continue
            yrs = (pd.Timestamp(n["end"]) - pd.Timestamp(n["start"])).days / 365.25
            if yrs <= 0:
                skipped_years += 1
                continue
            per_year = n["awarded_value"] / yrs
            ratio = r["annualised_gbp"] / per_year
            rows.append({"supplier_norm": r["supplier_norm"], "published_names": r["published_names"],
                         "notice_id": n["notice_id"], "awarded_value": round(float(n["awarded_value"]), 2),
                         "start": n["start"], "end": n["end"], "contract_years": round(yrs, 4),
                         "award_per_year": round(per_year, 2), "window_gbp": r["window_gbp"],
                         "annualised_gbp": r["annualised_gbp"], "ratio": round(ratio, 4),
                         "flag": ratio >= RATIO_FLAG, "main_tag": r["main_tag"], "row_ids": r["row_ids"]})
        scols = ["supplier_norm", "published_names", "notice_id", "awarded_value", "start", "end", "contract_years",
                 "award_per_year", "window_gbp", "annualised_gbp", "ratio", "flag", "main_tag", "row_ids"]
        sv = pd.DataFrame(rows, columns=scols).sort_values("ratio", ascending=False)
        p_sv = FULL / "spend_vs_award.csv"
        sv.to_csv(p_sv, index=False)
        fl = sv[sv["flag"]]
        top = fl.head(TOP).copy()
        top["row_ids"] = top["row_ids"].map(lambda s: s.split(";"))
        tests["spend_vs_award"] = entry(
            th["rule_refs"]["variations_app_c_row_e"],
            {"ratio_flag": RATIO_FLAG, "contract_years": "(end - start) days / 365.25",
             "ratio": f"{ANN_LABEL} / (Awarded Value / contract_years)",
             "population": "suppliers matched exactly to exactly one live notice with one supplier and "
                           "Awarded Value > 0"},
            {"items": int(len(fl)), "population": considered, "compared": int(len(sv)),
             "skipped_missing_or_nonpositive_years": skipped_years},
            round(float(fl["window_gbp"].sum()), 2), by_tag_from(fl, "main_tag", "window_gbp"),
            records(top, scols), p_sv,
            ["Award values may be estimates or maxima and may include VAT, while spend is net.",
             f"Spend is an {ANN_LABEL}; uneven timing of payments distorts the ratio.",
             "The full list includes unflagged comparisons for context."],
            annualised_gbp_total=round(float(fl["annualised_gbp"].sum()), 2))

    # ---------------------------------------------------------------------
    inputs = {"rules": {"path": "outputs/rules.json", "sha256": sha256(RULES)},
              "spend": [{"path": f["path"], "sha256": f["sha256"], "rows": f["rows_loaded"]} for f in clean["files"]],
              "contracts": ({"path": "data/contracts.csv", "sha256": csum["sha256"], "rows": csum["rows_raw"],
                             "used": True} if use_contracts else {"path": "data/contracts.csv", "used": False})}
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": inputs,
        "window": {"first_payment": str(w_start.date()), "last_payment": str(w_end.date()), "months": months,
                   "annualisation_factor": factor, "annualised_label": ANN_LABEL},
        "rules_used": th,
        "normalisation": {"steps": NORMALISATION_STEPS,
                          "aliases": "normalised name plus the parts either side of ' T A ' / ' TRADING AS ' "
                                     "(and ' TA ', since step 4 joins 'T A'); alias equality = match_type 'alias'"},
        "cleaning": clean,
        "contracts": csum,
        "tests": tests,
        "warnings": warnings,
        "language": LANGUAGE,
    }
    with open(ANALYTICS, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)

    print(f"window {w_start.date()}..{w_end.date()} months={months} factor={factor:g}")
    for k, t in tests.items():
        if t["status"] != "run":
            print(f"{k}: skipped ({t['reason']})")
            continue
        bt = max(t["by_tag"].items(), key=lambda x: x[1]["gbp"])[0] if t["by_tag"] else None
        print(f"{k}: items={t['counts']['items']} gbp_total={t['gbp_total']} largest_tag={bt}")
    if use_contracts:
        print("coverage:", tests["off_contract"]["coverage"])
    print(f"warnings: {len(warnings)}")


if __name__ == "__main__":
    sys.exit(main())
