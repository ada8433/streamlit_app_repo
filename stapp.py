import streamlit as st
import pandas as pd
import datetime
import altair as alt

# Page setup
st.set_page_config(page_title="门诊预约Dashboard", page_icon="📋", layout="wide")

# ---------------------------------------------------------
# Dictionary
# ---------------------------------------------------------
# MCQs
CHOICE_MAPS = {
    "填写者": {"1": "求诊者本人", "2": "其他（请说明您与求诊人的关系）"},
    "性别": {"1": "男", "2": "女"},
    "您的常住地为": {"1": "上海", "2": "其他"},
    "教育水平": {
        "1": "高中及以下",
        "2": "中专/大专",
        "3": "本科",
        "4": "硕士",
        "5": "博士及以上",
    },
    "职业": {
        "1": "政府/事业单位工作人员",
        "2": "公司普通职员",
        "3": "企事业、政府高级管理人员",
        "4": "工人",
        "5": "医护人员",
        "6": "其他专业人士（如教师/律师/记者等）",
        "7": "警察/军人",
        "8": "农林牧渔劳动者",
        "9": "个体/自由职业",
        "10": "学生",
        "11": "退休",
        "12": "无业",
    },
    "年级": {
        "1": "小学",
        "2": "初中",
        "3": "高中",
        "4": "大学",
        "5": "硕士",
        "6": "博士",
    },
    "婚姻状态": {"1": "单身", "2": "未婚", "3": "已婚", "4": "离婚", "5": "丧偶"},
    "主要同居者": {
        "1": "独居",
        "2": "母父",
        "3": "子女",
        "4": "伴侣/配偶",
        "5": "兄弟姐妹",
        "6": "外祖母父",
        "7": "其他",
    },
    "诊断": {
        "1": "抑郁",
        "2": "焦虑",
        "3": "失眠",
        "4": "强迫",
        "5": "双相",
        "6": "精神分裂症",
        "7": "其他",
    },
    "未服药情况": {
        "1": "医生未建议",
        "2": "服药顾虑未服药",
        "3": "已自行停药",
        "4": "遵医嘱停药",
    },
    "是否有以下想法或行为": {
        "1": "无",
        "2": "自伤意念",
        "3": "自伤行为",
        "4": "自杀意念",
        "5": "自杀想法",
    },
    "您有多少关系密切，可以得到支持和帮助的朋友？（只选一项）": {
        "1": "0",
        "2": "1-2个",
        "3": "3-5个",
        "4": "6个或6个以上",
    },
    "近一年来居住情况": {
        "1": "远离家人，且独居一室",
        "2": "住处经常变动，多数时间和陌生人住在一起",
        "3": "和同学、同事或朋友住在一起",
        "4": "和家人住在一起",
    },
    "您遇到烦恼时会主动倾诉吗：（只选一项）": {
        "1": "从不向任何人倾诉",
        "2": "被询问会倾诉",
        "3": "会主动倾诉",
    },
    "下列来源中哪一项是您遇到烦恼时最主要倾诉对象？（只选一项）": {
        "1": "性缘伴侣",
        "2": "家人",
        "3": "朋友",
        "4": "同事",
        "5": "领导",
        "6": "党团工会等",
        "7": "宗教、社会团体等",
        "8": "其它",
    },
    "请选择您需要预约登记的治疗方式": {"1": "团体", "2": "个体", "3": "家庭"},
    "首次来我院就诊年份": {
        "1": "2021",
        "2": "2020",
        "3": "2019",
        "4": "2018",
        "5": "2017",
        "6": "2016",
        "7": "2015",
        "8": "2014",
        "9": "2013",
        "10": "2012",
        "11": "2011",
        "12": "2010",
        "13": "2009",
        "14": "2008",
        "15": "2007",
        "16": "2006",
        "17": "2005",
        "18": "2004",
        "19": "2003",
        "20": "2002",
        "21": "2001",
        "22": "2000",
        "23": "1999",
        "24": "1998",
        "25": "1997",
        "26": "1996",
        "27": "1995",
        "28": "1994",
        "29": "1993",
        "30": "1992",
        "31": "1991",
        "32": "1990",
        "33": "1990以前",
        "34": "2022",
        "35": "2023",
        "36": "2024",
        "37": "2025",
        "38": "2026",
    },
}

# YES_OR_NO
YES_NO_MAP = {1: "是", 2: "否"}

