import io
import pandas as pd
import streamlit as st

from mappings import (
    CONTACT_OUTCOMES,
    DIAGNOSIS_FIELDS,
    GAD_FIELDS,
    GAD_LABELS,
    PHQ_FIELDS,
    PHQ_LABELS,
    TEXT_TO_SCORE,
    TREATMENT_OPTIONS,
)
from preprocessing import load_raw_data, preprocess_data
from utils import (
    get_diagnoses,
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
# Navigation Callbacks
# ---------------------------------------------------------
def step_patient(step: int):
    curr_idx = name_options.index(st.session_state.dropdown_val)
    # Modulo (%) provides circular wrap-around:
    # - At end (idx + 1 == len), wraps to 0 (first patient)
    # - At start (0 - 1), wraps to len - 1 (last patient)
    new_idx = (curr_idx + step) % len(name_options)
    st.session_state.dropdown_val = name_options[new_idx]


def update_idx_from_dropdown():
    st.session_state.patient_idx = name_options.index(st.session_state.dropdown_val)


# ---------------------------------------------------------
# Main Execution Flow
# ---------------------------------------------------------
uploaded_file = st.sidebar.file_uploader("📂 选择数据文件", type=["csv", "xlsx"])

if not uploaded_file:
    st.info("👈 请在左侧侧边栏上传门诊预约登记表 (CSV / XLSX)。")
    st.stop()

# Store raw data in session state for the edit-and-save workflow
if (
    "raw_df" not in st.session_state
    or st.session_state.get("_file_name") != uploaded_file.name
):
    st.session_state["raw_df"] = load_raw_data(uploaded_file)
    st.session_state["_file_name"] = uploaded_file.name

df = preprocess_data(st.session_state["raw_df"])

# ------------ Sidebar filters-------------
st.sidebar.header("🔍 档案检索")

# Filter By Date
# 1. Convert column to datetime format
df["提交答卷时间"] = pd.to_datetime(df["提交答卷时间"])

# 2. Add a date range picker in the sidebar
date_range = st.sidebar.date_input(
    "📅 登记日期范围",
    value=(df["提交答卷时间"].min().date(), df["提交答卷时间"].max().date()),
)

# 3. Apply filter when both start and end dates are picked
if len(date_range) == 2:
    start_date, end_date = date_range

    filtered_df = df[
        (df["提交答卷时间"].dt.date >= start_date)
        & (df["提交答卷时间"].dt.date <= end_date)
    ]
else:
    filtered_df = df

# Filter By Treatment Type
treatment_col = "请选择您需要预约登记的治疗方式"
if treatment_col in filtered_df.columns:
    all_treatments = filtered_df[treatment_col].dropna().unique().tolist()
    selected_treatments = st.sidebar.multiselect(
        "🛋️ 预约治疗方式", options=all_treatments, default=all_treatments
    )
    if selected_treatments:
        filtered_df = filtered_df[filtered_df[treatment_col].isin(selected_treatments)]

# Filter By Sex
sex_col = "性别"
if sex_col in filtered_df.columns:
    all_sex = filtered_df[sex_col].dropna().unique().tolist()
    selected_sex = st.sidebar.multiselect("💁性别", options=all_sex, default=all_sex)
    if selected_sex:
        filtered_df = filtered_df[filtered_df[sex_col].isin(selected_sex)]

if filtered_df.empty:
    st.warning("⚠️ 当前筛选条件下未找到求诊者记录。")
    st.stop()


# ---- Patient Search & Prev/Next buttons----
# 1. Construct search box options
filtered_df["_label"] = (
    filtered_df["姓名（实名）"].fillna("未知").astype(str)
    + " ("
    + filtered_df["提交答卷时间"].dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    + ")"
)
name_options = filtered_df["_label"].tolist()

# 2. Initialize current patient index in session_state &
# ensure index stays within bounds if the filtered list shrinks
if (
    "dropdown_val" not in st.session_state
    or st.session_state.dropdown_val not in name_options
):
    st.session_state.dropdown_val = name_options[0]

# 3. Previous / Next Buttons Layout
col_prev, col_dropdown, col_next = st.columns([1, 4, 1], vertical_alignment="bottom")

with col_prev:
    st.button("◀️ 上一位", on_click=step_patient, args=(-1,))

with col_next:
    st.button("▶️ 下一位", on_click=step_patient, args=(1,))

# 4. Pull the patient profile when actively selected from dropdown
with col_dropdown:
    selected_label = st.selectbox(
        "🔍 选择/输入求诊者姓名（预约提交时间）",
        options=name_options,
        key="dropdown_val",
        on_change=update_idx_from_dropdown,
    )

# Active record
patient_idx = name_options.index(selected_label)
person = filtered_df.iloc[patient_idx]

st.caption(f"当前第 **{patient_idx + 1}** / **{len(name_options)}** 位求诊者")

# ---------------------------------------------------------
# Sidebar: Edit Form (placed after patient selection so we have `person`)
# ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("#### ✏️ 首访 / 回访信息登记")

with st.sidebar.form("edit_patient_form"):
    # ---- 首访 (first contact) ----
    st.markdown("**📞 首访**")
    new_first_therapist = st.text_input(
        "首访治疗师", value=safe_str(person.get("首访治疗师"))
    )
    new_first_date = st.date_input("首访时间", value=parse_date(person.get("首访时间")))
    new_first_outcome = st.selectbox(
        "首访情况",
        options=CONTACT_OUTCOMES,
        index=safe_index(CONTACT_OUTCOMES, person.get("首访情况")),
    )
    new_treatment_rec = st.multiselect(
        "治疗推荐",
        options=TREATMENT_OPTIONS,
        default=parse_multi(person.get("治疗推荐"), TREATMENT_OPTIONS),
    )
    new_no_rec_reason = st.text_input(
        "未推荐说明", value=safe_str(person.get("未推荐说明"))
    )

    st.markdown("---")

    # ---- 回访 (follow-up) ----
    st.markdown("**🔄 回访**")
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

    submitted = st.form_submit_button("💾 保存修改", use_container_width=True)

# ---- Save logic (runs once on the rerun triggered by the submit button) ----
if submitted:
    raw_idx = int(person["_original_idx"])
    raw_df = st.session_state["raw_df"]

    raw_df.at[raw_idx, "首访治疗师"] = new_first_therapist
    raw_df.at[raw_idx, "首访时间"] = (
        str(new_first_date) if new_first_date is not None else ""
    )
    raw_df.at[raw_idx, "首访情况"] = new_first_outcome
    raw_df.at[raw_idx, "治疗推荐"] = (
        ", ".join(new_treatment_rec) if new_treatment_rec else ""
    )
    raw_df.at[raw_idx, "未推荐说明"] = new_no_rec_reason
    raw_df.at[raw_idx, "回访治疗师"] = new_followup_therapist
    raw_df.at[raw_idx, "回访时间"] = (
        str(new_followup_date) if new_followup_date is not None else ""
    )
    raw_df.at[raw_idx, "回访情况"] = new_followup_outcome
    raw_df.at[raw_idx, "回访治疗安排"] = new_followup_notes

    st.cache_data.clear()
    st.session_state["_save_success"] = True
    st.rerun()

# Show success feedback after rerun
if st.session_state.pop("_save_success", False):
    st.sidebar.success("✅ 修改已保存！请点击下方按钮下载更新后的文件。")

# ---- Download updated file ----
if "raw_df" in st.session_state:
    _buf = io.BytesIO()
    st.session_state["raw_df"].to_excel(_buf, index=False, engine="openpyxl")
    _buf.seek(0)
    st.sidebar.download_button(
        label="📥 下载更新后的文件",
        data=_buf,
        file_name=f"updated_{st.session_state.get('_file_name', 'data.xlsx')}",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ---------------------------------------------------------
# Main View: Structured Sections
# ---------------------------------------------------------

# Patient Demo Banner
phone_number = phone_num_slicer(person.get("联系电话", "-"))
st.title(
    f"👤 {person.get('姓名（实名）', '未知')} | \
                {person.get('年龄', '未填')} 岁| \
                {person.get('性别', '未填')} |\
                📞{phone_number}\
                :violet-badge[💬 {person.get('请选择您需要预约登记的治疗方式')}]\
                :blue-badge[{person.get('电话评估治疗师', '-')}]"
)

# Repeat Submission Alert & First Entry Notice
total_submissions = int(person.get("总提交次数", 1))
current_submission = int(person.get("提交次数", 1))
first_entry_time = person.get("首次登记时间")
last_entry_time = person.get("最新登记时间")
current_progress = person.get("当前治疗进展", "-")

# Format first entry date cleanly
if pd.notna(first_entry_time):
    first_entry_str = pd.to_datetime(first_entry_time).strftime("%Y-%m-%d %H:%M")
else:
    first_entry_str = "未知"

if total_submissions > 1:
    st.info(
        f"📋 **多次登记提示**：该求诊者在数据库中共有 **{total_submissions}** 次提交记录（当前查看的是第 **{current_submission}** 次）。\n\n"
        f"**初次登记时间**：`{first_entry_str}`\n\n"
        f"**当前治疗进展**：`{current_progress}` （`{last_entry_time}`）"
    )
else:
    st.info(f"**当前治疗进展**：`{current_progress}` （`{last_entry_time}`）")

# Key Metrics
main = st.container()

# Diagnosis badges
diagnoses_list = person.get("diagnoses_list", [])
if not diagnoses_list:
    diagnosis_cols = df.columns[DIAGNOSIS_FIELDS[0] : DIAGNOSIS_FIELDS[1]]
    diagnoses_list = get_diagnoses(diagnosis_cols, person)

display = ""
for d in diagnoses_list:
    display += f":red-badge[{d}] "
main.write(f"{display}")

# Scale Metrics
m1, m2, m3 = main.columns(3)

phq_severity = person.get("PHQ_Severity", "")
phq_label = f"抑郁筛查量表 (PHQ-9) · {phq_severity}" if phq_severity else "抑郁筛查量表 (PHQ-9)"
m1.metric(
    label=phq_label,
    value=f"{int(person['PHQ_Total'])} / 27",
)

gad_severity = person.get("GAD_Severity", "")
gad_label = f"广泛性焦虑量表 (GAD-7) · {gad_severity}" if gad_severity else "广泛性焦虑量表 (GAD-7)"
m2.metric(
    label=gad_label,
    value=f"{int(person['GAD_Total'])} / 21",
)

isi_severity = person.get("ISI_Severity", "")
isi_label = f"失眠严重程度量表 (ISI) · {isi_severity}" if isi_severity else "失眠严重程度量表 (ISI)"
m3.metric(label=isi_label, value=f"{int(person['ISI_TOTAL'])} / 28")

# Risk indicators (Self-harm / Suicide)
active_risks = person.get("crisis_risk_flags", [])
if not active_risks:
    risk_cols = [c for c in df.columns if "25(" in c]
    active_risks = [
        c.replace("25(", "").replace(")", "")
        for c in risk_cols
        if person.get(c) == 1 or person.get(c) == "是"
    ]

if active_risks:
    main.error(f"⚠️ 风险预警指标: {', '.join(active_risks)}")

# Organize 112 columns into Tabs
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
        st.write(f"**姓名**：{person.get('姓名（实名）', '-')}")
        st.write(f"**身份证号**：{person.get('求诊者身份证号', '-')}")
        st.write(f"**联系电话**：{person.get('联系电话', '-')}")
        st.write(f"**常住地**：{person.get('您的常住地为', '-')}")
        st.write(f"**户籍地**：{person.get('您的户籍所在地', '-')}")

    with col2:
        st.markdown("### 🎓 社会人口学资料")
        st.write(f"**教育水平**：{person.get('教育水平', '-')}")
        st.write(f"**职业**：{person.get('职业', '-')}")
        st.write(f"**年级**：{person.get('年级', '-')}")
        st.write(f"**休学/离职状态**：{person.get('目前是否已经休学/休假或离职', '-')}")
        st.write(
            f"**婚姻/生育状态**：{person.get('婚姻状态', '-')}, {person.get('生育状态', '-')} (孩子数: {person.get('孩子个数', '-')})"
        )

    with col3:
        st.markdown("### 📞 紧急联系人")
        st.write(f"**紧急联系人**：{person.get('紧急联系人的姓名', '-')}")
        st.write(f"**关系**：{person.get('紧急联系人与来访的关系：', '-')}")
        st.write(f"**联系电话**：{person.get('紧急联系人电话（手机号）', '-')}")

# ---------------------------------------------------------
# TAB 2: Clinical & Medication History
# ---------------------------------------------------------
with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🏥 诊疗背景")
        st.write(f"**病程（月）**：{person.get('病程（月）', '-')}")
        st.write(f"**首次来院年份**：{person.get('首次来我院就诊年份', '-')}")
        st.write(f"**本院就诊经历**：{person.get('是否曾在本院心理咨询门诊就诊', '-')}")
        st.write(
            f"**重大生活事件**：{person.get('半年内是否经历重大生活事件', '-')} ({person.get('请注明具体事件', '无说明')})"
        )
        st.write(f"**家族史**：{person.get('是否有精神/心理疾病家族史', '-')}")
        st.write(f"**躯体疾病**：{person.get('是否有躯体疾病', '-')}")

    with col2:
        st.markdown("### 💊 药物使用与安全状态")
        st.write(f"**目前是否服药**：{person.get('目前是否在服用精神科药物', '-')}")
        st.write(
            f"**药物名称/时间/剂量**：{person.get('服用药物名称，服用时间，剂量', '-')}"
        )
        st.write(f"**未服药情况**：{person.get('未服药情况', '-')}")

        # Symptoms list
        symptoms_cols = [c for c in df.columns if "19(" in c]
        present_symptoms = [
            c.replace("19(", "").replace(")", "")
            for c in symptoms_cols
            if person.get(c) == 1 or person.get(c) == "是"
        ]
        present_symptoms = person.get("diagnoses_list")
        if not present_symptoms:
            symptoms_cols = [c for c in df.columns if "19(" in c]
            present_symptoms = [
                c.replace("19(", "").replace(")", "")
                for c in symptoms_cols
                if person.get(c) == 1 or person.get(c) == "是"
            ]
        st.write(
            f"**当前主诉/症状**：{', '.join(present_symptoms) if present_symptoms else '无特异记录'}"
        )

# ---------------------------------------------------------
# TAB 3: Scales (PHQ-9, GAD-7, ISI)
# ---------------------------------------------------------
with tab3:
    phq_cols = df.columns[PHQ_FIELDS[0] : PHQ_FIELDS[1]]
    gad_cols = df.columns[GAD_FIELDS[0] : GAD_FIELDS[1]]
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

    # Raw option text mapping back to scores (0..3)
    phq_scores = [TEXT_TO_SCORE.get(person[c], 0) for c in phq_cols]
    gad_scores = [TEXT_TO_SCORE.get(person[c], 0) for c in gad_cols]
    # Use pre-computed item scores from pipeline (0..3)
    phq_scores = [int(person.get(f"_phq_score_{i}", 0)) for i in range(len(PHQ_LABELS))]
    gad_scores = [int(person.get(f"_gad_score_{i}", 0)) for i in range(len(GAD_LABELS))]

    st.markdown("### 📝 抑郁与焦虑自评（PHQ-9 & GAD-7）")
    c1, c2 = st.columns(2, gap="medium", border=True)
    with c1:
        plot_scale_breakdown(
            PHQ_LABELS, phq_scores, max_score=3, title="PHQ-9 抑郁症状条目得分"
        )
        st.write(f"#### PHQ总分：{person.get('PHQ_Total', '-')}")
        phq_sev = person.get("PHQ_Severity", "")
        phq_sev_str = f" ({phq_sev})" if phq_sev else ""
        st.write(f"#### PHQ总分：{person.get('PHQ_Total', '-')}{phq_sev_str}")
        st.markdown("#### PHQ-9 项目摘要")
        for c in phq_cols[:9]:
            st.write(f"• **{c.split('—')[-1]}**: {person.get(c, '-')}")

    with c2:
        plot_scale_breakdown(
            GAD_LABELS, gad_scores, max_score=3, title="GAD-7 焦虑症状条目得分"
        )
        st.write(f"#### GAD总分：{person.get('GAD_Total', '-')}")
        gad_sev = person.get("GAD_Severity", "")
        gad_sev_str = f" ({gad_sev})" if gad_sev else ""
        st.write(f"#### GAD总分：{person.get('GAD_Total', '-')}{gad_sev_str}")
        st.markdown("#### GAD-7 项目摘要")
        for c in gad_cols[:7]:
            st.write(f"• **{c.split('—')[-1]}**: {person.get(c, '-')}")

# ---------------------------------------------------------
# TAB 4: Social Support Network
# ---------------------------------------------------------
with tab4:
    st.markdown("### 🤝 社会支持评估")
    st.write(
        f"**密切联系的朋友数**：{person.get('您有多少关系密切，可以得到支持和帮助的朋友？（只选一项）', '-')}"
    )
    st.write(
        f"**倾诉意愿**：{person.get('您遇到烦恼时会主动倾诉吗：（只选一项）', '-')} | **主要倾诉对象：** {person.get('下列来源中哪一项是您遇到烦恼时最主要倾诉对象？（只选一项）', '-')}"
    )
    obj_support = person.get("objective_support_list", [])
    subj_support = person.get("subjective_support_list", [])
    if obj_support:
        st.write(f"**急难经济/实际支持来源**：{'、'.join(obj_support)}")
    if subj_support:
        st.write(f"**急难安慰/关心支持来源**：{'、'.join(subj_support)}")

# ---------------------------------------------------------
# TAB 5: Treatment Goals & Preferences
# ---------------------------------------------------------
with tab5:
    st.markdown("### 🎯 治疗目标与诉求")
    goal_cols = [c for c in df.columns if "目标(" in c]
    selected_goals = [
        c.replace("目标(", "").replace(")", "") for c in goal_cols if person.get(c) == 1
    ]
    selected_goals = person.get("treatment_goals_list")
    if not selected_goals:
        goal_cols = [c for c in df.columns if "目标(" in c]
        selected_goals = [
            c.replace("目标(", "").replace(")", "") for c in goal_cols if person.get(c) == 1
        ]

    st.write(
        f"**心理治疗目标**：{' | '.join(selected_goals) if selected_goals else '未明确选定'}"
    )
    st.write(
        f"**预约登记的治疗方式**：{person.get('请选择您需要预约登记的治疗方式', '-')}"
    )
    st.write(f"**过去心理咨询经历**：{person.get('过去心理咨询', '-')}")
    st.write(f"**电话评估治疗师**：:blue-badge[{person.get('电话评估治疗师', '-')}]")
    st.info(f"**其他备注信息**：{person.get('其他需要备注说明的信息：', '无')}")
