"""
build_master_db.py
==================
Extracts, harmonises and merges the OAI raw files into the Master Feature Schema
defined in master_schema.py.

Produces:
    data/processed/master_db.csv   — one row per (patient, visit)
    data/processed/master_db_v00.csv — baseline visit only (V00)

Column Mapping (OAI raw → master schema):
──────────────────────────────────────────────────────────────────────────────
OAI SOURCE FILE         RAW COLUMN(S)                    → MASTER COLUMN
──────────────────────────────────────────────────────────────────────────────
oai_oarisk01            src_subject_id                   → patient_id
oai_oarisk01            ageyears                         → age
oai_oarisk01            sex   (M/F)                      → sex  (1/0)
oai_oarisk01            height_av   (mm → /10 cm)        → height
oai_oarisk01            weight_met  (kg)                 → weight
oai_oarisk01            bmi                              → bmi
oai_oarisk01            abcirc (cm)                      → waist
oai_oarisk01            injl / injr (any knee injury)    → previous_injury
oai_oarisk01            kinj / kninj (knee specific)     → injury_type
oai_oarisk01            ksurgl / ksurgr                  → surgery
oai_oarisk01            pa1/pa2/pa3 (PASE-like acts)     → physical_activity
oai_oarisk01            dayltmins (via accelsummary)     → sedentary_time
oai_oarisk01            oagrdl / oagrdr (K-L grade)      → oa_status
oai_charlson01          diab                             → diabetes
oai_charlson01          bpsys ≥ 140 or bpdias ≥ 90      → hypertension  [via oarisk]
oai_koos_womac01        womac_pain_left/right (avg)      → pain_score
oai_koos_womac01        womac_stiffness_left/right (avg) → morning_stiffness
oai_koos_womac01        koos_rksymptoms/lksymptoms       → swelling & crepitus
oai_oarisk01            lkeffb / rkeffb (effusion)       → swelling
oai_oarisk01            lkfhdeg / rkfhdeg (flexion deg)  → rom
oai_accelsummary01      daymvmins (mvpa minutes)         → physical_activity (fallback)
oai_accelsummary01      dayltmins (light activity min)   → sedentary_time (fallback)
──────────────────────────────────────────────────────────────────────────────
NOTE: gait columns (gait_speed, cadence, stride_time, stance_time, swing_time,
      gait_symmetry) come from the ESP32 sensor pipeline at runtime (edge_processing.py).
      They will be NaN for the historical OAI dataset and populated for live patients.
"""

import os
import sys
import pandas as pd
import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw", "OAI")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Add scripts dir to path so we can import master_schema
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from master_schema import MASTER_SCHEMA, SCHEMA_COLUMNS, FEATURE_GROUPS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_oai(fname: str, skiprows: list | None = None, **kwargs) -> pd.DataFrame:
    """Load a tab-separated OAI NDA file (header + description-row skipped)."""
    path = os.path.join(RAW_DIR, fname)
    if not os.path.exists(path):
        print(f"  [WARN] Missing file: {fname} — skipping.")
        return pd.DataFrame()
    skip = [1] if skiprows is None else skiprows  # row 1 is the description row in NDA files
    df = pd.read_csv(path, sep="\t", skiprows=skip, low_memory=False, on_bad_lines="skip", **kwargs)
    # Standardise ID
    for col in df.columns:
        if col.upper() == "SRC_SUBJECT_ID":
            df = df.rename(columns={col: "patient_id"})
            break
    return df


def _safe_mean(df: pd.DataFrame, cols: list) -> pd.Series:
    """Row-wise mean of `cols`, ignoring NaN. Returns NaN if all are NaN."""
    available = [c for c in cols if c in df.columns]
    if not available:
        return pd.Series(np.nan, index=df.index)
    return df[available].astype(float).mean(axis=1)


def _coerce_sex(series: pd.Series) -> pd.Series:
    """Map M→1, F→0; already numeric passes through."""
    return series.map({"M": 1, "F": 0}).fillna(series.apply(
        lambda x: 1 if str(x).strip().upper() == "M" else (0 if str(x).strip().upper() == "F" else np.nan)
    )).astype("Int8")


