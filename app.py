import streamlit as st
import pandas as pd
import datetime

# ---------------------------------------------------------
# [설정] 페이지 및 스타일
# ---------------------------------------------------------
st.set_page_config(page_title="최종 UI 시안 (V3)", page_icon="🎨", layout="wide")

PROJECT_CATEGORIES = ["CTA 공부", "업무/사업", "건강/운동", "기타/생활"]
CATEGORY_COLORS = {"CTA 공부": "blue", "업무/사업": "orange", "건강/운동": "green", "기타/생활": "gray"}

# ---------------------------------------------------------
# [팝업 1] 목표(D-Day) 관리
# ---------------------------------------------------------
@st.dialog("🎯 목표(D-Day) 관리")
def mock_goal_popup():
    st.caption("프로젝트별 목표를 관리합니다. 가장 급한 목표가 메인에 뜹니다.")
    
    # 목록 예시
    goals = [
        ("업무/사업", "카이론 앱 개발", "2025-12-07"),
        ("CTA 공부", "1차 시험", "2026-04-25"),
        ("건강/운동", "체중 감량", "2025-12-31")
    ]
    
    for cat, name, date in goals:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.5, 2, 0.8], vertical_alignment="center")
            c1.markdown(f":{CATEGORY_COLORS.get(cat, 'gray')}[**[{cat}]**]")
            c2.write(f"{name} ({date})")
            c3.button("삭제", key=f"del_g_{name}")

    st.markdown("---")
    st.write("###### ➕ 새 목표 추가")
    with st.form("goal_form"):
        c1, c2 = st.columns(2)
        c1.selectbox("카테고리", PROJECT_CATEGORIES)
        c2.text_input("목표명")
        st.date_input("목표 날짜")
        st.form_submit_button("목표 등록", type="primary")

# ---------------------------------------------------------
# [팝업 2] Inbox(생각 보관함)
# ---------------------------------------------------------
@st.dialog("📥 Inbox (생각 보관함)")
def mock_inbox_popup():
    st.caption("할 일이나 아이디어를 임시로 보관하세요.")
    
    tab1, tab2 = st.tabs(["➕ 추가하기", "📋 목록 (2)"])
    
    with tab1:
        with st.form("inbox_form"):
            c1, c2 = st.columns([1, 2])
            c1.selectbox("카테고리", PROJECT_CATEGORIES)
            c2.text_input("내용")
            st.text_area("메모/링크", height=80)
            st.form_submit_button("보관함에 저장", type="primary")
            
    with tab2:
        for i in range(2):
            with st.container(border=True):
                c1, c2 = st.columns([4, 1], vertical_alignment="center")
                c1.markdown("**[업무] 디자인 시안 피드백 정리**")
                c1.caption("참고: 카톡 내용 확인하기")
                c2.button("삭제", key=f"inb_del_{i}")

# ---------------------------------------------------------
# [팝업 3] 템플릿(루틴) 관리
# ---------------------------------------------------------
@st.dialog("💾 템플릿(루틴) 관리")
def mock_template_popup():
    st.caption("자주 쓰는 하루 일과를 세트로 만드세요.")
    
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    c1.selectbox("편집할 템플릿", ["평일 루틴 (기본)", "주말 몰입", "+ 새 템플릿 만들기"])
    c2.button("삭제", type="primary")
    
    st.markdown("---")
    st.write("###### '평일 루틴' 구성")
    
    # 예시 데이터
    dummy_routine = [
        ("08:00", "CTA 공부", "아침 백지 복습"),
        ("13:00", "건강/운동", "점심 식사"),
        ("19:00", "기타/생활", "저녁 식사")
    ]
    
    # 헤더
    h1, h2, h3, h4 = st.columns([1, 1.2, 3, 0.5])
    h1.caption("시간")
    h2.caption("카테고리")
    h3.caption("내용")
    
    for t_time, t_cat, t_main in dummy_routine:
        r1, r2, r3, r4 = st.columns([1, 1.2, 3, 0.5], vertical_alignment="center")
        r1.text(t_time)
        r2.text(t_cat)
        r3.write(f"**{t_main}**")
        r4.button("x", key=f"rt_{t_time}")
        
    with st.expander("➕ 항목 추가"):
        e1, e2 = st.columns([1, 1.5])
        e1.time_input("시간")
        e2.selectbox("카테고리", PROJECT_CATEGORIES, key="t_add_cat")
        st.text_input("내용", key="t_add_main")
        st.button("리스트에 추가", use_container_width=True)


# =========================================================
# [UI] 사이드바 Layout
# =========================================================
with st.sidebar:
    st.title("🗂️ 메뉴")
    st.button("📝 Daily Planner", use_container_width=True, type="primary")
    st.button("📊 Dashboard", use_container_width=True)
    
    st.markdown("---")
    
    # 팝업 트리거 버튼들
    if st.button("📥 Inbox 관리 (2)", use_container_width=True):
        mock_inbox_popup()
    
    if st.button("💾 템플릿 관리", use_container_width=True):
        mock_template_popup()

    st.markdown("---")
    st.subheader("🎯 목표")
    
    # 목표 리스트 간략 표시
    st.info("**[업무] 카이론 앱 개발**\nD-1 (12/07)")
    st.caption("**[공부] 1차 시험** (D-140)")
    
    if st.button("목표 설정 팝업", use_container_width=True):
        mock_goal_popup()
        
    st.markdown("---")
    with st.expander("⚙️ 고급 설정"):
        st.text_input("텔레그램 ID", value="12345678")
        st.button("ID 저장")


