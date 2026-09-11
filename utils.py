"""
utils.py - Helper functions, data formatters, parsers, and chart builders.
"""

import altair as alt
import pandas as pd
import streamlit as st


# ---------------------------------------------------------
# Formatting & Extraction Helpers
# ---------------------------------------------------------
def phone_num_slicer(phone: str) -> str:
    """Format a 11-digit phone number into 'XXX XXXX XXXX' format."""
    phone = str(phone).strip()
    phone_slice = [phone[:3], phone[3:7], phone[7:]]
    return " ".join(phone_slice)


def get_diagnoses(diagnosis_columns, person) -> list:
    """Extract previous diagnoses marked as positive in the patient record."""
    prev_diagnoses = []
    for label in diagnosis_columns:
        if person.get(label) == 1:
            prev_diagnoses.append(label.split("(")[1].split(")")[0].strip())
    return prev_diagnoses


# ---------------------------------------------------------
# Safe Parsing & Indexing Helpers for Forms
# ---------------------------------------------------------
def safe_str(val, default=""):
    """Return clean string, treating NaN / None / 'nan' / 'NaT' as default."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    s = str(val).strip()
    return default if s in ("nan", "NaT", "None", "") else s


def parse_date(val):
    """Safely return a datetime.date object or None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if s in ("", "nan", "NaT", "None"):
        return None
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


def parse_multi(val, options: list) -> list:
    """Parse a comma-separated string into a list of valid options."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    return [v.strip() for v in str(val).split(",") if v.strip() in options]


def safe_index(options: list, val, default=0) -> int:
    """Return the index of val in options, or default if not found."""
    s = safe_str(val)
    try:
        return options.index(s)
    except ValueError:
        return default


# Backward compatibility aliases with underscore prefix
_safe_str = safe_str
_parse_date = parse_date
_parse_multi = parse_multi
_safe_index = safe_index


# ---------------------------------------------------------
# Visualization Helpers
# ---------------------------------------------------------
def plot_scale_breakdown(item_names, scores, max_score=3, title="条目明细分布"):
    """Render a horizontal bar chart breakdown of psychometric scale items."""
    chart_data = pd.DataFrame({"条目": item_names, "得分": scores})

    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X(
                "得分:Q", scale=alt.Scale(domain=[0, max_score]), title="得分 (0-3)"
            ),
            y=alt.Y("条目:N", sort=None),
            color=alt.Color(
                "得分:Q",
                scale=alt.Scale(scheme="redyellowgreen", reverse=True),
                legend=None,
            ),
            tooltip=["条目", "得分"],
        )
        .properties(title=title, height=320)
    )

    text = chart.mark_text(align="left", baseline="middle", dx=3).encode(text="得分:Q")

    return st.altair_chart(chart + text, width="stretch")