def _kl_to_oa_status(series: pd.Series) -> pd.Series:
    """K-L grade ≥ 2 → OA present (1), K-L 0-1 → No OA (0), missing → NaN."""
    s = pd.to_numeric(series, errors="coerce")
    return s.apply(lambda x: 1 if x >= 2 else (0 if x >= 0 else np.nan)).astype("Int8")


def _hypertension_flag(bpsys: pd.Series, bpdias: pd.Series) -> pd.Series:
    """Derive hypertension: SBP ≥ 140 OR DBP ≥ 90."""
    s = pd.to_numeric(bpsys, errors="coerce")
    d = pd.to_numeric(bpdias, errors="coerce")
    flag = ((s >= 140) | (d >= 90)).astype("Int8")
    flag[s.isna() & d.isna()] = pd.NA
    return flag


def _injury_type(df: pd.DataFrame) -> pd.Series:
    """
    Classify injury type from OAI columns:
      artl/artr  → 'ligament'
      menl/menr  → 'meniscal'
      injl/injr  → 'other'
      none       → None
    """
    result = pd.Series(None, index=df.index, dtype="object")
    for col_men, col_lig, col_gen, label in [
        ("menl", "artl", "injl", "left"),
        ("menr", "artr", "injr", "right"),
    ]:
        if col_men in df.columns:
            result = result.where(
                pd.to_numeric(df[col_men], errors="coerce").fillna(0) == 0,
                other="meniscal"
            )
        if col_lig in df.columns:
            result = result.where(
                pd.to_numeric(df[col_lig], errors="coerce").fillna(0) == 0,
                other="ligament"
            )
        if col_gen in df.columns:
            result = result.where(
                pd.to_numeric(df[col_gen], errors="coerce").fillna(0) == 0,
                other="other"
            )
    return result


# ── Main Build Function ───────────────────────────────────────────────────────

