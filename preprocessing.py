"""
preprocessing.py - Data ingestion, cleaning, scale scoring, and preprocessing pipeline.
All internal variables, intermediate DataFrames, and functions use standard English naming.

Caching layout
--------------
preprocess_data(raw_df)                 attaches editable admin columns + computes longitudinal history
  └─ _cached_survey_pipeline(survey_df) @st.cache_data; receives survey answers WITHOUT administrative
                                        columns, so saving an edit never re-runs cleaning / scoring
                                        and only one DataFrame is stored in Streamlit's cache.

Every stage mutates the frame it receives; `run_survey_pipeline` makes the single defensive copy.
"""

import re
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd
import streamlit as st

from mappings import (
    CHOICE_MAPS,
    EDITABLE_COLS,
    FAMILY_SUPPORT_ITEMS,
    FAMILY_SUPPORT_MAP,
    MULTISELECT_GROUPS,
    NOT_APPLICABLE_VALUE,
    SCALES,
    WORKING_COMPAT_COLS,
    YES_NO_FIELDS,
    YES_NO_MAP,
)
from utils import NA_STRS, NULL_STRS

ADMIN_STR_COLS = EDITABLE_COLS + WORKING_COMPAT_COLS
CRISIS_TERMS = frozenset({"自伤意念", "自伤行为", "自杀意念", "自杀想法"})
# Checkbox "selected" markers (1 also matches 1.0 / True under isin)
_CHECKED = [1, "1", "1.0", "是"]


def load_raw_data(file_obj) -> pd.DataFrame:
    """
    Load raw CSV or Excel file, ensuring editable therapist columns
    and compatibility working columns exist with string dtype.
    """
    file_obj.seek(0)
    if getattr(file_obj, "name", "").endswith(".csv"):
        raw_df = pd.read_csv(file_obj)
    else:
        raw_df = pd.read_excel(file_obj)
    return ensure_administrative_columns(raw_df)


# ---------------------------------------------------------
# Pipeline Stage 1: Administrative Columns
# ---------------------------------------------------------
def ensure_administrative_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure editable and working compatibility columns exist as strings.
    String dtype matters: saving text into an all-NaN (float) column would
    otherwise raise a dtype warning (an error in pandas 3).
    """
    for col in ADMIN_STR_COLS:
        if col not in df.columns:
            df[col] = ""
    df[ADMIN_STR_COLS] = df[ADMIN_STR_COLS].fillna("").astype(str)
    return df


# ---------------------------------------------------------
# Vectorised cell helpers (Series-level versions of utils.safe_str / format_value)
# ---------------------------------------------------------
def _clean_text(s: pd.Series) -> pd.Series:
    """Stripped strings; missing -> '', jump codes (-3, '-3.0', ...) -> NOT_APPLICABLE_VALUE."""
    txt = s.astype(str).str.strip()
    txt = txt.where(s.notna() & ~txt.isin(NULL_STRS), "")
    return txt.mask(txt.str.removesuffix(".0").isin(NA_STRS), NOT_APPLICABLE_VALUE)


def _map_codes(s: pd.Series, mapping: dict) -> pd.Series:
    """Map option codes to labels ('2', 2 and 2.0 all hit key '2'); unknown values pass through."""
    key = _clean_text(s).str.removesuffix(".0")
    return key.map(mapping).fillna(key)


def _nonblank(df: pd.DataFrame, col: str) -> pd.Series:
    """Column with '' turned into NaN (all-NaN if the column is missing)."""
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=object)
    return df[col].replace("", np.nan)


# ---------------------------------------------------------
# Pipeline Stage 1b: Special Values & Missing Text Sanitization
# ---------------------------------------------------------
def sanitize_special_and_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitize survey conditional jump codes (-3) and missing text values.
    1. Replaces -3 with NOT_APPLICABLE_VALUE ('不适用').
    2. Fills missing NaN values in text/object/string columns with '' so they don't render as 'nan'.
    """
    # Process column-by-column to avoid pandas 2.x CoW block manager IndexError bug
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            continue
        if pd.api.types.is_numeric_dtype(s):
            if s.eq(-3).any():
                df[col] = s.replace(-3, NOT_APPLICABLE_VALUE)
        else:
            df[col] = _clean_text(s)
    return df


