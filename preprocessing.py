"""
preprocessing.py - Data ingestion, cleaning, scale scoring, and preprocessing pipeline.
All internal variables, intermediate DataFrames, and functions use standard English naming.
"""

import re
from typing import List, Optional
import pandas as pd
import streamlit as st

from mappings import (
    ALL_ADMIN_COLS,
    CHOICE_MAPS,
    COHABITANT_PREFIX,
    CONTACT_OUTCOMES,
    DIAGNOSIS_PREFIX,
    EDITABLE_COLS,
    FREQUENCY_MAP,
    GAD_FIELDS,
    GAD_FREQUENCY_MAP,
    GAD_ITEM_PATTERNS,
    GAD_LABELS,
    GOAL_PREFIX,
    ISI_FIELDS,
    ISI_ITEM_PATTERNS,
    ISI_LABELS,
    NOT_APPLICABLE_VALUE,
    OBJECTIVE_SUPPORT_PREFIX,
    PHQ_FIELDS,
    PHQ_ITEM_PATTERNS,
    PHQ_LABELS,
    RISK_PREFIX,
    SUBJECTIVE_SUPPORT_PREFIX,
    TEXT_TO_SCORE,
    WORKING_COMPAT_COLS,
    YES_NO_FIELDS,
    YES_NO_MAP,
)


def load_raw_data(file_obj) -> pd.DataFrame:
    """
    Load raw CSV or Excel file, ensuring editable therapist columns
    and compatibility working columns exist with string dtype.
    """
    file_obj.seek(0)
    if hasattr(file_obj, "name") and file_obj.name.endswith(".csv"):
        raw_df = pd.read_csv(file_obj)
    else:
        raw_df = pd.read_excel(file_obj)

    # Ensure all administrative columns exist
    for col in ALL_ADMIN_COLS:
        if col not in raw_df.columns:
            raw_df[col] = ""

    # Force string dtype on editable columns
    raw_df[EDITABLE_COLS] = raw_df[EDITABLE_COLS].fillna("").astype(str)
    raw_df[WORKING_COMPAT_COLS] = raw_df[WORKING_COMPAT_COLS].fillna("").astype(str)
    return raw_df


# ---------------------------------------------------------
# Pipeline Stage 1: Administrative Columns & Index Preservation
# ---------------------------------------------------------
def ensure_administrative_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure editable and working compatibility columns are properly initialized."""
    clean_df = df.copy()
    for col in ALL_ADMIN_COLS:
        if col not in clean_df.columns:
            clean_df[col] = ""
    clean_df[EDITABLE_COLS] = clean_df[EDITABLE_COLS].fillna("").astype(str)
    clean_df[WORKING_COMPAT_COLS] = clean_df[WORKING_COMPAT_COLS].fillna("").astype(str)
    return clean_df


# ---------------------------------------------------------
# Pipeline Stage 1b: Special Values & Missing Text Sanitization
# ---------------------------------------------------------
def sanitize_special_and_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitize survey conditional jump codes (-3) and missing text values.
    1. Replaces -3, -3.0, '-3', '-3.0' with NOT_APPLICABLE_VALUE ('不适用').
    2. Fills missing NaN values in text/object/string columns with '' so they don't render as 'nan'.
    """
    clean_df = df.copy()
    na_markers = {-3, -3.0, "-3", "-3.0"}

    # Process column-by-column to avoid pandas 2.x CoW block manager IndexError bug
    for col in clean_df.columns:
        s = clean_df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            continue

        if pd.api.types.is_numeric_dtype(s):
            if s.isin([-3, -3.0]).any():
                clean_df[col] = s.replace([-3, -3.0], NOT_APPLICABLE_VALUE)
        else:
            # String, object, categorical, and mixed text columns
            clean_df[col] = s.map(
                lambda x: NOT_APPLICABLE_VALUE
                if x in na_markers
                else (
                    ""
                    if (pd.isna(x) or str(x).strip() in ("nan", "None", "NaT"))
                    else x
                )
            )

    return clean_df


