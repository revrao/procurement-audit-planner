"""Parse the raw Contracts Finder export (data/contracts.csv).

Outputs (outputs/analytics-full/): notice_suppliers.csv, contracts_summary.json
Prints short aggregates only. Run only if data/contracts.csv exists.
"""
import json
import sys
from datetime import datetime

import pandas as pd

from common import (CLEAN_SUMMARY, CONTRACTS_CSV, CONTRACTS_SUMMARY, NOTICE_SUPPLIERS, aliases,
                    ensure_full_dir, normalise, sha256)

SUPPLIER_COL = "Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]"
NEEDED = ["Notice Identifier", "Organisation Name", "Published Date", "Contract start date",
          "Contract end date", "Awarded Value", SUPPLIER_COL]
COUNCIL_NAMES = {"west berkshire council", "west berkshire"}
DMY = "%d/%m/%Y"
ISO_DAY = "%Y-%m-%d"
CAP_ROWS = 1000


def stop(msg):
    print(f"STOP: {msg}")
    sys.exit(2)


def parse_fmt(v, fmt, what, notice):
    if v is None or pd.isna(v) or str(v).strip() == "":
        return pd.NaT
    try:
        return pd.Timestamp(datetime.strptime(str(v).strip(), fmt))
    except ValueError:
        stop(f"contracts.csv notice {notice}: {what} {v!r} not parseable with {fmt}")


def split_blocks(packed):
    if packed is None or pd.isna(packed) or str(packed).strip() == "":
        return []
    s = str(packed).strip()
    if s.startswith("["):
        s = s[1:]
    if s.endswith("]"):
        s = s[:-1]
    return s.split("][")


