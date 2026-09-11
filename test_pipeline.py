"""
test_pipeline.py - Automated verification tests for the clinical data cleaning pipeline.
"""

import os
import sys
import pandas as pd

from mappings import (
    ALL_ADMIN_COLS,
    EDITABLE_COLS,
    GAD_LABELS,
    ISI_LABELS,
    PHQ_LABELS,
    WORKING_COMPAT_COLS,
)
from preprocessing import load_raw_data, preprocess_data


def run_tests():
    print("=== Testing Pipeline Initialization ===")
    mock_file = "mock.xlsx"
    assert os.path.exists(mock_file), f"File {mock_file} not found!"

    with open(mock_file, "rb") as f:
        loaded_raw = load_raw_data(f)

    print(f"load_raw_data output shape: {loaded_raw.shape}")
    for col in EDITABLE_COLS:
        assert col in loaded_raw.columns, (
            f"Editable column {col} missing in loaded_raw!"
        )
    for col in WORKING_COMPAT_COLS:
        assert col in loaded_raw.columns, (
            f"Compatibility column {col} missing in loaded_raw!"
        )

    print("✅ Stage 0: load_raw_data passed.")

    # Test preprocess_data
    clean_df = preprocess_data(loaded_raw)
    print(f"preprocess_data output shape: {clean_df.shape}")

    # Verify core columns exist
    assert "PHQ_Total" in clean_df.columns, "PHQ_Total missing!"
    assert "GAD_Total" in clean_df.columns, "GAD_Total missing!"
    assert "ISI_TOTAL" in clean_df.columns, "ISI_TOTAL missing!"
    assert "_original_idx" in clean_df.columns, "_original_idx missing!"
    assert "提交次数" in clean_df.columns, "提交次数 missing!"
    assert "总提交次数" in clean_df.columns, "总提交次数 missing!"
    assert "has_crisis_risk" in clean_df.columns, "has_crisis_risk missing!"

    # Verify derived multiselect list columns
    assert "diagnoses_list" in clean_df.columns, "diagnoses_list missing!"
    assert "crisis_risks_list" in clean_df.columns, "crisis_risks_list missing!"
    assert "treatment_goals_list" in clean_df.columns, "treatment_goals_list missing!"
    assert "cohabitants_list" in clean_df.columns, "cohabitants_list missing!"

    row0 = clean_df.iloc[0]
    print("=== Sample Cleaned Record ===")
    print("Patient:", row0.get("姓名（实名）"))
    print("Phone:", row0.get("联系电话"))
    print("PHQ_Total:", row0.get("PHQ_Total"), f"({row0.get('PHQ_Severity')})")
    print("GAD_Total:", row0.get("GAD_Total"), f"({row0.get('GAD_Severity')})")
    print("ISI_TOTAL:", row0.get("ISI_TOTAL"), f"({row0.get('ISI_Severity')})")
    print("Diagnoses:", row0.get("diagnoses_list"))
    print("Crisis Risks:", row0.get("crisis_risks_list"))
    print("Has Crisis Risk:", row0.get("has_crisis_risk"))
    print("Crisis Flags:", row0.get("crisis_risk_flags"))
    print("Treatment Goals:", row0.get("treatment_goals_list"))
    print("Cohabitants:", row0.get("cohabitants_list"))

    # Verify scale score columns
    for i in range(len(PHQ_LABELS)):
        assert f"_phq_score_{i}" in clean_df.columns, f"_phq_score_{i} missing!"
    for i in range(len(GAD_LABELS)):
        assert f"_gad_score_{i}" in clean_df.columns, f"_gad_score_{i} missing!"
    for i in range(len(ISI_LABELS)):
        assert f"_isi_score_{i}" in clean_df.columns, f"_isi_score_{i} missing!"

    # Test Edit-Save workflow
    raw_idx = int(row0["_original_idx"])
    loaded_raw.at[raw_idx, "首访治疗师"] = "测试治疗师"
    loaded_raw.at[raw_idx, "首访情况"] = "本人接听"
    loaded_raw.at[raw_idx, "治疗推荐"] = "个体, 家庭"
    loaded_raw.at[raw_idx, "回访治疗安排"] = "已安排周三首访"

    recleaned_df = preprocess_data(loaded_raw)
    re_row0 = recleaned_df.iloc[0]
    assert re_row0["首访治疗师"] == "测试治疗师", "Edited therapist not saved!"
    assert re_row0["首访情况"] == "本人接听", "Edited outcome not saved!"
    assert re_row0["当前治疗进展"] == "已安排周三首访", (
        "Therapist progress not updated!"
    )

    # Verify working columns preserved
    for w_col in WORKING_COMPAT_COLS:
        assert w_col in loaded_raw.columns, (
            f"Working column {w_col} missing after edit!"
        )

    print("✅ Stage 1: Edit-Save simulation and working columns preservation passed.")
    print("✅ All assertions passed successfully!")


if __name__ == "__main__":
    run_tests()
