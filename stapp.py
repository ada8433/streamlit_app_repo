import datetime
import io
import re

import pandas as pd
import streamlit as st

from mappings import (
    CONTACT_OUTCOMES,
    FAMILY_SUPPORT_ITEMS,
    SCALES,
    TREATMENT_OPTIONS,
)
from preprocessing import find_scale_columns, load_raw_data, preprocess_data
from utils import (
    format_value,
    parse_date,
    parse_multi,
    phone_num_slicer,
    plot_scale_breakdown,
    safe_index,
    safe_str,
)

# Page setup
st.set_page_config(page_title="门诊预约Dashboard", page_icon="📋", layout="wide")


# ---------------------------------------------------------
# Navigation & Filter Helpers
# ---------------------------------------------------------
def step_patient(step: int):
    curr_idx = name_options.index(st.session_state.dropdown_val)
    # Modulo (%) provides circular wrap-around
    st.session_state.dropdown_val = name_options[(curr_idx + step) % len(name_options)]


def _get_filter_options(df: pd.DataFrame, col: str, order: list | None = None) -> list:
    """Extract ordered unique options for a categorical filter column."""
    if col not in df.columns:
        return []
    present = {v for v in df[col].dropna().unique() if safe_str(v)}
    options = [m for m in order if m in present] if order else []
    return options if options else sorted(present)


def _sidebar_multiselect_filter(
    df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    col: str,
    label: str,
    key: str,
    order: list | None = None,
) -> pd.DataFrame:
    """Render a sidebar multiselect filter for a categorical column and filter rows."""
    if col not in filtered_df.columns:
        return filtered_df
    options = _get_filter_options(df, col, order)
    selected = st.sidebar.multiselect(label, options=options, key=key)
    return filtered_df[filtered_df[col].isin(selected)] if selected else filtered_df


def init_or_reset_filters(df: pd.DataFrame, force: bool = False):
    """Initialize or reset all filter blocks in session_state to their default values."""
    has_dates = not df["提交答卷时间"].isna().all()
    today = pd.to_datetime("today").date()
    min_date = df["提交答卷时间"].min().date() if has_dates else today
    max_date = df["提交答卷时间"].max().date() if has_dates else today

    defaults = {
        "filter_date_range": (min_date, max_date),
        "filter_treatments": _get_filter_options(df, "请选择您需要预约登记的治疗方式"),
        "filter_sex": _get_filter_options(df, "性别"),
        "filter_rec": [],
        "filter_priority": False,
        "filter_marriage": _get_filter_options(
            df, "婚姻状态", order=["单身", "未婚", "已婚", "离婚", "丧偶"]
        ),
        "filter_crisis": "全部求诊者",
        "filter_therapist": "全部",
    }
    for k, val in defaults.items():
        if force or k not in st.session_state:
            st.session_state[k] = val


# ---------------------------------------------------------
# Main Execution Flow
# ---------------------------------------------------------
uploaded_file = st.sidebar.file_uploader("📂 选择数据文件", type=["csv", "xlsx"])

if not uploaded_file:
    st.info("👈 请在左侧侧边栏上传门诊预约登记表 (CSV / XLSX)。")
    st.stop()

# Store raw data in session state for the edit-and-save workflow
new_file_loaded = (
    "raw_df" not in st.session_state
    or st.session_state.get("_file_name") != uploaded_file.name
)
if new_file_loaded:
    st.session_state["raw_df"] = load_raw_data(uploaded_file)
    st.session_state["_file_name"] = uploaded_file.name

df = preprocess_data(st.session_state["raw_df"])

# Initialize filter defaults in session_state (force reset if brand-new file uploaded)
init_or_reset_filters(df, force=new_file_loaded)

# ------------ Sidebar filters -------------
st.sidebar.header("🔍 档案检索与筛选")

total_count = len(df)
high_risk_total = (
    int(df["has_crisis_risk"].sum()) if "has_crisis_risk" in df.columns else 0
)
st.sidebar.caption(f"📊 总共：**{total_count}** 位 | 🚨 高危：**{high_risk_total}** 位")

# 0. Quick Reset Button
if st.sidebar.button("🔄 重置所有筛选", use_container_width=True):
    init_or_reset_filters(df, force=True)
    st.rerun()


