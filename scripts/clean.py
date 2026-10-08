"""Clean the monthly 'Expenditure over £500' workbooks.

Outputs (outputs/analytics-full/): spend_clean.csv, exclusions.csv, clean_summary.json
Prints short aggregates only.
"""
import json
import re
import sys
from datetime import datetime

import pandas as pd

from common import (load_thresholds, CLEAN_SUMMARY, EXCLUSIONS, REQUIRED_COLS, SHEET, SPEND_CLEAN,
                    SPEND_DIR, TEXT_DATE_FORMAT, ensure_full_dir, normalise, sha256)


def stop(msg):
    print(f"STOP: {msg}")
    sys.exit(2)


def find_header(raw):
    for i in range(min(10, len(raw))):
        vals = {str(v).strip() for v in raw.iloc[i].tolist() if pd.notna(v)}
        if all(c in vals for c in REQUIRED_COLS):
            return i
    return None


def implied_month(stem):
    """Fiscal period Pnn of year YYYY -> calendar (year, month); P01 = April."""
    m = re.search(r"(\d{4})_P(\d{2})", stem)
    if not m:
        return None
    fy, p = int(m.group(1)), int(m.group(2))
    month = (p - 1 + 3) % 12 + 1
    year = fy + (1 if p >= 10 else 0)
    return year, month


def parse_dates(series, fname, warnings):
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series)
    out = []
    n_text = 0
    for v in series:
        if isinstance(v, (datetime, pd.Timestamp)):
            out.append(pd.Timestamp(v))
        elif pd.isna(v):
            out.append(pd.NaT)
        else:
            n_text += 1
            try:
                out.append(pd.Timestamp(datetime.strptime(str(v).strip(), TEXT_DATE_FORMAT)))
            except ValueError:
                stop(f"{fname}: date value not parseable with {TEXT_DATE_FORMAT}: {v!r}")
    if n_text:
        warnings.append(f"{fname}: {n_text} dates arrived as text and were parsed as {TEXT_DATE_FORMAT}")
    return pd.Series(out, index=series.index)


TAG_RULES = {
    "placement": "Service starts with 'Adult Social Care' or \"Children's Social Care\" and Narrative in "
                 "{Private Contractors, Private Contractors Additional Cost, Payment to contractor}; or Service is "
                 "'Education & SEND' or starts with 'Education (DSG' and Narrative in {Other agencies, Private "
                 "Contractors, Payment to contractor}",
    "grant": "Narrative in {Grants, Voluntary Associations}",
    "agency_staff": "Narrative is 'Agency & Temporary Staff'",
    "premises": "Expenditure category is 'Premises'",
    "general_procurement": "everything else",
    "order": "first match wins, in the order above",
}
EXCLUSION_RULES = {
    "redacted_supplier": "Supplier name is 'Redacted' (ignoring case and spaces)",
    "pension_statutory": "Narrative contains 'LGPS', 'AVC' or 'Control', or is 'Council Tax Court Orders'; "
                         "or Expenditure category is 'Transfer Payment'",
    "public_body": "Narrative is one of the joint-arrangement / NHS / other-local-authority narratives; or the "
                   "normalised supplier matches \\b(COUNCIL|BOROUGH|NHS|HMRC|HM REVENUE|POLICE|FIRE AND RESCUE|"
                   "INTEGRATED CARE BOARD)\\b",
    "grants_never_excluded": "a row tagged 'grant' is kept even if it matches public_body (clause 1.6.2)",
    "order": "first matching reason wins: redacted_supplier, pension_statutory, public_body",
}
PUBLIC_NARR = {
    "Joint Arrangements (with Other Local Authorities or NHS)",
    "Payments to NHS (excl Joint Arrangement)",
    "Payments to Other Local Authorities (excl Joint Arrangements)",
}
PUBLIC_RE = re.compile(r"\b(COUNCIL|BOROUGH|NHS|HMRC|HM REVENUE|POLICE|FIRE AND RESCUE|INTEGRATED CARE BOARD)\b")


def s(x):
    return "" if pd.isna(x) else str(x).strip()


def tag_row(service, narrative, category):
    if (service.startswith("Adult Social Care") or service.startswith("Children's Social Care")) and \
            narrative in {"Private Contractors", "Private Contractors Additional Cost", "Payment to contractor"}:
        return "placement"
    if (service == "Education & SEND" or service.startswith("Education (DSG")) and \
            narrative in {"Other agencies", "Private Contractors", "Payment to contractor"}:
        return "placement"
    if narrative in {"Grants", "Voluntary Associations"}:
        return "grant"
    if narrative == "Agency & Temporary Staff":
        return "agency_staff"
    if category == "Premises":
        return "premises"
    return "general_procurement"


def exclusion_reason(supplier, supplier_norm, narrative, category, tag):
    if re.sub(r"\s+", "", supplier).lower() == "redacted":
        return "redacted_supplier", None
    if ("LGPS" in narrative or "AVC" in narrative or "Control" in narrative
            or narrative == "Council Tax Court Orders" or category == "Transfer Payment"):
        return "pension_statutory", None
    if tag != "grant":
        if narrative in PUBLIC_NARR:
            return "public_body", "narrative"
        if PUBLIC_RE.search(supplier_norm):
            return "public_body", "supplier_regex"
    return None, None


