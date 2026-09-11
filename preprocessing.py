"""
preprocessing.py - Data ingestion, cleaning, scale scoring, and preprocessing pipeline.
"""

import pandas as pd
import streamlit as st

from mappings import (
    CHOICE_MAPS,
    EDITABLE_COLS,
    FREQUENCY_MAP,
    GAD_FIELDS,
    ISI_FIELDS,
    PHQ_FIELDS,
    YES_NO_FIELDS,
    YES_NO_MAP,
)


def load_raw_data(file) -> pd.DataFrame:
    """Load raw CSV or Excel file, ensuring editable columns exist with string dtype."""
    file.seek(0)
    raw = (
        pd.read_csv(file)
        if file.name.endswith(".csv")
        else pd.read_excel(file)
    )
    # Ensure editable columns exist (new files may not have them yet)
    for col in EDITABLE_COLS:
        if col not in raw.columns:
            raw[col] = ""
    # Force string dtype so saving strings to empty columns won't fail
    raw[EDITABLE_COLS] = raw[EDITABLE_COLS].fillna("").astype(str)
    return raw


@st.cache_data(show_spinner="正在处理数据...")
def preprocess_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Clean and transform the raw clinical registration DataFrame for presentation."""
    df = raw_df.copy()

    # 1. Standardize string identifier columns
    string_cols = ["联系电话", "求诊者身份证号"]
    for col in string_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(r"\D+", "", regex=True)

    # 2. Parse submission time
    if "提交答卷时间" in df.columns:
        df["提交答卷时间"] = pd.to_datetime(df["提交答卷时间"], errors="coerce")

    # 3. Dynamic Column Identification (Resilient to shifting column index)
    phq_cols = (
        df.columns[PHQ_FIELDS[0] : PHQ_FIELDS[1]]
        if len(df.columns) >= PHQ_FIELDS[1]
        else []
    )
    gad_cols = (
        df.columns[GAD_FIELDS[0] : GAD_FIELDS[1]]
        if len(df.columns) >= GAD_FIELDS[1]
        else []
    )
    isi_cols = (
        df.columns[ISI_FIELDS[0] : ISI_FIELDS[1]]
        if len(df.columns) >= ISI_FIELDS[1]
        else []
    )

    # 4. Standardize Survey Scales (Assumes input 1-4 mapped to 0-3)
    for prefix, cols in [
        ("_phq_score_", phq_cols),
        ("_gad_score_", gad_cols),
        ("_isi_score_", isi_cols),
    ]:
        for idx, col in enumerate(cols):
            numeric_s = pd.to_numeric(df[col], errors="coerce").fillna(1)
            # Normalize 1-4 scale down to 0-3 standard Likert score
            df[f"{prefix}{idx}"] = (numeric_s - 1).clip(lower=0, upper=3).astype(int)

    # 5. Calculate Total Scores
    phq_score_cols = [f"_phq_score_{i}" for i in range(len(phq_cols))]
    gad_score_cols = [f"_gad_score_{i}" for i in range(len(gad_cols))]
    isi_score_cols = [f"_isi_score_{i}" for i in range(len(isi_cols))]

    df["PHQ_Total"] = df[phq_score_cols].sum(axis=1) if phq_score_cols else 0
    df["GAD_Total"] = df[gad_score_cols].sum(axis=1) if gad_score_cols else 0
    df["ISI_TOTAL"] = df[isi_score_cols].sum(axis=1) if isi_score_cols else 0

    # 6. Map number key to readable values from dictionary
    for column, mapping in CHOICE_MAPS.items():
        if column in df.columns:
            df[column] = df[column].astype(str).map(mapping)

    for column in YES_NO_FIELDS:
        if column in df.columns:
            df[column] = df[column].astype(float).map(YES_NO_MAP)

    df[phq_cols] = df[phq_cols].replace(FREQUENCY_MAP)
    df[gad_cols] = df[gad_cols].replace(FREQUENCY_MAP)

    # 7. Calculate Repeat Submissions & First Entry Timestamp
    # Fall back to phone number if national ID is absent or empty
    id_col = "求诊者身份证号" if "求诊者身份证号" in df.columns else "联系电话"

    if id_col in df.columns and "提交答卷时间" in df.columns:
        # Preserve original index for edit-save mapping
        df["_original_idx"] = df.index
        # Sort chronologically so attempt #1 is always the earliest
        df = df.sort_values("提交答卷时间", ascending=True).reset_index(drop=True)

        # 1-indexed attempt number
        df["提交次数"] = df.groupby(id_col).cumcount() + 1
        # Total number of entries for this patient
        df["总提交次数"] = df.groupby(id_col)[id_col].transform("count")
        # Exact date/time of the first/last entry in database
        df["首次登记时间"] = df.groupby(id_col)["提交答卷时间"].transform("min")
        df["最新登记时间"] = df.groupby(id_col)["提交答卷时间"].transform("max")
        # Check latest progress (support new and legacy column name)
        _progress_col = (
            "回访治疗安排" if "回访治疗安排" in df.columns else "备注（回访治疗安排）"
        )
        if _progress_col in df.columns:
            df["当前治疗进展"] = df.groupby(id_col)[_progress_col].transform("max")
    else:
        df["_original_idx"] = df.index
        df["提交次数"] = 1
        df["总提交次数"] = 1
        df["首次登记时间"] = df.get("提交答卷时间")

    return df