# 1. Filter By Date
date_range = st.sidebar.date_input(
    "📅 登记日期范围",
    key="filter_date_range",
)

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
    filtered_df = df[df["提交答卷时间"].dt.date.between(start_date, end_date)]
else:
    filtered_df = df


# 2. Filter By Priority (优先安排)
if st.sidebar.checkbox("‼️ 仅看优先安排", key="filter_priority"):
    filtered_df = filtered_df[filtered_df["优先安排"] == "是"]

# 3. Filter By Treatment Type (预约治疗方式)
filtered_df = _sidebar_multiselect_filter(
    df,
    filtered_df,
    col="请选择您需要预约登记的治疗方式",
    label="🛋️ 预约治疗方式",
    key="filter_treatments",
)

# 4. Filter By Sex (性别)
filtered_df = _sidebar_multiselect_filter(
    df,
    filtered_df,
    col="性别",
    label="💁 性别",
    key="filter_sex",
)

# 5. Filter By Treatment Recommendation (治疗推荐)
selected_recs = st.sidebar.multiselect(
    "🏷️ 治疗推荐",
    options=["未推荐/待定"] + TREATMENT_OPTIONS,
    key="filter_rec",
    help="留空代表不过滤；可多选，匹配推荐内容中包含任一项的记录",
)
if selected_recs:
    rec_s = filtered_df["治疗推荐"].fillna("").astype(str).str.strip()
    mask = pd.Series(False, index=filtered_df.index)
    if "未推荐/待定" in selected_recs:
        mask |= rec_s.isin(["", "-", "不适用"])
    targets = [re.escape(t) for t in selected_recs if t != "未推荐/待定"]
    if targets:
        mask |= rec_s.str.contains("|".join(targets), regex=True)
    filtered_df = filtered_df[mask]

# 6. Filter By Marriage Status (婚姻情况)
filtered_df = _sidebar_multiselect_filter(
    df,
    filtered_df,
    col="婚姻状态",
    label="💍 婚姻情况",
    key="filter_marriage",
    order=["单身", "未婚", "已婚", "离婚", "丧偶"],
)

# 7. Filter By Crisis Risk (危机预警)
crisis_filter = st.sidebar.selectbox(
    "🚨 危机预警筛选",
    options=["全部求诊者", "🚨 仅高危预警 (自伤/自杀/PHQ9项)", "常规求诊者"],
    key="filter_crisis",
)
if crisis_filter == "🚨 仅高危预警 (自伤/自杀/PHQ9项)":
    filtered_df = filtered_df[filtered_df["has_crisis_risk"].astype(bool)]
elif crisis_filter == "常规求诊者":
    filtered_df = filtered_df[~filtered_df["has_crisis_risk"].astype(bool)]

# 8. Filter By First Therapist (首访治疗师)
therapist_s = df["首访治疗师"].fillna("").astype(str).str.strip()
all_therapists = sorted(t for t in therapist_s.unique() if t not in ("", "-", "不适用"))
selected_therapist = st.sidebar.selectbox(
    "👨‍⚕️ 首访治疗师",
    options=["全部"] + all_therapists + ["未分配"],
    key="filter_therapist",
)
if selected_therapist == "未分配":
    filtered_df = filtered_df[
        filtered_df["首访治疗师"]
        .fillna("")
        .astype(str)
        .str.strip()
        .isin(["", "-", "不适用"])
    ]
elif selected_therapist != "全部":
    filtered_df = filtered_df[filtered_df["首访治疗师"] == selected_therapist]

# Filter result summary
st.sidebar.markdown(f"**当前筛选结果**：`{len(filtered_df)}` / `{len(df)}` 位")

if filtered_df.empty:
    st.warning("⚠️ 当前筛选条件下未找到求诊者记录，请调整或重置筛选条件。")
    st.stop()


# ---- Patient Search & Prev/Next buttons ----
name_options = filtered_df["_label"].tolist()

if (
    "dropdown_val" not in st.session_state
    or st.session_state.dropdown_val not in name_options
):
    st.session_state.dropdown_val = name_options[0]

col_prev, col_dropdown, col_next = st.columns([1, 4, 1], vertical_alignment="bottom")

with col_prev:
    st.button("◀️ 上一位", key="top_prev", on_click=step_patient, args=(-1,))

with col_next:
    st.button("▶️ 下一位", key="top_next", on_click=step_patient, args=(1,))