YES_NO_FIELDS = [
    "目前是否已经休学/休假或离职",
    "生育状态",
    "半年内是否经历重大生活事件",
    "是否饲养宠物",
    "是否曾在本院心理咨询门诊就诊",
    "目前是否在服用精神科药物",
    "是否有精神/心理疾病家族史",
    "是否有躯体疾病",
    "过去心理咨询",
]

# LIKERT_STYLE
FREQUENCY_MAP = {1: "没有", 2: "有几天", 3: "一半以上时间", 4: "几乎每天"}

SEVERITY_MAP = {1: "无", 2: "轻度", 3: "中度", 4: "重度", 5: "极重度"}

SATISFACTION_MAP = {
    1: "非常满意",
    2: "满意",
    3: "不太满意",
    4: "不满意",
    5: "非常不满意",
}

TEXT_TO_SCORE = {
    "没有": 0,
    "完全不会": 0,
    "0": 0,
    0: 0,
    "有几天": 1,
    "好几天": 1,
    "1": 1,
    1: 1,
    "一半以上时间": 2,
    "一半以上的时间": 2,
    "2": 2,
    2: 2,
    "几乎每天": 3,
    "3": 3,
    3: 3,
}
# PHQ-9 Items
phq_labels = [
    "1. 兴趣减退",
    "2. 心情低落",
    "3. 睡眠困扰",
    "4. 疲劳乏力",
    "5. 食欲改变",
    "6. 自责内疚",
    "7. 专注困难",
    "8. 动作迟缓/烦躁",
    "9. 自伤意念",
]
# GAD-7 Items
gad_labels = [
    "1. 紧张急切",
    "2. 无法控制担忧",
    "3. 担忧过多",
    "4. 难以放松",
    "5. 不安坐立难安",
    "6. 易怒急躁",
    "7. 恐惧感",
]
PHQ_FIELDS = [49, 58]
GAD_FIELDS = [58, 65]
ISI_FIELDS = [65, 72]


# ---------------------------------------------------------
# Preprocess and load adta
# ---------------------------------------------------------
# Preprocess function
@st.cache_data
def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    # Cleans data types and maps coded numerical keys to readable text.
    df = df.copy()

    # Cast IDs and phone numbers to string to preserve leading zeros
    string_cols = ["联系电话", "求诊者身份证号", "紧急联系人电话（手机号）"]
    for col in string_cols:
        if col in df.columns:
            df[col] = df[col].astype(str)

    # calculate sum scores for survey
    phq_cols = df.columns[PHQ_FIELDS[0] : PHQ_FIELDS[1]]
    gad_cols = df.columns[GAD_FIELDS[0] : GAD_FIELDS[1]]
    isi_cols = df.columns[ISI_FIELDS[0] : ISI_FIELDS[1]]
    df["PHQ_Total"] = (
        df[phq_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) - 9
    )
    df["GAD_Total"] = (
        df[gad_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) - 7
    )
    df["ISI_TOTAL"] = (
        df[isi_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) - 7
    )

    # Map number key to readable values from dictionary

    for column, mapping in CHOICE_MAPS.items():
        if column in df.columns:
            df[column] = df[column].astype(str).map(mapping)

    for column in YES_NO_FIELDS:
        if column in df.columns:
            df[column] = df[column].astype(float).map(YES_NO_MAP)

    df[phq_cols] = df[phq_cols].replace(FREQUENCY_MAP)
    df[gad_cols] = df[gad_cols].replace(FREQUENCY_MAP)

    return df


# Load dataset
# @st.cache_data
def load_data(uploaded_file):
    # Read the data based on file type
    if uploaded_file.name.endswith(".csv"):
        raw_df = pd.read_csv(uploaded_file)
    else:
        raw_df = pd.read_excel(uploaded_file)
    # raw_df = pd.read_excel(file_path)
    return preprocess_data(raw_df)


# Load file
try:
    # Create the file chooser widget
    uploaded_file = st.file_uploader("选择文件上传", type=["csv", "xlsx"])
    if uploaded_file is not None:
        df = load_data(uploaded_file)
except Exception as e:
    st.error(f"无法读取文件, {e}")
    st.stop()


# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
# get diagnoses
def get_diagnoses(diagnosis_columns, person):
    prev_diagnoses = []
    for label in diagnosis_columns:
        if person.get(label) == 1:
            prev_diagnoses.append(label.split("(")[1].split(")")[0].strip())
    return prev_diagnoses


