import streamlit as st
import pandas as pd
import datetime

# 페이지 설정
st.set_page_config(page_title="UI 디자인 시안 V2", page_icon="🎨", layout="wide")

# 스타일 예시 데이터
PROJECT_CATEGORIES = ["CTA 공부", "업무/사업", "건강/운동", "기타/생활"]

# ---------------------------------------------------------
# [팝업 1] 목표(D-Day) 관리 디자인
# ---------------------------------------------------------
@st.dialog("🎯 목표(D-Day) 관리")
def mock_goal_popup():
    st.caption("프로젝트별 주요 목표일을 관리하세요. 가장 급한 목표가 메인에 표시됩니다.")
    
    # 기존 리스트 예시
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.5, 2, 1], vertical_alignment="center")
        c1.markdown(":blue[**[CTA 공부]**]")
        c2.write("1차 시험 (2026-04-25)")
        c3.button("삭제", key="del_g1")
        
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.5, 2, 1], vertical_alignment="center")
        c1.markdown(":orange[**[업무/사업]**]")
        c2.write("카이론 앱 런칭 (2025-12-07)")
        c3.button("삭제", key="del_g2")

    st.markdown("---")
    st.write("###### ➕ 새 목표 추가")
    with st.form("mock_goal_form"):
        c1, c2 = st.columns(2)
        c1.selectbox("카테고리", PROJECT_CATEGORIES, key="mg_cat")
        c2.text_input("목표명 (예: 바디프로필)", key="mg_name")
        st.date_input("목표 날짜", key="mg_date")
        st.form_submit_button("목표 등록", type="primary")

# ---------------------------------------------------------
# [팝업 2] Inbox(생각 보관함) 디자인
# ---------------------------------------------------------
@st.dialog("📥 Inbox (생각 보관함)")
def mock_inbox_popup():
    st.caption("떠오르는 아이디어나 나중에 할 일을 막 적어두세요.")
    
    # 탭으로 분리 (입력 / 목록)
    tab1, tab2 = st.tabs(["➕ 추가하기", "📋 목록 보기 (3)"])
    
    with tab1:
        with st.form("mock_inbox_form"):
            c1, c2 = st.columns([1, 2])
            c1.selectbox("분류", PROJECT_CATEGORIES, key="mi_cat")
            c1.selectbox("우선순위", ["높음", "보통", "낮음"], key="mi_prio")
            c2.text_input("할 일 내용", placeholder="예: 세법 개정안 확인")
            c2.text_area("메모/링크", height=100, placeholder="구체적인 내용...")
            st.form_submit_button("보관함에 저장", type="primary")
            
    with tab2:
        # 리스트 예시
        for i in range(3):
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.markdown("**[업무] 디자인 시안 컨펌**")
                c1.caption("참고 링크: figma.com/...")
                c2.button("삭제", key=f"mi_del_{i}")

# ---------------------------------------------------------
# [팝업 3] 템플릿(루틴) 관리 디자인
# ---------------------------------------------------------
@st.dialog("📑 루틴 템플릿 관리")
def mock_template_popup():
    st.caption("자주 쓰는 하루 일과를 세트로 만들어두세요.")
    
    # 템플릿 선택
    st.selectbox("편집할 템플릿 선택", ["평일 루틴 (기본)", "주말 몰입 루틴", "+ 새 템플릿 만들기"], key="mt_sel")
    
    st.markdown("---")
    st.write("###### '평일 루틴' 구성 내용")
    
    # 테이블 헤더
    h1, h2, h3, h4 = st.columns([1, 1.5, 3, 0.5])
    h1.caption("시간")
    h2.caption("카테고리")
    h3.caption("할 일")
    
    # 예시 데이터
    dummy_routine = [
        ("08:00", "CTA 공부", "아침 백지 복습"),
        ("13:00", "건강/운동", "점심 식사"),
        ("19:00", "기타/생활", "저녁 식사")
    ]
    
    for t_time, t_cat, t_task in dummy_routine:
        r1, r2, r3, r4 = st.columns([1, 1.5, 3, 0.5], vertical_alignment="center")
        r1.text(t_time)
        r2.text(t_cat)
        r3.text(t_task)
        r4.button("x", key=f"mt_del_{t_time}")
        
    # 루틴 항목 추가
    with st.expander("➕ 이 템플릿에 항목 추가", expanded=True):
        c1, c2, c3 = st.columns([1, 1.5, 2])
        c1.time_input("시간", key="mt_add_time")
        c2.selectbox("카테고리", PROJECT_CATEGORIES, key="mt_add_cat")
        c3.text_input("내용", key="mt_add_task")
        st.button("항목 추가", use_container_width=True)


# =========================================================
# 메인 화면 구성 (팝업 트리거용)
# =========================================================

# 1. 사이드바
with st.sidebar:
    st.title("🗂️ 메뉴")
    st.button("📝 Daily Planner", use_container_width=True, type="primary")
    st.button("📊 Dashboard", use_container_width=True)
    
    st.markdown("---")
    
    # 팝업 트리거 버튼들
    if st.button("📥 Inbox 관리", use_container_width=True):
        mock_inbox_popup()
        
    if st.button("📑 템플릿 관리", use_container_width=True):
        mock_template_popup()

    st.markdown("---")
    
    st.subheader("🎯 목표 (D-Day)")
    st.info("**[업무] 카이론 앱 개발** (D-1)")
    if st.button("목표 설정 팝업", use_container_width=True):
        mock_goal_popup()

# 2. 메인 바디 (Daily View 느낌만)
st.title("📝 2025-12-06 (카이론 앱 개발 D-1)")

# 상단 컨트롤
c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="center")
with c1: st.checkbox("☀️ 7시 기상 성공!", value=True)
with c2: st.selectbox("📥 루틴 불러오기", ["선택하세요", "평일 루틴"], label_visibility="collapsed")
with c3: st.button("적용", use_container_width=True)

st.divider()

# 할 일 리스트 예시 (하나만)
with st.container(border=True):
    c1, c2, c3, c4, c5 = st.columns([0.8, 1, 3.5, 1, 1.5], vertical_alignment="center")
    c1.text("09:00")
    c2.markdown(":blue[**[CTA 공부]**]")
    c3.markdown("**오전 학습 세션**")
    c4.markdown("⏱️ `01:30:00`")
    c5.button("⏹️ 중지", use_container_width=True, type="primary")
    
    with st.expander("🔽 세부 내용 보기"):
        st.text_area("세부 목표", "- 강의 3강 듣기\n- 복습하기")
        st.text_input("자료 링크")
