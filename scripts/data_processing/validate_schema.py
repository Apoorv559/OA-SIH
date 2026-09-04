"""
validate_schema.py
==================
Validates any DataFrame against the Master Feature Schema.
Run standalone or import as a library function.

Usage:
    python validate_schema.py data/processed/master_db.csv
"""

import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from master_schema import MASTER_SCHEMA, SCHEMA_COLUMNS, REQUIRED_COLUMNS, FEATURE_GROUPS


def validate(df: pd.DataFrame, strict: bool = False) -> dict:
    """
    Validate ``df`` against the master schema.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to validate. Must contain at least the required columns.
    strict : bool
        If True, raise ValueError on any violation. If False, return a report dict.

    Returns
    -------
    dict with keys:
        'passed'   : bool
        'errors'   : list of str
        'warnings' : list of str
        'stats'    : dict  col -> {'pct_fill': float, 'out_of_range': int}
    """
    errors = []
    warnings = []
    stats = {}

    # 1. Check required columns exist
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            errors.append(f"MISSING REQUIRED column: '{col}'")
        elif df[col].isna().all():
            errors.append(f"REQUIRED column '{col}' is entirely NaN")

    # 2. Check all schema columns present (warn if optional ones are missing)
    for col in SCHEMA_COLUMNS:
        if col not in df.columns:
            if col in REQUIRED_COLUMNS:
                pass  # already an error
            else:
                warnings.append(f"Optional column missing: '{col}'")
            continue

        series = df[col]
        meta = MASTER_SCHEMA[col]
        n = len(df)
        n_valid = series.notna().sum()
        pct_fill = n_valid / n * 100 if n > 0 else 0
        col_stats: dict = {"pct_fill": round(pct_fill, 1), "out_of_range": 0}

        # 3. Range checks
        if "range" in meta:
            lo, hi = meta["range"]
            numeric = pd.to_numeric(series, errors="coerce")
            out_of_range = ((numeric < lo) | (numeric > hi)).sum()
            col_stats["out_of_range"] = int(out_of_range)
            if out_of_range > 0:
                warnings.append(
                    f"Column '{col}': {out_of_range} values outside expected range "
                    f"[{lo}, {hi}]"
                )

        # 4. Allowed value checks (categorical)
        if "values" in meta:
            allowed = set(meta["values"].keys())
            bad = series.dropna().apply(lambda x: x not in allowed).sum()
            col_stats["bad_categories"] = int(bad)
            if bad > 0:
                warnings.append(
                    f"Column '{col}': {bad} values not in allowed set {allowed}"
                )

        stats[col] = col_stats

    # 5. Duplicate patient check
    if "patient_id" in df.columns and "visit" in df.columns:
        dupes = df.duplicated(subset=["patient_id", "visit"]).sum()
        if dupes:
            warnings.append(f"{dupes} duplicate (patient_id, visit) pairs found")
    elif "patient_id" in df.columns:
        dupes = df.duplicated(subset=["patient_id"]).sum()
        if dupes:
            warnings.append(f"{dupes} duplicate patient_id values found")

    result = {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }

    if strict and not result["passed"]:
        raise ValueError("Schema validation failed:\n" + "\n".join(errors))

    return result


def print_report(report: dict, df: pd.DataFrame):
    """Pretty-print the validation report."""
    status = "PASS" if report["passed"] else "FAIL"
    print(f"\n=== Schema Validation: {status} ===")
    print(f"    Rows: {len(df):,}   Columns: {len(df.columns)}")

    if report["errors"]:
        print(f"\n[ERRORS] ({len(report['errors'])})")
        for e in report["errors"]:
            print(f"  X  {e}")

    if report["warnings"]:
        print(f"\n[WARNINGS] ({len(report['warnings'])})")
        for w in report["warnings"]:
            print(f"  !  {w}")

    print("\n[COLUMN FILL RATES]")
    for group_name, cols in FEATURE_GROUPS.items():
        print(f"  -- {group_name.upper()} --")
        for col in cols:
            if col in report["stats"]:
                s = report["stats"][col]
                pct = s["pct_fill"]
                filled = int(pct / 10)
                bar = "#" * filled + "." * (10 - filled)
                oor = f"  [{s['out_of_range']} out-of-range]" if s.get("out_of_range", 0) > 0 else ""
                print(f"    {col:<26} [{bar}] {pct:5.1f}%{oor}")
            else:
                print(f"    {col:<26} [MISSING]")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_schema.py <path_to_csv>")
        sys.exit(1)

    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path, low_memory=False)
    report = validate(df)
    print_report(report, df)
    sys.exit(0 if report["passed"] else 1)