with col_dropdown:
    selected_label = st.selectbox(
        "🔍 选择/输入求诊者姓名（预约提交时间）",
        options=name_options,
        key="dropdown_val",
    )

# Active record
patient_idx = name_options.index(selected_label)
person = filtered_df.iloc[patient_idx]


def pget(col, default="-"):
    return format_value(person.get(col), default=default)


st.caption(f"当前第 **{patient_idx + 1}** / **{len(name_options)}** 位求诊者")

if st.session_state.pop("_save_success", False):
    st.toast("✅ 评估登记已成功保存！", icon="💾")

# ---------------------------------------------------------
# Main View: Structured Sections
# ---------------------------------------------------------

# Patient Demo Banner
phone_number = phone_num_slicer(pget("联系电话", "-"))
st.title(
    f"👤 {pget('姓名（实名）', '未知')} | "
    f"{pget('年龄', '未填')} 岁 | "
    f"{pget('性别', '未填')} | "
    f"📞 {phone_number} "
    f":violet-badge[💬 {pget('请选择您需要预约登记的治疗方式', '未选')}] "
    f":blue-badge[{pget('首访治疗师', '-')}]"
)

# Repeat Submission Alert & First Entry Notice
total_submissions = int(person.get("总提交次数", 1))
current_submission = int(person.get("提交次数", 1))
first_entry_time = person.get("首次登记时间")
current_progress = person.get("当前治疗进展", "-")
last_note = person.get("最近备注", "-")

first_entry_str = (
    pd.to_datetime(first_entry_time).strftime("%Y-%m-%d %H:%M")
    if pd.notna(first_entry_time)
    else "未知"
)

if total_submissions > 1:
    st.warning(
        f"📋 **多次登记提示**：该求诊者在数据库中共有 **{total_submissions}** 次提交记录（当前查看的是第 **{current_submission}** 次）。\n\n"
        f"**初次登记时间**：{first_entry_str}\n\n"
    )

st.info(f"**当前治疗进展**：{current_progress}\n\n**最近备注**：{last_note}")

# Key Metrics
main = st.container()

# Diagnosis badges
diagnoses_list = person.get("diagnoses_list", [])
main.write(" ".join(f":red-badge[{d}]" for d in diagnoses_list))

# Scale Metrics
for col_ui, scale in zip(main.columns(3), SCALES):
    sev = person.get(scale["severity_col"], "")
    max_total = scale["max_item"] * len(scale["labels"])
    col_ui.metric(
        label=f"{scale['title']} · {sev}" if sev else scale["title"],
        value=f"{int(person[scale['total_col']])} / {max_total}",
    )

# Risk indicators (Self-harm / Suicide)
active_risks = person.get("crisis_risk_flags", [])
if active_risks:
    main.error(f"⚠️ 风险预警指标: {', '.join(active_risks)}")

# Organize columns into Tabs
tab1, tab2, tab3, tab4, tab5 = main.tabs(
    [
        "1. 基本信息与联络",
        "2. 临床表现与用药史",
        "3. 量表评估结果",
        "4. 社会支持网络",
        "5. 治疗目标与预约",
    ]
)

# ---------------------------------------------------------
# TAB 1: Basic Info & Contacts
# ---------------------------------------------------------
with tab1:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 🆔 身份证明")
        st.write(f"**姓名**：{pget('姓名（实名）')}")
        st.write(f"**身份证号**：{pget('求诊者身份证号')}")
        st.write(f"**联系电话**：{pget('联系电话')}")
        st.write(f"**常住地**：{pget('您的常住地为')}")
        st.write(f"**户籍地**：{pget('您的户籍所在地')}")

    with col2:
        st.markdown("### 🎓 社会人口学资料")
        st.write(f"**教育水平**：{pget('教育水平')}")
        st.write(f"**职业**：{pget('职业')}")
        st.write(f"**年级**：{pget('年级')}")
        st.write(f"**休学/离职状态**：{pget('目前是否已经休学/休假或离职')}")
        st.write(
            f"**婚姻/生育状态**：{pget('婚姻状态')}, {pget('生育状态')} (孩子数: {pget('孩子个数')})"
        )
        cohabitants = person.get("cohabitants_list", [])
        st.write(
            f"**主要同居者**：{'、'.join(cohabitants) if cohabitants else '未明确记录'}"
        )
        st.write(f"**饲养宠物**：{pget('是否饲养宠物')}")

    with col3:
        st.markdown("### 📞 紧急联系人")
        st.write(f"**紧急联系人**：{pget('紧急联系人的姓名')}")
        st.write(f"**关系**：{pget('紧急联系人与来访的关系：')}")
        st.write(f"**联系电话**：{pget('紧急联系人电话（手机号）')}")