def main():
    if not CONTRACTS_CSV.exists():
        print("contracts.csv not present: nothing to do")
        return
    ensure_full_dir()
    raw = pd.read_csv(CONTRACTS_CSV, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = [c for c in NEEDED if c not in raw.columns]
    if missing:
        stop(f"data/contracts.csv missing expected columns {missing}")
    warnings = []
    n_raw = len(raw)
    if n_raw >= CAP_ROWS:
        warnings.append(f"contracts.csv has {n_raw} rows (>= {CAP_ROWS}): the export may have hit the "
                        f"Contracts Finder download cap")

    org = raw["Organisation Name"].str.strip().str.lower()
    keep = org.isin(COUNCIL_NAMES)
    dropped = raw[~keep]
    dropped_buyers = dropped["Organisation Name"].str.strip().value_counts().to_dict()
    case_variants = raw.loc[keep, "Organisation Name"].str.strip().value_counts().to_dict()
    notices = raw[keep].copy()
    dup_ids = int(notices["Notice Identifier"].duplicated().sum())
    if dup_ids:
        warnings.append(f"{dup_ids} duplicate Notice Identifier rows among council notices "
                        f"(e.g. 'West Berkshire Council' and 'West Berkshire' exports overlapping); "
                        f"kept once per (notice, supplier)")

    clean = json.load(open(CLEAN_SUMMARY, encoding="utf-8"))
    w_start = pd.Timestamp(clean["window"]["first_payment"])
    w_end = pd.Timestamp(clean["window"]["last_payment"])

    rows, bad_blocks, no_supplier = [], 0, 0
    pub_dates = []
    for _, r in notices.iterrows():
        nid = r["Notice Identifier"].strip()
        pub = parse_fmt(r["Published Date"][:10], ISO_DAY, "Published Date", nid)
        pub_dates.append(pub)
        start = parse_fmt(r["Contract start date"], DMY, "Contract start date", nid)
        end = parse_fmt(r["Contract end date"], DMY, "Contract end date", nid)
        av = pd.to_numeric(r["Awarded Value"].replace(",", ""), errors="coerce") if r["Awarded Value"] else float("nan")
        blocks = split_blocks(r[SUPPLIER_COL])
        if not blocks:
            no_supplier += 1
        for b in blocks:
            parts = b.split("|")
            if len(parts) != 6:
                bad_blocks += 1
            name = parts[0].strip()
            ref_type = parts[2].strip() if len(parts) > 2 else ""
            ref_no = parts[3].strip() if len(parts) > 3 else ""
            norm = normalise(name)
            rows.append({
                "notice_id": nid,
                "supplier_name": name,
                "supplier_norm": norm,
                "aliases": "|".join(aliases(norm)),
                "companies_house": ref_no if ref_type == "COMPANIES_HOUSE" else "",
                "awarded_value": av,
                "published": pub.date() if pd.notna(pub) else None,
                "start": start.date() if pd.notna(start) else None,
                "end": end.date() if pd.notna(end) else None,
                "live_in_window": bool(pd.notna(start) and start <= w_end and (pd.isna(end) or end >= w_start))
                                  if pd.notna(start) else bool(pd.isna(end) or end >= w_start),
                "ended_before_window": bool(pd.notna(end) and end < w_start),
            })
    ns = pd.DataFrame(rows).drop_duplicates(subset=["notice_id", "supplier_norm"])
    n_sup = ns.groupby("notice_id")["supplier_norm"].transform("size")
    ns["n_suppliers_on_notice"] = n_sup
    if bad_blocks:
        warnings.append(f"{bad_blocks} supplier blocks did not have exactly 6 pipe-separated fields; "
                        f"name taken from the first field")
    n_no_start = int(notices["Contract start date"].str.strip().eq("").sum())
    if n_no_start:
        warnings.append(f"{n_no_start} council notices have no Contract start date; live_in_window "
                        f"then uses the end date only")

    # year completeness
    pubs = pd.Series(pub_dates).dropna()
    by_year = pubs.dt.year.value_counts().sort_index()
    full_years = [y for y in by_year.index if pubs.min() <= pd.Timestamp(y, 1, 1)
                  and pd.Timestamp(y, 12, 31) <= pubs.max()]
    if full_years:
        med = float(by_year.loc[full_years].median())
        for y in full_years:
            if by_year.loc[y] < med / 4:
                warnings.append(f"published year {y} has {int(by_year.loc[y])} notices, under a quarter of the "
                                f"median full year ({med:g}): possibly incomplete")
    far = int((ns.drop_duplicates("notice_id")["end"].dropna()
               .map(lambda d: pd.Timestamp(d) > w_end + pd.DateOffset(years=20))).sum())
    if far:
        warnings.append(f"{far} notices have an end date more than 20 years out")

    ns.to_csv(NOTICE_SUPPLIERS, index=False)
    per_notice = ns.drop_duplicates("notice_id")
    summary = {
        "file": "data/contracts.csv",
        "sha256": sha256(CONTRACTS_CSV),
        "rows_raw": n_raw,
        "rows_kept_council": int(keep.sum()),
        "rows_dropped_other_buyers": int((~keep).sum()),
        "dropped_buyers": dropped_buyers,
        "kept_buyer_name_variants": case_variants,
        "council_filter": "Organisation Name trimmed and lower-cased in {'west berkshire council', 'west berkshire'}",
        "notices_without_supplier": no_supplier,
        "notice_supplier_rows": int(len(ns)),
        "distinct_notices_with_supplier": int(ns["notice_id"].nunique()),
        "distinct_supplier_names": int(ns["supplier_norm"].nunique()),
        "with_companies_house": int((ns["companies_house"] != "").sum()),
        "join_note": "The spend data has no company number, so notice-to-spend joins are by normalised name "
                     "(and trading-as aliases) only; Companies House numbers are retained for the auditor.",
        "published_range": [str(pubs.min().date()), str(pubs.max().date())],
        "notices_by_published_year": {int(k): int(v) for k, v in by_year.items()},
        "window": {"start": str(w_start.date()), "end": str(w_end.date())},
        "notices_live_in_window": int(per_notice["live_in_window"].sum()),
        "notices_ended_before_window": int(per_notice["ended_before_window"].sum()),
        "notices_awarded_value_zero": int((per_notice["awarded_value"].fillna(0) == 0).sum()),
        "date_formats": {"Contract start/end date": DMY, "Published Date": "first 10 chars as " + ISO_DAY},
        "full_list": "outputs/analytics-full/notice_suppliers.csv",
        "warnings": warnings,
    }
    with open(CONTRACTS_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, default=str)
    for k in ["rows_raw", "rows_kept_council", "rows_dropped_other_buyers", "dropped_buyers",
              "kept_buyer_name_variants", "notices_without_supplier", "notice_supplier_rows",
              "distinct_notices_with_supplier", "distinct_supplier_names", "with_companies_house",
              "published_range", "notices_by_published_year", "notices_live_in_window",
              "notices_ended_before_window", "notices_awarded_value_zero"]:
        print(f"{k}: {summary[k]}")
    for w in warnings:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