# =========================================================
# [UI] 메인 화면 Layout (Daily View)
# =========================================================

# 1. 헤더 (가장 급한 목표 강조)
st.title("📝 2025-12-06 (카이론 앱 개발 D-1)")

# 2. 목표 현황판 (가로 배치)
c1, c2, c3, c4 = st.columns(4)
c1.metric("🚨 카이론 개발", "2025-12-07", "D-1", delta_color="inverse")
c2.metric("📅 1차 시험", "2026-04-25", "D-140")
c3.metric("📉 체중 감량", "2025-12-31", "D-25")
c4.metric("🥕 당근 마켓", "2025-12-07", "D-1")

st.divider()

# 3. 상단 컨트롤 (기상 / 템플릿)
ctrl_c1, ctrl_c2 = st.columns([1, 2], vertical_alignment="center")
with ctrl_c1:
    st.checkbox("☀️ 7시 기상 성공!", value=True)
with ctrl_c2:
    sc1, sc2 = st.columns([3, 1])
    sc1.selectbox("루틴 불러오기", ["선택하세요", "평일 루틴", "주말 루틴"], label_visibility="collapsed")
    sc2.button("적용", use_container_width=True)

st.write("") # 간격

# 4. 할 일 입력 (접었다 폈다)
with st.expander("➕ 새로운 할 일 추가 (Click)", expanded=True):
    r1_c1, r1_c2 = st.columns([1, 1])
    r1_c1.time_input("시작 시간", datetime.time(14,0))
    r1_c2.selectbox("카테고리", PROJECT_CATEGORIES)
    
    st.text_input("메인 목표", placeholder="예: 오후 집중 업무")
    st.text_area("세부 목표 (선택)", height=60, placeholder="- 보고서 작성\n- 메일 회신")
    st.text_input("참고 링크 (선택)")
    
    st.button("등록", use_container_width=True, type="primary")

st.markdown("---")

# 5. 할 일 리스트 (Main Task List)
st.subheader("📋 오늘의 할 일")

# 더미 데이터
dummy_tasks = [
    {"time": "09:00", "cat": "CTA 공부", "main": "오전 학습 세션", "sub": "- 세법 3강\n- 복습하기", "link": "", "dur": 7200, "state": "done"},
    {"time": "12:00", "cat": "건강/운동", "main": "점심 식사", "sub": "", "link": "", "dur": 3600, "state": "done"},
    {"time": "13:00", "cat": "업무/사업", "main": "카이론 앱 UI 수정", "sub": "- 메인화면 배치 변경\n- 컬러셋 확정", "link": "figma.com/...", "dur": 1540, "state": "running"},
    {"time": "19:00", "cat": "기타/생활", "main": "저녁 식사", "sub": "", "link": "", "dur": 0, "state": "ready"},
]

for t in dummy_tasks:
    # 카드형 컨테이너
    with st.container(border=True):
        # [Header Row] 시간 | 카테고리 | 메인 | 타이머 | 버튼
        c1, c2, c3, c4, c5 = st.columns([0.8, 1.2, 3.5, 1, 1.5], vertical_alignment="center")
        
        c1.text(t['time'])
        c2.markdown(f":{CATEGORY_COLORS.get(t['cat'])}[**{t['cat']}**]")
        c3.markdown(f"**{t['main']}**")
        
        # 타이머 표시
        m, s = divmod(t['dur'], 60)
        h, m = divmod(m, 60)
        t_str = f"{h:02d}:{m:02d}:{s:02d}"
        
        if t['state'] == 'running':
            c4.markdown(f"🔥 `{t_str}`")
            c5.button("⏹️ 중지", key=f"stop_{t['time']}", use_container_width=True)
        else:
            c4.markdown(f"⏱️ `{t_str}`")
            c5.button("▶️ 시작", key=f"start_{t['time']}", use_container_width=True)
            
        # [Detail Row] 세부내용 (있으면 펼치기)
        has_detail = bool(t['sub'] or t['link'])
        exp_label = "🔽 세부 내용 보기" if has_detail else "🔽 내용 추가"
        
        with st.expander(exp_label):
            st.text_area("세부 목표", value=t['sub'], key=f"sub_{t['time']}")
            st.text_input("자료 링크", value=t['link'], key=f"link_{t['time']}")
            
            # 삭제 버튼 (우측 정렬 느낌)
            d1, d2 = st.columns([4, 1])
            d2.button("🗑️ 삭제", key=f"del_{t['time']}", use_container_width=True)

st.markdown("---")

# 6. 하단 리포트 (Daily Report)
st.subheader("📊 Daily Report")

k1, k2, k3 = st.columns(3)
k1.metric("총 집중 시간", "03:25:40", help="순수 공부/업무 시간")
k2.metric("목표 달성률", "35%")
k3.metric("오늘의 평가", "Fighting 🔥")

st.caption("프로젝트별 시간 비중")
st.progress(60, text="CTA 공부 (60%)")
st.progress(30, text="업무/사업 (30%)")

st.text_area("✍️ 오늘의 회고", placeholder="오늘 하루는 어땠나요? 내일의 다짐을 적어보세요.")

if st.button("💾 모든 기록 저장하기", type="primary", use_container_width=True):
    st.toast("✅ 저장되었습니다!")