def main():
    ensure_full_dir()
    files = sorted(SPEND_DIR.glob("*.xlsx"))
    files = [f for f in files if not f.name.startswith("~$")]
    if not files:
        stop("no workbooks found in data/spend/")
    warnings, frames, per_file = [], [], []
    for f in files:
        try:
            raw = pd.read_excel(f, sheet_name=SHEET, header=None)
        except ValueError as e:
            stop(f"{f.name}: cannot read sheet '{SHEET}': {e}")
        h = find_header(raw)
        if h is None:
            present = {str(v).strip() for i in range(min(10, len(raw))) for v in raw.iloc[i] if pd.notna(v)}
            missing = [c for c in REQUIRED_COLS if c not in present]
            stop(f"{f.name}: no header row in first 10 rows; missing columns {missing}")
        header = [s(v) for v in raw.iloc[h].tolist()]
        body = raw.iloc[h + 1:].copy()
        body.columns = header
        missing = [c for c in REQUIRED_COLS if c not in body.columns]
        if missing:
            stop(f"{f.name}: missing columns {missing}")
        body = body[REQUIRED_COLS].copy()
        body["excel_row"] = [h + 1 + 1 + i for i in range(len(body))]  # header Excel row = h+1
        blank = body[REQUIRED_COLS].isna().all(axis=1)
        if blank.any():
            warnings.append(f"{f.name}: {int(blank.sum())} fully blank rows skipped")
        body = body[~blank]
        stem = f.stem
        body["row_id"] = stem + ":" + body["excel_row"].astype(str)
        body["month_file"] = stem
        body["Date"] = parse_dates(body["Date"], f.name, warnings)
        if body["Date"].isna().any():
            stop(f"{f.name}: {int(body['Date'].isna().sum())} rows with no date")
        body["date"] = body["Date"].dt.normalize()
        body["Net amount"] = pd.to_numeric(body["Net amount"], errors="coerce")
        if body["Net amount"].isna().any():
            stop(f"{f.name}: {int(body['Net amount'].isna().sum())} rows with non-numeric Net amount")
        n_low = int((body["Net amount"] < 500).sum())
        if n_low:
            warnings.append(f"{f.name}: {n_low} rows with Net amount below 500 (expected none)")
        im = implied_month(stem)
        if im:
            start = pd.Timestamp(year=im[0], month=im[1], day=1)
            end = start + pd.offsets.MonthEnd(0)
            out = body[(body["date"] < start - pd.Timedelta(days=7)) | (body["date"] > end + pd.Timedelta(days=7))]
            if len(out):
                warnings.append(f"{f.name}: {len(out)} dates fall more than 7 days outside implied month "
                                f"{im[0]}-{im[1]:02d}")
        else:
            warnings.append(f"{f.name}: cannot infer month from file name")
        n_blank_cat = int(body["Expenditure category"].isna().sum())
        per_file.append({"file": f.name, "path": str(f.relative_to(f.parents[2])), "sha256": sha256(f),
                         "header_excel_row": h + 1, "rows_loaded": len(body),
                         "blank_expenditure_category": n_blank_cat,
                         "implied_month": f"{im[0]}-{im[1]:02d}" if im else None})
        frames.append(body)

    df = pd.concat(frames, ignore_index=True)
    for c in ["Service", "Expenditure category", "Narrative", "Supplier name"]:
        df[c] = df[c].map(s)
    df["supplier_norm"] = df["Supplier name"].map(normalise)
    df["tag"] = [tag_row(a, b, c) for a, b, c in zip(df["Service"], df["Narrative"], df["Expenditure category"])]
    res = [exclusion_reason(a, b, c, d, e) for a, b, c, d, e in
           zip(df["Supplier name"], df["supplier_norm"], df["Narrative"], df["Expenditure category"], df["tag"])]
    df["exclusion"] = [r[0] for r in res]
    df["exclusion_via"] = [r[1] for r in res]

    # grants kept despite matching public_body
    grant_public = 0
    for a, b, c in zip(df["tag"], df["Narrative"], df["supplier_norm"]):
        if a == "grant" and (b in PUBLIC_NARR or PUBLIC_RE.search(c)):
            grant_public += 1

    # expectation checks (agent spec): report differences, never adapt silently
    qt = load_thresholds()["quote_threshold"]["value"]
    red = df[df["exclusion"] == "redacted_supplier"]
    expectations = {}
    for pf in per_file:
        stem = pf["file"].rsplit(".", 1)[0]
        r = red[red["month_file"] == stem]
        expectations[pf["file"]] = {"rows": pf["rows_loaded"], "redacted_rows": int(len(r)),
                                    "blank_category": pf["blank_expenditure_category"]}
        if not (2900 * 0.9 <= pf["rows_loaded"] <= 4200 * 1.1):
            warnings.append(f"{pf['file']}: {pf['rows_loaded']} rows, outside expected ~2,900-4,200")
        if not (600 * 0.8 <= len(r) <= 800 * 1.2):
            warnings.append(f"{pf['file']}: {len(r)} redacted rows, outside expected ~600-800")
        if not (29 * 0.5 <= pf["blank_expenditure_category"] <= 29 * 1.5):
            warnings.append(f"{pf['file']}: {pf['blank_expenditure_category']} blank categories, expected ~29")
    share_tp = float((red["Expenditure category"] == "Transfer Payment").mean()) if len(red) else 0.0
    n_red_big = int((red["Net amount"] >= qt).sum())
    expectations["redacted_share_transfer_payment"] = round(share_tp, 4)
    expectations["redacted_rows_at_or_above_quote_threshold"] = n_red_big
    if share_tp < 0.9:
        warnings.append(f"redacted rows: only {share_tp:.1%} are Transfer Payments (expected ~96%)")
    if n_red_big:
        warnings.append(f"redacted rows: {n_red_big} at or above quote_threshold (expected none)")

    excl = df[df["exclusion"].notna()]
    kept = df[df["exclusion"].isna()].copy()

    # identical rows (all six source columns equal), across or within files
    key = df[REQUIRED_COLS].astype(str).agg("␟".join, axis=1)
    dup_mask = key.duplicated(keep=False)
    ident_groups = df[dup_mask].groupby(key[dup_mask])["row_id"].apply(list).tolist()

    out_cols = ["row_id", "month_file", "excel_row", "Service", "Expenditure category", "Narrative", "Date",
                "date", "Net amount", "Supplier name", "supplier_norm", "tag"]
    kept[out_cols].to_csv(SPEND_CLEAN, index=False)
    excl[["row_id", "exclusion", "exclusion_via", "Supplier name", "Narrative", "Net amount"]].rename(
        columns={"exclusion": "reason"}).to_csv(EXCLUSIONS, index=False)

    for pf in per_file:
        m = df["month_file"] == pf["file"].rsplit(".", 1)[0]
        pf["rows_excluded"] = int((m & df["exclusion"].notna()).sum())
        pf["rows_kept"] = int((m & df["exclusion"].isna()).sum())

    by_reason = {r: {"rows": int(len(g)), "gbp": round(float(g["Net amount"].sum()), 2)}
                 for r, g in excl.groupby("exclusion")}
    by_tag = {t: {"rows": int(len(g)), "gbp": round(float(g["Net amount"].sum()), 2)}
              for t, g in kept.groupby("tag")}
    regex_hits = excl[excl["exclusion_via"] == "supplier_regex"]
    regex_suppliers = (regex_hits.groupby("Supplier name").size().sort_values(ascending=False)
                       .reset_index().rename(columns={0: "rows"}).to_dict("records"))
    gp = kept[kept["tag"] == "general_procurement"].groupby("Narrative")["Net amount"].agg(["size", "sum"])
    gp = gp.sort_values("sum", ascending=False)

    summary = {
        "files": per_file,
        "rows_loaded": int(len(df)),
        "rows_excluded": int(len(excl)),
        "rows_kept": int(len(kept)),
        "gbp_loaded": round(float(df["Net amount"].sum()), 2),
        "gbp_kept": round(float(kept["Net amount"].sum()), 2),
        "exclusion_rules": EXCLUSION_RULES,
        "exclusions_by_reason": by_reason,
        "grants_kept_despite_public_body_match": grant_public,
        "public_body_supplier_regex_hits": regex_suppliers,
        "tag_rules": TAG_RULES,
        "tags": by_tag,
        "blank_expenditure_category_kept_rows": int((kept["Expenditure category"] == "").sum()),
        "general_procurement_narratives": [
            {"narrative": n, "rows": int(r["size"]), "gbp": round(float(r["sum"]), 2)} for n, r in gp.iterrows()],
        "identical_rows": {"count_rows": int(dup_mask.sum()), "groups": len(ident_groups),
                           "row_ids": ident_groups},
        "window": {"first_payment": str(kept["date"].min().date()), "last_payment": str(kept["date"].max().date()),
                   "first_payment_all_rows": str(df["date"].min().date()),
                   "last_payment_all_rows": str(df["date"].max().date()),
                   "months": len(files)},
        "full_files": {"spend_clean": "outputs/analytics-full/spend_clean.csv",
                       "exclusions": "outputs/analytics-full/exclusions.csv"},
        "expectation_checks": expectations,
        "warnings": warnings,
    }
    with open(CLEAN_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, default=str)

    print(f"files: {[(p['file'], p['header_excel_row'], p['rows_loaded']) for p in per_file]}")
    print(f"rows loaded {len(df)}, excluded {len(excl)}, kept {len(kept)}")
    print("exclusions:", by_reason)
    print("tags:", by_tag)
    print(f"grants kept despite public_body match: {grant_public}")
    print(f"public_body supplier-regex distinct suppliers: {len(regex_suppliers)}")
    print("general_procurement narratives (top 15 by £):")
    print(gp.head(15).to_string())
    print(f"identical rows: {int(dup_mask.sum())} in {len(ident_groups)} groups")
    print("window:", summary["window"])
    print("expectations:", expectations)
    for w in warnings:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