# plot PHQ and GAD charts
def plot_scale_breakdown(item_names, scores, max_score=3, title="条目明细分布"):
    # 1. Build a clean plotting DataFrame
    chart_data = pd.DataFrame({"条目": item_names, "得分": scores})

    # 2. Build horizontal bar chart using Altair
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

    # 3. Add score numbers on top of bars
    text = chart.mark_text(align="left", baseline="middle", dx=3).encode(text="得分:Q")

    return st.altair_chart(chart + text, width="stretch")


# Previous/Next buttons
def next_patient():
    if st.session_state.patient_idx + 1 >= len(name_options):
        st.session_state.patient_idx = 0
    else:
        st.session_state.patient_idx += 1


def previous_patient():
    if st.session_state.patient_idx > 0:
        st.session_state.patient_idx -= 1


# slice phone numbers into easy-to-read format
def phone_num_slicer(phone):
    phone_slice = [phone[:3], phone[3:7], phone[7:]]
    return " ".join(phone_slice)


# ---------------------------------------------------------
# Filter & Search
# ---------------------------------------------------------

# Sidebar: filter
st.sidebar.header("🔍 档案检索")
try:
    # ------------Filter By Date---------------
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

    # ------------Filter By Treatment Type----------
    treatment_col = "请选择您需要预约登记的治疗方式"
    if treatment_col in filtered_df.columns:
        all_treatments = filtered_df[treatment_col].dropna().unique().tolist()
        selected_treatments = st.sidebar.multiselect(
            "🛋️ 预约治疗方式", options=all_treatments, default=all_treatments
        )
        if selected_treatments:
            filtered_df = filtered_df[
                filtered_df[treatment_col].isin(selected_treatments)
            ]

    # ------------Filter By Sex----------
    sex_col = "性别"
    if sex_col in filtered_df.columns:
        all_sex = filtered_df[sex_col].dropna().unique().tolist()
        selected_sex = st.sidebar.multiselect(
            "💁性别", options=all_sex, default=all_sex
        )
        if selected_sex:
            filtered_df = filtered_df[filtered_df[sex_col].isin(selected_sex)]

    if filtered_df.empty:
        st.sidebar.warning("该日期范围内无求诊者记录")
    else:
        # Main page: search
        # 2. Initialize current patient index in session_state
        name_options = (
            filtered_df["姓名（实名）"].astype(str)
            + " ("
            + df["提交答卷时间"].astype(str)
            + ")"
        ).tolist()
        if "patient_idx" not in st.session_state:
            st.session_state.patient_idx = 0

        # Ensure index stays within bounds if the filtered list shrinks
        if st.session_state.patient_idx >= len(name_options):
            st.session_state.patient_idx = 0

        # 3. Previous / Next Buttons Layout
        col_prev, col_dropdown, col_next = st.columns(
            [1, 5, 1], vertical_alignment="bottom"
        )

        with col_prev:
            if st.button(
                "上一位",
                on_click=previous_patient,
            ):
                st.rerun()

        with col_next:
            if st.button(
                "下一位",
                on_click=next_patient,
            ):
                st.rerun()

        with col_dropdown:
            selected_name = st.selectbox(
                "🔍 选择/输入求诊者姓名（预约提交时间）",
                options=name_options,
                index=st.session_state.patient_idx,
            )
            if selected_name:
                st.session_state.patient_idx = name_options.index(selected_name)
                person = filtered_df[
                    filtered_df["姓名（实名）"].astype(str)
                    + " ("
                    + df["提交答卷时间"].astype(str)
                    + ")"
                    == selected_name
                ].iloc[0]
        # 4. Pull the active person record
        person = filtered_df.iloc[st.session_state.patient_idx]

        st.caption(
            f"当前第 **{st.session_state.patient_idx + 1}** / **{len(name_options)}** 位求诊者"
        )

except Exception as e:
    st.info(f"{e}")