# ---------------------------------------------------------
# Pipeline Stage 2: Identifiers & Demographics Sanitization
# ---------------------------------------------------------
def clean_identifiers_and_demographics(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize patient phone numbers, national IDs, names, and age."""
    clean_df = df.copy()

    # Digits-only for phone columns
    phone_cols = ["联系电话", "求诊者联系电话（手机号）", "紧急联系人电话（手机号）"]
    for col in phone_cols:
        if col in clean_df.columns:
            clean_df[col] = (
                clean_df[col]
                .fillna("")
                .astype(str)
                .str.replace(r"\.0$", "", regex=True)
                .str.replace(r"\D+", "", regex=True)
            )

    # National ID: strip whitespace and uppercase
    id_cols = ["求诊者身份证号", "身份证号"]
    for col in id_cols:
        if col in clean_df.columns:
            clean_df[col] = (
                clean_df[col]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )
            clean_df.loc[clean_df[col].isin(["nan", "None", "NaT"]), col] = ""

    # Names: strip whitespace
    name_cols = ["姓名（实名）", "求诊者姓名", "紧急联系人的姓名"]
    for col in name_cols:
        if col in clean_df.columns:
            clean_df[col] = clean_df[col].fillna("").astype(str).str.strip()
            clean_df.loc[clean_df[col].isin(["nan", "None", "NaT"]), col] = ""

    # Numeric age
    if "年龄" in clean_df.columns:
        clean_df["年龄_数值"] = pd.to_numeric(clean_df["年龄"], errors="coerce")

    return clean_df


# ---------------------------------------------------------
# Pipeline Stage 3: Datetime Parsing
# ---------------------------------------------------------
def parse_datetime_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Parse submission timestamps and therapist contact dates."""
    clean_df = df.copy()
    if "提交答卷时间" in clean_df.columns:
        clean_df["提交答卷时间"] = pd.to_datetime(
            clean_df["提交答卷时间"], errors="coerce"
        )
    return clean_df


# ---------------------------------------------------------
# Pipeline Stage 4: Single-Choice & Binary Mappings
# ---------------------------------------------------------
def map_categorical_choices(df: pd.DataFrame) -> pd.DataFrame:
    """Map single-choice option codes to human-readable strings."""
    clean_df = df.copy()

    # Map multiple-choice questions
    for col, choice_map in CHOICE_MAPS.items():
        if col in clean_df.columns:

            def _map_choice(val):
                if pd.isna(val) or val == "" or val is None:
                    return ""
                # Normalize float strings like "1.0" -> "1"
                s = str(val).strip()
                if s.endswith(".0"):
                    s = s[:-2]
                if s in ("-3", NOT_APPLICABLE_VALUE, "不适用"):
                    return NOT_APPLICABLE_VALUE
                if s in ("nan", "None", "NaT"):
                    return ""
                return choice_map.get(s, s)

            clean_df[col] = clean_df[col].apply(_map_choice)

    # Map binary fields
    for col in YES_NO_FIELDS:
        if col in clean_df.columns:

            def _map_yes_no(val):
                if pd.isna(val) or val == "" or val is None:
                    return ""
                s = str(val).strip()
                if s.endswith(".0"):
                    s = s[:-2]
                if s in ("-3", NOT_APPLICABLE_VALUE, "不适用"):
                    return NOT_APPLICABLE_VALUE
                if s in ("nan", "None", "NaT"):
                    return ""
                return YES_NO_MAP.get(s, YES_NO_MAP.get(val, s))

            clean_df[col] = clean_df[col].apply(_map_yes_no)

    return clean_df


# ---------------------------------------------------------
# Pipeline Stage 5: Multi-Select Checkbox Consolidation
# ---------------------------------------------------------
def _extract_selected_labels(row: pd.Series, prefix: str) -> List[str]:
    """Helper to extract selected labels from one-hot checkbox columns."""
    selected = []
    for col_name in row.index:
        if col_name.startswith(prefix) and "(" in col_name and col_name.endswith(")"):
            val = row[col_name]
            # Consider 1, '1', 1.0, '是', True as selected
            if val in (1, "1", 1.0, "1.0", "是", True):
                label = col_name[len(prefix) : -1].strip()
                selected.append(label)
    return selected


def consolidate_multiselect_groups(df: pd.DataFrame) -> pd.DataFrame:
    """
    Consolidate matrix checkbox columns (14, 19, 25, 39, 41, 目标)
    into structured list columns and clean display strings.
    """
    clean_df = df.copy()

    groups = [
        (COHABITANT_PREFIX, "cohabitants_list", "同居者_列表"),
        (DIAGNOSIS_PREFIX, "diagnoses_list", "主诉诊断_列表"),
        (RISK_PREFIX, "crisis_risks_list", "危机预警_列表"),
        (OBJECTIVE_SUPPORT_PREFIX, "objective_support_list", "客观支持来源_列表"),
        (SUBJECTIVE_SUPPORT_PREFIX, "subjective_support_list", "主观支持来源_列表"),
        (GOAL_PREFIX, "treatment_goals_list", "治疗目标_列表"),
    ]

    for prefix, en_col, cn_col in groups:
        matching_cols = [
            c for c in clean_df.columns if c.startswith(prefix) and "(" in c
        ]
        if matching_cols:
            extracted_series = clean_df.apply(
                lambda r: _extract_selected_labels(r, prefix), axis=1
            )
            clean_df[en_col] = extracted_series
            clean_df[cn_col] = extracted_series
        else:
            clean_df[en_col] = [[] for _ in range(len(clean_df))]
            clean_df[cn_col] = [[] for _ in range(len(clean_df))]

    return clean_df


# ---------------------------------------------------------
# Pipeline Stage 6: Psychometric Scale Scoring Engine
# ---------------------------------------------------------
def _find_scale_columns(
    df: pd.DataFrame, patterns: List[str], fallback_slice: Optional[List[int]] = None
) -> List[Optional[str]]:
    """Match survey columns using regex patterns with fallback to slice indices."""
    matched_cols: List[Optional[str]] = []
    all_cols = list(df.columns)

    for pat in patterns:
        found = None
        for col in all_cols:
            if re.search(pat, col):
                found = col
                break
        matched_cols.append(found)

    # Fallback to slice index if no columns matched
    if not any(matched_cols) and fallback_slice and len(all_cols) >= fallback_slice[1]:
        matched_cols = all_cols[fallback_slice[0] : fallback_slice[1]]

    return matched_cols


def _score_scale_item(val, max_score: int = 3) -> int:
    """Safely convert survey item response (digit 1-5 or text) into standard Likert score."""
    if pd.isna(val) or val is None or val == "":
        return 0

    val_str = str(val).strip()
    if val_str in (NOT_APPLICABLE_VALUE, "不适用", "-3", "-3.0", "not applicable"):
        return 0

    # If text choice is recognized
    if val_str in TEXT_TO_SCORE:
        return min(TEXT_TO_SCORE[val_str], max_score)

    # If numeric string or float/int
    try:
        num = float(val_str)
        if num < 0:
            return 0
        # Survey export encodes Likert options as 1-indexed (1, 2, 3, 4, 5)
        # Map to 0-indexed standard Likert score (0, 1, 2, 3, 4)
        score = int(num) - 1
        return max(0, min(score, max_score))
    except (ValueError, TypeError):
        return 0


def compute_clinical_scales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate psychometric scale item scores, total scores, severity tiers,
    and high-risk crisis flags for PHQ-9, GAD-7, and ISI.
    """
    clean_df = df.copy()

    # --- 1. PHQ-9 (9 items, item max score 3, total 27) ---
    phq_cols = _find_scale_columns(clean_df, PHQ_ITEM_PATTERNS, PHQ_FIELDS)
    phq_score_cols = []

    for idx, col in enumerate(phq_cols):
        score_col = f"_phq_score_{idx}"
        phq_score_cols.append(score_col)
        if col and col in clean_df.columns:
            clean_df[score_col] = clean_df[col].apply(
                lambda v: _score_scale_item(v, max_score=3)
            )
            # Format original column text for clean UI presentation
            clean_df[col] = clean_df[col].replace(FREQUENCY_MAP)
        else:
            clean_df[score_col] = 0

    clean_df["PHQ_Total"] = clean_df[phq_score_cols].sum(axis=1)

    def _phq_severity(score: int) -> str:
        if score <= 4:
            return "无/极轻度"
        elif score <= 9:
            return "轻度抑郁"
        elif score <= 14:
            return "中度抑郁"
        elif score <= 19:
            return "中重度抑郁"
        return "重度抑郁"

    clean_df["PHQ_Severity"] = clean_df["PHQ_Total"].apply(_phq_severity)

    # --- 2. GAD-7 (7 items, item max score 3, total 21) ---
    gad_cols = _find_scale_columns(clean_df, GAD_ITEM_PATTERNS, GAD_FIELDS)
    gad_score_cols = []

    for idx, col in enumerate(gad_cols):
        score_col = f"_gad_score_{idx}"
        gad_score_cols.append(score_col)
        if col and col in clean_df.columns:
            clean_df[score_col] = clean_df[col].apply(
                lambda v: _score_scale_item(v, max_score=3)
            )
            clean_df[col] = clean_df[col].replace(GAD_FREQUENCY_MAP)
        else:
            clean_df[score_col] = 0

    clean_df["GAD_Total"] = clean_df[gad_score_cols].sum(axis=1)

    def _gad_severity(score: int) -> str:
        if score <= 4:
            return "无/极轻度"
        elif score <= 9:
            return "轻度焦虑"
        elif score <= 14:
            return "中度焦虑"
        return "重度焦虑"

    clean_df["GAD_Severity"] = clean_df["GAD_Total"].apply(_gad_severity)

    # --- 3. ISI (7 items, item max score 4, total 28) ---
    isi_cols = _find_scale_columns(clean_df, ISI_ITEM_PATTERNS, ISI_FIELDS)
    isi_score_cols = []

    for idx, col in enumerate(isi_cols):
        score_col = f"_isi_score_{idx}"
        isi_score_cols.append(score_col)
        if col and col in clean_df.columns:
            clean_df[score_col] = clean_df[col].apply(
                lambda v: _score_scale_item(v, max_score=4)
            )
        else:
            clean_df[score_col] = 0

    clean_df["ISI_TOTAL"] = clean_df[isi_score_cols].sum(axis=1)

    def _isi_severity(score: int) -> str:
        if score <= 7:
            return "无显著失眠"
        elif score <= 14:
            return "轻度失眠"
        elif score <= 21:
            return "中度失眠"
        return "重度失眠"

    clean_df["ISI_Severity"] = clean_df["ISI_TOTAL"].apply(_isi_severity)

    # --- 4. Crisis Risk Assessment (Q25 & PHQ Item 9) ---
    def _check_crisis_risk(row: pd.Series) -> bool:
        # Check explicit self-harm / suicide checkbox options
        risks = row.get("crisis_risks_list", [])
        has_q25_risk = any(
            r in ["自伤意念", "自伤行为", "自杀意念", "自杀想法"] for r in risks
        )
        # Check PHQ Item 9 (Suicidal ideation item score > 0)
        has_phq9_risk = row.get("_phq_score_8", 0) > 0
        return has_q25_risk or has_phq9_risk

    clean_df["has_crisis_risk"] = clean_df.apply(_check_crisis_risk, axis=1)

    def _get_active_risk_labels(row: pd.Series) -> List[str]:
        labels = [r for r in row.get("crisis_risks_list", []) if r != "无"]
        if row.get("_phq_score_8", 0) > 0 and "自伤意念" not in labels:
            labels.append("PHQ-9 自伤念头阳性")
        return labels

    clean_df["crisis_risk_flags"] = clean_df.apply(_get_active_risk_labels, axis=1)

    return clean_df


# ---------------------------------------------------------
# Pipeline Stage 7: Longitudinal History & Entity Tracking
# ---------------------------------------------------------
def track_longitudinal_patient_history(df: pd.DataFrame) -> pd.DataFrame:
    """Group submissions by Patient ID (fallback to Phone) and compute visit frequency."""
    clean_df = df.copy()

    # Determine primary grouping column
    id_col = "求诊者身份证号" if "求诊者身份证号" in clean_df.columns else "联系电话"

    clean_df["_original_idx"] = clean_df.index

    if id_col in clean_df.columns and "提交答卷时间" in clean_df.columns:
        # Sort chronologically so attempt #1 is always the earliest
        clean_df = clean_df.sort_values("提交答卷时间", ascending=True).reset_index(
            drop=True
        )

        # 1-indexed attempt number
        clean_df["提交次数"] = clean_df.groupby(id_col).cumcount() + 1
        # Total number of entries for this patient
        clean_df["总提交次数"] = clean_df.groupby(id_col)[id_col].transform("count")
        # Exact date/time of the first/last entry in database
        clean_df["首次登记时间"] = clean_df.groupby(id_col)["提交答卷时间"].transform(
            "min"
        )
        clean_df["最新登记时间"] = clean_df.groupby(id_col)["提交答卷时间"].transform(
            "max"
        )

        # Check latest progress (support new and legacy column names)
        progress_col = (
            "回访治疗安排"
            if "回访治疗安排" in clean_df.columns
            else (
                "备注（回访治疗安排）"
                if "备注（回访治疗安排）" in clean_df.columns
                else None
            )
        )
        if progress_col:
            clean_df["当前治疗进展"] = clean_df.groupby(id_col)[progress_col].transform(
                "max"
            )
        else:
            clean_df["当前治疗进展"] = "-"
    else:
        clean_df["提交次数"] = 1
        clean_df["总提交次数"] = 1
        clean_df["首次登记时间"] = clean_df.get("提交答卷时间")
        clean_df["最新登记时间"] = clean_df.get("提交答卷时间")
        clean_df["当前治疗进展"] = "-"

    return clean_df


# ---------------------------------------------------------
# Master Pipeline Execution Function
# ---------------------------------------------------------
def run_cleaning_pipeline(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Execute full multi-stage data cleaning and clinical scoring pipeline.
    Uses method chaining (pipe) for modularity and testability.
    """
    return (
        raw_df.copy()
        .pipe(ensure_administrative_columns)
        .pipe(sanitize_special_and_missing_values)
        .pipe(clean_identifiers_and_demographics)
        .pipe(parse_datetime_fields)
        .pipe(map_categorical_choices)
        .pipe(consolidate_multiselect_groups)
        .pipe(compute_clinical_scales)
        .pipe(track_longitudinal_patient_history)
    )


# ---------------------------------------------------------
# Streamlit-Cached Public Interface
# ---------------------------------------------------------
@st.cache_data(show_spinner="正在处理数据...")
def preprocess_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Cached entry point for the Streamlit dashboard."""
    return run_cleaning_pipeline(raw_df)