# ---------------------------------------------------------
# TAB 2: Clinical & Medication History
# ---------------------------------------------------------
with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🏥 诊疗背景")
        st.write(f"**病程（月）**：{pget('病程（月）')}")
        st.write(f"**首次来院年份**：{pget('首次来我院就诊年份')}")
        st.write(f"**本院就诊经历**：{pget('是否曾在本院心理咨询门诊就诊')}")
        st.write(
            f"**重大生活事件**：{pget('半年内是否经历重大生活事件')} ({pget('请注明具体事件', '无说明')})"
        )
        st.write(f"**家族史**：{pget('是否有精神/心理疾病家族史')}")
        st.write(f"**躯体疾病**：{pget('是否有躯体疾病')}")

    with col2:
        st.markdown("### 💊 药物使用与安全状态")
        st.write(f"**目前是否服药**：{pget('目前是否在服用精神科药物')}")
        st.write(f"**药物名称/时间/剂量**：{pget('服用药物名称，服用时间，剂量')}")
        st.write(f"**未服药情况**：{pget('未服药情况')}")

        present_symptoms = person.get("diagnoses_list", [])
        st.write(
            f"**当前主诉/症状**：{', '.join(present_symptoms) if present_symptoms else '无特异记录'}"
        )

# ---------------------------------------------------------
# TAB 3: Scales (PHQ-9, GAD-7, ISI)
# ---------------------------------------------------------
with tab3:
    scale_by_key = {s["key"]: s for s in SCALES}

    def _get_scale_scores(scale: dict) -> list[int]:
        return [
            int(person.get(f"_{scale['key']}_score_{i}", 0))
            for i in range(len(scale["labels"]))
        ]

    def _render_scale_summary(scale: dict, show_score: bool = False):
        cols = find_scale_columns(df.columns, scale)
        sev = person.get(scale["severity_col"], "")
        sev_str = f" ({sev})" if sev else ""
        short_name = scale["name"].split("-")[0]
        st.write(
            f"#### {short_name}总分：{person.get(scale['total_col'], '-')}{sev_str}"
        )
        st.markdown(f"#### {scale['name']} 项目摘要")
        for idx, lbl in enumerate(scale["labels"]):
            col_name = cols[idx] if idx < len(cols) and cols[idx] else lbl
            item_label = (
                str(col_name).split("—")[-1]
                if not show_score and idx < len(cols) and cols[idx]
                else lbl
            )
            val_text = format_value(person.get(col_name, "-"))
            if show_score:
                score_val = person.get(f"_{scale['key']}_score_{idx}", 0)
                st.write(f"• **{item_label}**: {val_text} `({score_val}分)`")
            else:
                st.write(f"• **{item_label}**: {val_text}")

    st.markdown("### 📝 抑郁与焦虑自评（PHQ-9 & GAD-7）")
    for col_ui, key in zip(st.columns(2, gap="medium", border=True), ("phq", "gad")):
        sc = scale_by_key[key]
        with col_ui:
            plot_scale_breakdown(
                sc["labels"],
                _get_scale_scores(sc),
                max_score=sc["max_item"],
                title=sc["chart_title"],
            )
            _render_scale_summary(sc)

    st.markdown("### 💤 失眠严重程度自评（ISI）")
    isi_sc = scale_by_key["isi"]
    c3, c4 = st.columns(2, gap="medium", border=True)
    with c3:
        plot_scale_breakdown(
            isi_sc["labels"],
            _get_scale_scores(isi_sc),
            max_score=isi_sc["max_item"],
            title=isi_sc["chart_title"],
        )
    with c4:
        _render_scale_summary(isi_sc, show_score=True)