# ---------------------------------------------------------
# Main View: Structured Sections
# ---------------------------------------------------------
try:
    # Key Highlights Banner
    phone_number = phone_num_slicer(person.get("联系电话", "-"))
    st.title(
        f"👤 {person.get('姓名（实名）', '未知')} | \
                    {person.get('年龄', '未填')} 岁| \
                    {person.get('性别', '未填')} |\
                    {phone_number}\
                    :violet-badge[💬 {person.get('请选择您需要预约登记的治疗方式')}]\
                    :blue-badge[{person.get('电话评估治疗师', '-')}]"
    )

    main = st.container()

    diagnoses_list = get_diagnoses(df.columns[30:37], person)
    display = ""
    for d in diagnoses_list:
        display += f":red-badge[{d}] "
    main.write(f"{display}")

    col1, col2, col3 = main.columns(3)

    col1.metric(
        label="抑郁筛查量表 (PHQ-9)",
        value=f"{int(person['PHQ_Total'])} / 27",
    )
    col2.metric(
        label="广泛性焦虑量表 (GAD-7)",
        value=f"{int(person['GAD_Total'])} / 21",
    )

    col3.metric(label="失眠严重程度量表 (ISI)", value=f"{int(person['ISI_TOTAL'])}/28")

    # Check for safety / risk indicators (Self-harm / Suicide)
    risk_cols = [c for c in df.columns if "25(" in c]
    active_risks = [
        c.replace("25(", "").replace(")", "")
        for c in risk_cols
        if person.get(c) == 1 or person.get(c) == "是"
    ]

    if any(r in ["自伤意念", "自伤行为", "自杀意念", "自杀想法"] for r in active_risks):
        main.error(f"⚠️ 风险预警指标: {', '.join(active_risks)}")

    # 电话评估后的信息变更
    st.markdown("---")
    st.markdown("### 📑 电话评估信息")
    edited_df = st.data_editor(
        df.loc[
            [person.name],
            df.columns[119:124],
        ],
        hide_index=True,
        num_rows="fixed",
    )

    # if st.button("提交", type="primary", width="stretch"):
    #     df.update(edited_df)
    #     df.to_excel(uploaded_file.name, index=False)

    # Update only the edited cells in the main dataframe

    # Save back to disk

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
            st.write(
                f"**休学/离职状态**：{person.get('目前是否已经休学/休假或离职', '-')}"
            )
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
            st.write(
                f"**本院就诊经历**：{person.get('是否曾在本院心理咨询门诊就诊', '-')}"
            )
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
            st.write(
                f"**当前主诉/症状**：{', '.join(present_symptoms) if present_symptoms else '无特异记录'}"
            )

    # ---------------------------------------------------------
    # TAB 3: Scales (PHQ-9, GAD-7, ISI)
    # ---------------------------------------------------------
    with tab3:
        phq_cols = df.columns[PHQ_FIELDS[0] : PHQ_FIELDS[1]]
        gad_cols = df.columns[GAD_FIELDS[0] : GAD_FIELDS[1]]

        # Raw option text mapping back to scores (0..3)
        phq_scores = [TEXT_TO_SCORE.get(person[c], 0) for c in phq_cols]
        gad_scores = [TEXT_TO_SCORE.get(person[c], 0) for c in gad_cols]
        st.markdown("### 📝 抑郁与焦虑自评（PHQ-9 & GAD-7）")
        c1, c2 = st.columns(2, gap="medium", border=True)
        with c1:
            plot_scale_breakdown(
                phq_labels, phq_scores, max_score=3, title="PHQ-9 抑郁症状条目得分"
            )
            st.write(f"#### PHQ总分：{person.get('PHQ_Total', '-')}")
            st.markdown("#### PHQ-9 项目摘要")
            for c in phq_cols[:9]:
                st.write(f"• **{c.split('—')[-1]}**: {person.get(c, '-')}")

        with c2:
            plot_scale_breakdown(
                gad_labels, gad_scores, max_score=3, title="GAD-7 焦虑症状条目得分"
            )
            st.write(f"#### GAD总分：{person.get('GAD_Total', '-')}")
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

    # ---------------------------------------------------------
    # TAB 5: Treatment Goals & Preferences
    # ---------------------------------------------------------
    with tab5:
        st.markdown("### 🎯 治疗目标与诉求")
        goal_cols = [c for c in df.columns if "目标(" in c]
        selected_goals = [
            c.replace("目标(", "").replace(")", "")
            for c in goal_cols
            if person.get(c) == 1
        ]

        st.write(
            f"**心理治疗目标**：{' | '.join(selected_goals) if selected_goals else '未明确选定'}"
        )
        st.write(
            f"**预约登记的治疗方式**：{person.get('请选择您需要预约登记的治疗方式', '-')}"
        )
        st.write(f"**过去心理咨询经历**：{person.get('过去心理咨询', '-')}")
        st.write(
            f"**电话评估治疗师**：:blue-badge[{person.get('电话评估治疗师', '-')}]"
        )
        st.info(f"**其他备注信息**：{person.get('其他需要备注说明的信息：', '无')}")
except Exception as e:
    st.warning(f"请检查日期，该日期范围内无求诊者记录 {e}")