def build_master_db():
    print("=" * 60)
    print("Building Master Database from OAI")
    print("=" * 60)

    # ── 1. Load raw tables ────────────────────────────────────────────────────
    print("\n[1/6] Loading raw OAI files …")

    df_risk   = _load_oai("oai_oarisk01.txt")
    df_char   = _load_oai("oai_charlson01.txt")
    df_koos   = _load_oai("oai_koos_womac01.txt")
    df_accel  = _load_oai("oai_accelsummary01.txt")

    for name, df in [("oarisk01", df_risk), ("charlson01", df_char),
                     ("koos_womac01", df_koos), ("accelsummary01", df_accel)]:
        if df.empty:
            print(f"  [WARN] {name} is empty — some features will be NaN.")
        else:
            print(f"  Loaded {name}: {df.shape[0]:,} rows × {df.shape[1]} cols")

    # ── 2. Build visit-level base from oarisk01 ───────────────────────────────
    print("\n[2/6] Building base table from oarisk01 …")

    base_cols = {
        "patient_id" : "patient_id",
        "visit"      : "visit",
        "ageyears"   : "age",
        "sex"        : "_sex_raw",
        "height_av"  : "_height_mm",
        "weight_met" : "weight",
        "bmi"        : "bmi",
        "abcirc"     : "waist",
        "bpsys"      : "_bpsys",
        "bpdias"     : "_bpdias",
        # Physical activity
        "pa1"        : "_pa1",
        "pa2"        : "_pa2",
        "pa3"        : "_pa3",
        # Knee injury
        "injl"       : "_injl",
        "injr"       : "_injr",
        "kinj"       : "_kinj",
        "kninj"      : "_kninj",
        "menl"       : "_menl",
        "menr"       : "_menr",
        "artl"       : "_artl",
        "artr"       : "_artr",
        # Surgery
        "ksurgl"     : "_ksurgl",
        "ksurgr"     : "_ksurgr",
        # ROM / effusion
        "lkfhdeg"    : "_lkfhdeg",
        "rkfhdeg"    : "_rkfhdeg",
        "lkeffb"     : "_lkeffb",
        "rkeffb"     : "_rkeffb",
        # KL grade (OA status)
        "oagrdl"     : "_oagrdl",
        "oagrdr"     : "_oagrdr",
        # Occupation / work
        "curemp"     : "_curemp",
        "hourwk"     : "_hourwk",
        "weekwk"     : "_weekwk",
    }

    if df_risk.empty:
        print("  [ERROR] oarisk01 missing — cannot build master DB.")
        return

    available = {k: v for k, v in base_cols.items() if k in df_risk.columns}
    base = df_risk[list(available.keys())].rename(columns=available).copy()

    # ── 3. Harmonise base columns ─────────────────────────────────────────────
    print("[3/6] Harmonising demographic & clinical features …")

    # Sex
    base["sex"] = _coerce_sex(base["_sex_raw"])

    # Height: OAI stores height in mm → convert to cm
    base["height"] = pd.to_numeric(base["_height_mm"], errors="coerce") / 10.0

    # Recompute BMI if height or weight present but BMI is missing
    bmi_missing = base["bmi"].isna()
    h_m = base["height"] / 100.0
    base.loc[bmi_missing, "bmi"] = (
        pd.to_numeric(base.loc[bmi_missing, "weight"], errors="coerce")
        / (h_m[bmi_missing] ** 2)
    ).round(1)

    # Waist
    base["waist"] = pd.to_numeric(base["waist"], errors="coerce")

    # Hypertension
    base["hypertension"] = _hypertension_flag(base["_bpsys"], base["_bpdias"])

    # Previous injury
    inj_cols = ["_injl", "_injr", "_kinj", "_kninj", "_menl", "_menr"]
    inj_available = [c for c in inj_cols if c in base.columns]
    if inj_available:
        inj_any = base[inj_available].apply(pd.to_numeric, errors="coerce").clip(lower=0).max(axis=1)
        base["previous_injury"] = (inj_any > 0).astype("Int8")
        base.loc[inj_any.isna(), "previous_injury"] = pd.NA
    else:
        base["previous_injury"] = pd.NA

    # Injury type
    base["injury_type"] = _injury_type(base)

    # Surgery (any knee surgery)
    for col in ["_ksurgl", "_ksurgr"]:
        if col in base.columns:
            base[col] = pd.to_numeric(base[col], errors="coerce")
    surg_cols_avail = [c for c in ["_ksurgl", "_ksurgr"] if c in base.columns]
    if surg_cols_avail:
        surg_any = base[surg_cols_avail].max(axis=1)
        base["surgery"] = (surg_any > 0).astype("Int8")
        base.loc[surg_any.isna(), "surgery"] = pd.NA
    else:
        base["surgery"] = pd.NA

    # ROM — average of left/right flexion-extension degrees if available; clamp to [0, 180]
    raw_rom = _safe_mean(base, ["_lkfhdeg", "_rkfhdeg"])
    base["rom"] = raw_rom.clip(lower=0, upper=180)

    # Swelling — effusion from exam
    base["swelling"] = _safe_mean(base, ["_lkeffb", "_rkeffb"]).apply(
        lambda x: 1 if x > 0 else (0 if x == 0 else np.nan)
    ).astype("Int8")

    # OA status from K-L grade (worst knee)
    oagrd_left  = pd.to_numeric(base.get("_oagrdl", pd.Series(dtype=float)), errors="coerce")
    oagrd_right = pd.to_numeric(base.get("_oagrdr", pd.Series(dtype=float)), errors="coerce")
    worst_kl = oagrd_left.combine(oagrd_right, max)
    base["oa_status"] = _kl_to_oa_status(worst_kl)

    # Physical activity (simple presence flag → MET-like): count active PA types
    pa_cols_avail = [c for c in ["_pa1", "_pa2", "_pa3"] if c in base.columns]
    if pa_cols_avail:
        # OAI pa1-pa3 encode participation (0=no, 1-4=frequency). Convert to rough MET-min.
        # Frequency codes 1=<1/mo, 2=1-3/mo, 3=1-2/wk, 4=3+/wk → MET-min/wk ≈ freq * 30
        freq_to_met = {0: 0, 1: 15, 2: 45, 3: 180, 4: 540}
        pa_values = base[pa_cols_avail].apply(pd.to_numeric, errors="coerce")
        pa_met = pa_values.map(lambda x: freq_to_met.get(int(x), np.nan) if pd.notna(x) else np.nan)
        base["physical_activity"] = pa_met.sum(axis=1, min_count=1)
    else:
        base["physical_activity"] = np.nan

    # Occupation: map curemp → sedentary/light/moderate/heavy using hourwk/weekwk
    if "_curemp" in base.columns:
        base["occupation"] = base["_curemp"].apply(
            lambda x: "employed" if pd.notna(x) and x == 1 else ("unemployed" if pd.notna(x) else None)
        )
    else:
        base["occupation"] = None

    # Placeholder gait columns (will be populated by ESP32 pipeline)
    for g_col in FEATURE_GROUPS["gait"]:
        base[g_col] = np.nan

    # Placeholder for features coming from other tables
    for col in ["muscle_strength", "crepitus", "pain_score", "morning_stiffness",
                "diabetes", "sedentary_time", "progression_status"]:
        if col not in base.columns:
            base[col] = np.nan

    # ── 4. Merge charlson01 (diabetes, comorbidities) ─────────────────────────
    print("[4/6] Merging charlson01 (diabetes, comorbidities) …")

    if not df_char.empty and "patient_id" in df_char.columns:
        char_keep = ["patient_id", "visit"]
        if "diab" in df_char.columns:
            char_keep.append("diab")
        char = df_char[char_keep].copy()

        # Merge on patient_id + visit
        base = base.merge(char, on=["patient_id", "visit"], how="left", suffixes=("", "_char"))

        if "diab" in base.columns:
            base["diabetes"] = pd.to_numeric(base["diab"], errors="coerce").astype("Int8")
        else:
            base["diabetes"] = pd.NA
    else:
        print("  [WARN] charlson01 unavailable or missing patient_id — diabetes set to NaN.")

    # ── 5. Merge koos_womac01 (pain, stiffness, symptoms) ────────────────────
    print("[5/6] Merging koos_womac01 (pain, stiffness, symptoms) …")

    if not df_koos.empty and "patient_id" in df_koos.columns:
        koos_keep = ["patient_id", "visit"]
        pain_raw    = [c for c in ["womac_pain_left","womac_pain_right"] if c in df_koos.columns]
        stiff_raw   = [c for c in ["womac_stiffness_left","womac_stiffness_right"] if c in df_koos.columns]
        sym_raw     = [c for c in ["koos_rksymptoms","koos_lksymptoms"] if c in df_koos.columns]

        koos_keep += pain_raw + stiff_raw + sym_raw
        koos = df_koos[koos_keep].copy()

        base = base.merge(koos, on=["patient_id", "visit"], how="left", suffixes=("", "_koos"))

        # Pain score: WOMAC raw 0-20 → normalise to 0-100
        if pain_raw:
            raw_pain = base[pain_raw].apply(pd.to_numeric, errors="coerce").mean(axis=1)
            base["pain_score"] = (raw_pain / 20.0 * 100).round(1)

        # Morning stiffness: WOMAC stiffness 0-8 → normalise to 0-100
        if stiff_raw:
            raw_stiff = base[stiff_raw].apply(pd.to_numeric, errors="coerce").mean(axis=1)
            base["morning_stiffness"] = (raw_stiff / 8.0 * 100).round(1)

        # Crepitus / swelling from KOOS symptoms (low score = more symptoms)
        if sym_raw:
            sym_score = base[sym_raw].apply(pd.to_numeric, errors="coerce").mean(axis=1)
            # Threshold: KOOS symptoms < 60 indicates significant symptoms
            base.loc[base["swelling"].isna(), "swelling"] = (sym_score < 60).astype("Int8")
    else:
        print("  [WARN] koos_womac01 unavailable — pain/stiffness set to NaN.")

    # ── 5b. Merge accelsummary01 (sedentary time, physical activity refinement) ─
    if not df_accel.empty and "patient_id" in df_accel.columns:
        accel_keep = ["patient_id", "visit"]
        if "dayltmins" in df_accel.columns:
            accel_keep.append("dayltmins")   # light-activity minutes/day ≈ sedentary proxy
        if "daymvmins" in df_accel.columns:
            accel_keep.append("daymvmins")   # moderate-vigorous minutes/day

        accel = df_accel[accel_keep].copy()
        base = base.merge(accel, on=["patient_id", "visit"], how="left", suffixes=("", "_accel"))

        if "dayltmins" in base.columns:
            base["sedentary_time"] = pd.to_numeric(base["dayltmins"], errors="coerce") / 60.0  # → hours/day

        if "daymvmins" in base.columns:
            mvpa = pd.to_numeric(base["daymvmins"], errors="coerce") * 7 * 3.5  # MET-min/week
            # Fill PA from accelerometer where pa columns missing
            pa_missing = base["physical_activity"].isna()
            base.loc[pa_missing, "physical_activity"] = mvpa[pa_missing]

    # ── 6. Select & order final columns ──────────────────────────────────────
    print("[6/6] Finalising master schema columns …")

    # Build the final DataFrame with exactly the master schema columns
    final_cols = SCHEMA_COLUMNS  # defined in master_schema.py
    master_df = pd.DataFrame(index=base.index)

    for col in final_cols:
        if col in base.columns:
            master_df[col] = base[col]
        else:
            master_df[col] = np.nan  # gracefully fill missing features

    # Cast dtypes
    for col, meta in MASTER_SCHEMA.items():
        if col not in master_df.columns:
            continue
        dtype = meta["dtype"]
        try:
            if dtype == "str":
                master_df[col] = master_df[col].astype(str).replace("nan", None).replace("<NA>", None)
            elif dtype in ("int8", "Int8"):
                master_df[col] = pd.to_numeric(master_df[col], errors="coerce").astype("Int8")
            elif dtype in ("float32",):
                master_df[col] = pd.to_numeric(master_df[col], errors="coerce").astype("float32")
        except Exception:
            pass

    # Drop rows missing BOTH oa_status AND patient_id
    master_df = master_df.dropna(subset=["patient_id"])

    print(f"\n  Final master DB shape: {master_df.shape[0]:,} rows × {master_df.shape[1]} cols")

    # ── Save ──────────────────────────────────────────────────────────────────
    out_all = os.path.join(PROCESSED_DIR, "master_db.csv")
    master_df.to_csv(out_all, index=False)
    print(f"  Saved -> {out_all}")

    # Baseline (V00) subset
    if "visit" in base.columns:
        v00_mask = base["visit"].str.strip().str.upper() == "V00"
        master_v00 = master_df.loc[v00_mask.values if len(v00_mask) == len(master_df) else master_df.index]
        out_v00 = os.path.join(PROCESSED_DIR, "master_db_v00.csv")
        master_v00.to_csv(out_v00, index=False)
        print(f"  Saved V00 baseline -> {out_v00}  ({master_v00.shape[0]:,} patients)")

    # -- Summary statistics ----------------------------------------------------------------
    print("\n-- Column Completeness Report --")
    for col in final_cols:
        n_valid = master_df[col].notna().sum()
        pct = n_valid / len(master_df) * 100 if len(master_df) > 0 else 0
        filled = int(pct / 10)
        bar = "#" * filled + "." * (10 - filled)
        print(f"  {col:<26} [{bar}] {pct:5.1f}%  ({n_valid:,}/{len(master_df):,})")

    print("\n[Done] Master database built successfully.")
    return master_df


if __name__ == "__main__":
    build_master_db()
