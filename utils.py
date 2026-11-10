"""
utils.py - Helper functions, data formatters, parsers, and chart builders.
"""

import altair as alt
import pandas as pd
import streamlit as st

from mappings import NOT_APPLICABLE_VALUE

# String renderings that mean "missing" (shared with the vectorised pipeline)
NULL_STRS = frozenset({"", "nan", "NaN", "NaT", "None", "<NA>"})
# Survey jump-code / not-applicable markers (after stripping a trailing ".0")
NA_STRS = frozenset({"-3", NOT_APPLICABLE_VALUE, "not applicable"})


# ---------------------------------------------------------
# Formatting & Extraction Helpers
# ---------------------------------------------------------
def phone_num_slicer(phone: str) -> str:
    """Format an 11-digit phone number as 'XXX XXXX XXXX'; return anything else unchanged."""
    p = str(phone).strip()
    return f"{p[:3]} {p[3:7]} {p[7:]}" if len(p) == 11 and p.isdigit() else p


# ---------------------------------------------------------
# Safe Parsing & Indexing Helpers for Forms
# ---------------------------------------------------------
def safe_str(val, default=""):
    """Return clean string, treating NaN / None / 'nan' / 'NaT' / '' as default."""
    if val is None or pd.isna(val):
        return default
    s = str(val).strip()
    return default if s in NULL_STRS else s


def format_value(val, default="-", na_text=NOT_APPLICABLE_VALUE) -> str:
    """
    Format a survey or patient profile field for clean UI display.
    Treats NaN, None, 'nan', 'NaT', 'None', and empty string as default ('-').
    Treats -3, -3.0, '-3', '-3.0', '不适用' as na_text ('不适用').
    """
    s = safe_str(val, default=None)
    if s is None:
        return default
    s = s.removesuffix(".0")
    return na_text if s in NA_STRS else s


def parse_date(val):
    """Safely return a datetime.date object or None."""
    s = safe_str(val)
    if not s:
        return None
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


def parse_multi(val, options: list) -> list:
    """Parse a comma-separated string into a list of valid options."""
    s = safe_str(val)
    if not s:
        return []
    return [v.strip() for v in s.split(",") if v.strip() in options]


def safe_index(options: list, val, default=0) -> int:
    """Return the index of val in options, or default if not found."""
    s = safe_str(val)
    try:
        return options.index(s)
    except ValueError:
        return default


# ---------------------------------------------------------
# Visualization Helpers
# ---------------------------------------------------------
def plot_scale_breakdown(
    item_names, scores, max_score=3, title="条目明细分布", height=None
):
    """Render a horizontal bar chart breakdown of psychometric scale items."""
    chart_data = pd.DataFrame({"条目": item_names, "得分": scores})
    calc_height = height or max(260, len(item_names) * 35)

    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X(
                "得分:Q",
                scale=alt.Scale(domain=[0, max_score]),
                title=f"得分 (0-{max_score})",
            ),
            y=alt.Y("条目:N", sort=None),
            color=alt.Color(
                "得分:Q",
                scale=alt.Scale(scheme="redyellowgreen", reverse=True),
                legend=None,
            ),
            tooltip=["条目", "得分"],
        )
        .properties(title=title, height=calc_height)
    )

    text = chart.mark_text(align="left", baseline="middle", dx=3).encode(text="得分:Q")

    return st.altair_chart(chart + text, width="stretch")