# ---------------------------------------------------------
# Pipeline Stage 2: Identifiers & Demographics Sanitization
# ---------------------------------------------------------
def clean_identifiers_and_demographics(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize patient phone numbers, national IDs, names, and age."""
    patterns = {
        # Digits-only for phone columns
        r"\D+": ["联系电话", "求诊者联系电话（手机号）", "紧急联系人电话（手机号）"],
        # National IDs: keep the 'X' check digit
        r"[^0-9X]+": ["求诊者身份证号", "身份证号"],
    }
    for pattern, cols in patterns.items():
        for col in (c for c in cols if c in df.columns):
            df[col] = (
                df[col]
                .fillna("")
                .astype(str)
                .str.upper()
                .str.replace(r"\.0$", "", regex=True)
                .str.replace(pattern, "", regex=True)
            )

    # Names: strip whitespace
    for col in ("姓名（实名）", "求诊者姓名", "紧急联系人的姓名"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    # Numeric age
    if "年龄" in df.columns:
        df["年龄_数值"] = pd.to_numeric(df["年龄"], errors="coerce")
    return df


# ---------------------------------------------------------
# Pipeline Stage 3: Datetime Parsing
# ---------------------------------------------------------
def parse_datetime_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Parse submission timestamps (column is created as NaT if absent)."""
    col = "提交答卷时间"
    df[col] = pd.to_datetime(df[col], errors="coerce") if col in df.columns else pd.NaT
    return df


# ---------------------------------------------------------
# Pipeline Stage 4: Single-Choice & Binary Mappings
# ---------------------------------------------------------
def map_categorical_choices(df: pd.DataFrame) -> pd.DataFrame:
    """Map single-choice option codes to human-readable strings."""
    yes_no = {col: YES_NO_MAP for col in YES_NO_FIELDS}
    for col, mapping in {**CHOICE_MAPS, **yes_no}.items():
        if col in df.columns:
            df[col] = _map_codes(df[col], mapping)

    # Standardize & map Family Support matrix items (SSRS Q37) -> 家庭支持_{label}
    for label, candidates in FAMILY_SUPPORT_ITEMS:
        col = next((c for c in candidates if c in df.columns), None)
        df[f"家庭支持_{label}"] = (
            _map_codes(df[col], FAMILY_SUPPORT_MAP).replace("", NOT_APPLICABLE_VALUE)
            if col
            else NOT_APPLICABLE_VALUE
        )
    return df


# ---------------------------------------------------------
# Pipeline Stage 5: Multi-Select Checkbox Consolidation
# ---------------------------------------------------------
def consolidate_multiselect_groups(df: pd.DataFrame) -> pd.DataFrame:
    """
    Consolidate one-hot checkbox columns (14, 19, 25, 39, 41, 目标) into list columns.
    The first column of a group may carry the question text before '—'
    (e.g. '想要通过心理治疗改善的目标—目标(改善症状)'), so prefixes are matched on the
    part after the last '—'.
    """
    tails = {c: str(c).split("—")[-1].strip() for c in df.columns}
    for out_col, prefix in MULTISELECT_GROUPS.items():
        cols = [c for c, t in tails.items() if t.startswith(prefix) and t.endswith(")")]
        labels = np.array([tails[c][len(prefix) : -1].strip() for c in cols], dtype=object)
        checked = df[cols].isin(_CHECKED).to_numpy()
        df[out_col] = [labels[row].tolist() for row in checked]
    return df


# ---------------------------------------------------------
# Pipeline Stage 6: Psychometric Scale Scoring Engine
# ---------------------------------------------------------
def find_scale_columns(columns: Sequence, scale: dict) -> List[Optional[str]]:
    """Match each scale item to a column via regex, falling back to fixed slice indices."""
    columns = list(columns)
    matched = [
        next((c for c in columns if re.search(pat, str(c))), None)
        for pat in scale["patterns"]
    ]
    lo, hi = scale["fallback"]
    if not any(matched) and len(columns) >= hi:
        matched = columns[lo:hi]
    return matched


def compute_clinical_scales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate psychometric scale item scores, total scores, severity tiers,
    and high-risk crisis flags for PHQ-9, GAD-7, and ISI (see mappings.SCALES).
    Item scores convert 1-indexed responses to 0-indexed Likert scores, clipped
    to [0, max_item]; blanks / '不适用' / non-numeric answers score 0.
    """
    for scale in SCALES:
        score_cols = []
        for idx, col in enumerate(find_scale_columns(df.columns, scale)):
            score_col = f"_{scale['key']}_score_{idx}"
            raw = pd.to_numeric(df[col], errors="coerce") if col else np.nan
            df[score_col] = (
                (np.trunc(pd.Series(raw, index=df.index, dtype=float)) - 1)
                .clip(0, scale["max_item"])
                .fillna(0)
                .astype(int)
            )
            score_cols.append(score_col)

        total = df[score_cols].sum(axis=1)
        df[scale["total_col"]] = total
        df[scale["severity_col"]] = pd.cut(
            total, [-np.inf, *scale["thresholds"], np.inf], labels=scale["tiers"]
        ).astype(str)

    # --- Crisis Risk Assessment (Q25 checkboxes & PHQ item 9: suicidal ideation) ---
    risks = df["crisis_risks_list"]
    phq9_positive = df["_phq_score_8"] > 0
    df["has_crisis_risk"] = risks.map(lambda r: not CRISIS_TERMS.isdisjoint(r)) | phq9_positive
    df["crisis_risk_flags"] = [
        [r for r in rs if r != "无"]
        + (["PHQ-9 自伤念头阳性"] if pos and "自伤意念" not in rs else [])
        for rs, pos in zip(risks, phq9_positive)
    ]
    return df


# ---------------------------------------------------------
# Pipeline Stage 7: Longitudinal History & Entity Tracking
# ---------------------------------------------------------
def track_longitudinal_patient_history(df: pd.DataFrame) -> pd.DataFrame:
    """
    Group submissions by patient (ID card, falling back to phone per row) and compute
    visit frequency, first/latest entry and the latest non-empty remark / progress.
    Rows with neither ID nor phone are treated as separate patients.
    """
    df["_original_idx"] = df.index
    # Stable sort so attempt #1 is always the earliest (ties keep file order)
    df = df.sort_values("提交答卷时间", kind="stable").reset_index(drop=True)

    key = _nonblank(df, "求诊者身份证号").fillna(_nonblank(df, "联系电话"))
    key = key.fillna(pd.Series("_row" + df.index.astype(str), index=df.index))
    groups = df.groupby(key, sort=False)
    times = groups["提交答卷时间"]

    df["提交次数"] = groups.cumcount() + 1
    df["总提交次数"] = times.transform("size")
    df["首次登记时间"] = times.transform("min")
    df["最新登记时间"] = times.transform("max")
    # Rows are chronological, so "last" = most recent non-empty entry
    for out_col, src_col in (("最近备注", "备注"), ("当前治疗进展", "回访治疗安排")):
        df[out_col] = _nonblank(df, src_col).groupby(key).transform("last").fillna("-")

    # Unique dropdown label: "姓名 (YYYY-mm-dd HH:MM)", suffixed " #n" on collisions
    names = df.get("姓名（实名）", pd.Series("", index=df.index)).replace("", "未知")
    label = names.astype(str) + " (" + df["提交答卷时间"].dt.strftime("%Y-%m-%d %H:%M").fillna("-") + ")"
    dup = label.groupby(label).cumcount()
    df["_label"] = label.where(dup == 0, label + " #" + (dup + 1).astype(str))
    return df


# ---------------------------------------------------------
# Master Pipeline Execution Functions
# ---------------------------------------------------------
def run_survey_pipeline(survey_df: pd.DataFrame) -> pd.DataFrame:
    """Cleaning + scoring stages (independent of the editable therapist columns)."""
    return (
        survey_df.copy()
        .pipe(sanitize_special_and_missing_values)
        .pipe(clean_identifiers_and_demographics)
        .pipe(parse_datetime_fields)
        .pipe(map_categorical_choices)
        .pipe(consolidate_multiselect_groups)
        .pipe(compute_clinical_scales)
    )


def _survey_part(raw_df: pd.DataFrame) -> pd.DataFrame:
    return raw_df.drop(columns=ADMIN_STR_COLS, errors="ignore")


def _attach_admin(survey_df: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    """Join the (string) administrative columns back on and compute patient history."""
    admin = raw_df.reindex(columns=ADMIN_STR_COLS).fillna("").astype(str)
    return track_longitudinal_patient_history(survey_df.join(admin))


def run_cleaning_pipeline(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Execute the full (uncached) multi-stage cleaning and clinical scoring pipeline."""
    return _attach_admin(run_survey_pipeline(_survey_part(raw_df)), raw_df)


# ---------------------------------------------------------
# Streamlit-Cached Public Interface
# ---------------------------------------------------------
@st.cache_data(show_spinner="正在处理数据...", max_entries=2)
def _cached_survey_pipeline(survey_df: pd.DataFrame) -> pd.DataFrame:
    return run_survey_pipeline(survey_df)


def preprocess_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Entry point for the Streamlit dashboard (reuses cached survey pipeline)."""
    return _attach_admin(_cached_survey_pipeline(_survey_part(raw_df)), raw_df)