# ---------------------------------------------------------
# TAB 4: Social Support Network (SSRS & Ecological Context)
# ---------------------------------------------------------
with tab4:
    st.markdown("### 🤝 社会支持网络与人际生态评估")

    # Row 1: Living Environment & Interpersonal Support
    sec1, sec2 = st.columns(2, gap="medium")
    with sec1:
        with st.container(border=True):
            st.markdown("#### 🏠 居住环境与同居生态")
            st.write(f"**近一年居住情况**：{pget('近一年来您：（只选一项）')}")
            cohabitants = person.get("cohabitants_list", [])
            st.write(
                f"**主要同居者**：{'、'.join(cohabitants) if cohabitants else '无/未明确记录'}"
            )
            st.write(f"**饲养宠物**：{pget('是否饲养宠物')}")

    with sec2:
        with st.container(border=True):
            st.markdown("#### 👥 人际交往与社区关怀")
            st.write(
                f"**密切联系的朋友数**：{pget('您有多少关系密切，可以得到支持和帮助的朋友？（只选一项）')}"
            )
            st.write(f"**朋友关怀程度**：{pget('您和朋友：（只选一项）')}")
            st.write(f"**邻里互助与关怀**：{pget('您和邻居：（只选一项）')}")

    # Row 2: Family Support Matrix (Q37)
    with st.container(border=True):
        st.markdown("#### 👨‍👩‍👧‍👦 家庭成员支持矩阵 (SSRS Q37)")
        f_cols = st.columns(len(FAMILY_SUPPORT_ITEMS))
        badge_styles = {
            "全力支持": "green-badge",
            "一般": "blue-badge",
            "极少": "orange-badge",
            "无": "red-badge",
            "不适用": "gray-badge",
            "-": "gray-badge",
        }
        for col_ui, (label, _) in zip(f_cols, FAMILY_SUPPORT_ITEMS):
            with col_ui:
                val = format_value(person.get(f"家庭支持_{label}"))
                badge_type = badge_styles.get(val, "blue-badge")
                st.markdown(f"**{label}**")
                st.markdown(f":{badge_type}[{val}]")

    # Row 3: Coping, Confiding & Utilization
    sec3, sec4 = st.columns(2, gap="medium")
    with sec3:
        with st.container(border=True):
            st.markdown("#### 💡 求助模式与倾诉意愿")
            st.write(f"**倾诉意愿**：{pget('您遇到烦恼时会主动倾诉吗：（只选一项）')}")
            st.write(
                f"**最主要倾诉对象**：{pget('下列来源中哪一项是您遇到烦恼时最主要倾诉对象？（只选一项）')}"
            )
            st.write(
                f"**烦恼求助行为方式**：{pget('您遇到烦恼时的求助方式：（只选一项）')}"
            )
            st.write(
                f"**团体组织活动参与**：{pget('对于团体（如党组织、宗教组织、工会、学生会等）组织活动，您：（只选一项）')}"
            )

    with sec4:
        with st.container(border=True):
            st.markdown("#### 🆘 急难支持来源")
            obj_support = person.get("objective_support_list", [])
            subj_support = person.get("subjective_support_list", [])
            has_obj = pget(
                "过去，在您遇到急难情况时，曾经得到的经济支持和解决实际问题的帮助的来源有："
            )
            has_subj = pget("过去，在您遇到急难情况时，曾经得到的安慰和关心的来源有：")

            st.write(f"**经济/实际帮助来源**：`{has_obj}`")
            st.write(
                f"• 渠道：{'、'.join(obj_support) if obj_support else '无具体登记渠道'}"
            )

            st.write(f"**安慰/情感关心来源**：`{has_subj}`")
            st.write(
                f"• 渠道：{'、'.join(subj_support) if subj_support else '无具体登记渠道'}"
            )

# ---------------------------------------------------------
# TAB 5: Treatment Goals & Preferences
# ---------------------------------------------------------
with tab5:
    st.markdown("### 🎯 治疗目标与诉求")
    selected_goals = person.get("treatment_goals_list", [])

    st.write(
        f"**心理治疗目标**：{' | '.join(selected_goals) if selected_goals else '未明确选定'}"
    )
    st.write(f"**预约登记的治疗方式**：{pget('请选择您需要预约登记的治疗方式')}")
    st.write(f"**过去心理咨询经历**：{pget('过去心理咨询')}")
    st.info(
        f"{pget('其他需要备注说明的信息：', '无')}",
        title="**来访备注**",
        icon="🙋",
    )
    st.info(f"{pget('备注', '无')}", title="**治疗师备注**", icon="🧑‍⚕️")

# ---------------------------------------------------------
# Main View: Evaluation & Follow-up Workspace (Bottom Area)
# ---------------------------------------------------------
st.markdown("---")
st.markdown("### ✏️ 评估随访")

with st.form("edit_patient_form"):
    new_priority = st.checkbox(
        "优先安排",
        value=(safe_str(person.get("优先安排")) == "是"),
    )
    col_first, col_follow = st.columns(2, gap="large")

    with col_first:
        st.markdown("#### 📞 首访信息登记")
        new_first_therapist = st.text_input(
            "首访治疗师", value=safe_str(person.get("首访治疗师"))
        )
        new_first_date = st.date_input(
            "首访时间", value=parse_date(person.get("首访时间"))
        )
        new_first_outcome = st.selectbox(
            "首访情况",
            options=CONTACT_OUTCOMES,
            index=safe_index(CONTACT_OUTCOMES, person.get("首访情况")),
        )
        new_treatment_rec = st.multiselect(
            "治疗推荐",
            options=TREATMENT_OPTIONS,
            default=parse_multi(person.get("治疗推荐"), TREATMENT_OPTIONS),
            help="支持选择多个推荐治疗方式",
        )
        new_no_rec_reason = st.text_input(
            "未推荐说明", value=safe_str(person.get("未推荐说明"))
        )

    with col_follow:
        st.markdown("#### 🔄 回访信息登记")
        new_followup_therapist = st.text_input(
            "回访治疗师", value=safe_str(person.get("回访治疗师"))
        )
        new_followup_date = st.date_input(
            "回访时间", value=parse_date(person.get("回访时间"))
        )
        new_followup_outcome = st.selectbox(
            "回访情况",
            options=CONTACT_OUTCOMES,
            index=safe_index(CONTACT_OUTCOMES, person.get("回访情况")),
        )
        new_followup_notes = st.text_input(
            "回访治疗安排", value=safe_str(person.get("回访治疗安排"))
        )
        new_no_arr_reason = st.text_input(
            "未安排说明", value=safe_str(person.get("未安排说明"))
        )

    new_note = st.text_input("备注", value=safe_str(person.get("备注")))

    btn_col1, btn_col2 = st.columns([1, 3], vertical_alignment="center")
    with btn_col1:
        save_current = st.form_submit_button(
            "💾 保存当前修改", use_container_width=True
        )
    with btn_col2:
        st.caption("💡 提示：点击保存后数据将写入当前会话；可随时下载最新 Excel 文件。")

# ---- Save logic (runs on submit button click) ----
if save_current:
    raw_idx = int(person["_original_idx"])
    raw_df = st.session_state["raw_df"]
    updates = {
        "优先安排": "是" if new_priority else "",
        "首访治疗师": new_first_therapist,
        "首访时间": str(new_first_date) if new_first_date is not None else "",
        "首访情况": new_first_outcome,
        "治疗推荐": ", ".join(new_treatment_rec) if new_treatment_rec else "",
        "未推荐说明": new_no_rec_reason,
        "回访治疗师": new_followup_therapist,
        "回访时间": str(new_followup_date) if new_followup_date is not None else "",
        "回访情况": new_followup_outcome,
        "回访治疗安排": new_followup_notes,
        "未安排说明": new_no_arr_reason,
        "备注": new_note,
    }
    for col, val in updates.items():
        raw_df.at[raw_idx, col] = val
    st.session_state["_save_success"] = True
    st.rerun()

# Bottom Download button + Prev/Next navigation
_export_df = st.session_state["raw_df"]


def get_bottom_excel_bytes() -> bytes:
    buf = io.BytesIO()
    _export_df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


col_btm_prev, col_btm_dl, col_btm_next = st.columns(
    [1, 2, 1], vertical_alignment="center"
)

with col_btm_prev:
    st.button(
        "◀️ 上一位",
        key="btm_prev",
        on_click=step_patient,
        args=(-1,),
        use_container_width=True,
    )

with col_btm_dl:
    st.download_button(
        label="📥 下载更新后的完整 Excel 文件",
        data=get_bottom_excel_bytes,
        on_click="ignore",
        file_name=f"{datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8))).date().strftime('%Y%m%d')}_{st.session_state.get('_file_name', 'data.xlsx')}",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )

with col_btm_next:
    st.button(
        "▶️ 下一位",
        key="btm_next",
        on_click=step_patient,
        args=(1,),
        use_container_width=True,
    )
