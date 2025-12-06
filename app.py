import streamlit as st
import pandas as pd
import datetime

# 페이지 설정
st.set_page_config(page_title="UI 디자인 시안", page_icon="🎨", layout="wide")

# 스타일 예시 데이터
PROJECT_CATEGORIES = ["CTA 공부", "업무/사업", "건강/운동", "기타/생활"]
CATEGORY_COLORS = {"CTA 공부": "blue", "업무/사업": "orange", "건강/운동": "green", "기타/생활": "gray"}

# ---------------------------------------------------------
# 1. 사이드바 (Sidebar)
# ---------------------------------------------------------
with st.sidebar:
    st.title("🗂️ 메뉴")
    st.button("📝 Daily Planner (현재 화면)", use_container_width=True, type="primary")
    st.button("📊 Dashboard (통계)", use_container_width=True)
    
    st.markdown("---")
    
    # Inbox
    c1, c2 = st.columns([3, 1])
    c1.button("📥 Inbox 관리", use_container_width=True)
    c2.markdown("**3개**") # 뱃지 느낌
    
    # 템플릿
    st.button("📑 루틴(템플릿) 관리", use_container_width=True)

    st.markdown("---")
    
    # 목표 관리 (리스트 형태)
    st.subheader("🎯 목표 (D-Day)")
    st.info("**[업무] 카이론 앱 개발**\nD-1 (2025-12-07)")
    st.success("**[공부] 1차 시험**\nD-140 (2026-04-25)")
    st.button("목표 설정 팝업", use_container_width=True)

    st.markdown("---")
    with st.expander("⚙️ 고급 설정"):
        st.text_input("텔레그램 ID", value="123456789")
        st.button("저장")

# ---------------------------------------------------------
# 2. 메인 화면 (Main)
# ---------------------------------------------------------
st.title("📝 2025-12-06 (카이론 앱 개발 D-1)")

# [A] 상단 컨트롤 패널
with st.container(border=True):
    c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="center")
    
    # 기상 인증
    with c1:
        st.checkbox("☀️ 7시 기상 성공!", value=True)
    
    # 템플릿 불러오기
    with c2:
        st.selectbox("📥 루틴 불러오기", ["선택하세요", "평일 루틴", "주말 루틴"], label_visibility="collapsed")
    
    with c3:
        st.button("적용", use_container_width=True)

st.write("") # 간격

# [B] 할 일 입력 (접었다 폈다)
with st.expander("➕ 새로운 할 일 추가 (클릭해서 열기)", expanded=True):
    c_time, c_cat, c_main = st.columns([1, 1, 3])
    c_time.time_input("시작", datetime.time(14, 0))
    c_cat.selectbox("분류", PROJECT_CATEGORIES)
    c_main.text_input("할 일 내용", placeholder="예: 오후 세법 강의 수강")
    
    c_sub, c_btn = st.columns([4, 1], vertical_alignment="bottom")
    c_sub.text_input("세부 목표/링크 (선택)", placeholder="강의 링크나 구체적 목표")
    c_btn.button("등록", use_container_width=True, type="primary")

st.markdown("---")

# [C] 할 일 리스트 (카드형 디자인)
st.subheader("📋 오늘의 할 일")

# 예시 데이터 (더미)
dummy_tasks = [
    {"time": "09:00", "cat": "CTA 공부", "main": "오전 학습 세션", "sub": "- 강의 3강 듣기\n- 복습 30분", "state": "done", "dur": 10800},
    {"time": "12:00", "cat": "건강/운동", "main": "점심 식사 및 휴식", "sub": "", "state": "done", "dur": 3600},
    {"time": "13:00", "cat": "업무/사업", "main": "비즈니스 미팅 준비", "sub": "자료 조사 링크: ...", "state": "running", "dur": 1500},
    {"time": "15:00", "cat": "CTA 공부", "main": "오후 학습 세션", "sub": "", "state": "ready", "dur": 0},
]

for t in dummy_tasks:
    # 카드형 컨테이너
    with st.container(border=True):
        # 1줄: 시간 | 카테고리 | 내용 | 타이머 | 버튼
        c1, c2, c3, c4, c5 = st.columns([0.8, 1, 3.5, 1, 1.5], vertical_alignment="center")
        
        c1.text(t['time'])
        # 카테고리 색상 뱃지
        color = CATEGORY_COLORS.get(t['cat'], 'gray')
        c2.markdown(f":{color}[**{t['cat']}**]")
        
        # 내용 (완료된 건 취소선?)
        c3.markdown(f"**{t['main']}**")
        
        # 타이머
        min, sec = divmod(t['dur'], 60)
        hr, min = divmod(min, 60)
        time_str = f"{hr:02d}:{min:02d}:{sec:02d}"
        
        if t['state'] == 'running':
            c4.markdown(f"🔥 `{time_str}`") # 작동중 강조
            c5.button("⏹️ 중지", key=f"stop_{t['time']}", use_container_width=True)
        else:
            c4.markdown(f"⏱️ `{time_str}`")
            c5.button("▶️ 시작", key=f"start_{t['time']}", use_container_width=True)

        # 2줄: 세부 내용 (Expander)
        if t['sub']:
            with st.expander("🔽 세부 내용 보기"):
                st.text_area("내용 수정", value=t['sub'], key=f"sub_{t['time']}")
                col_del, _ = st.columns([1, 4])
                col_del.button("🗑️ 삭제", key=f"del_{t['time']}")

st.markdown("---")

# [D] 하단 리포트 & 저장
st.subheader("📊 Daily Report")
k1, k2, k3 = st.columns(3)
k1.metric("총 집중 시간", "04:30:00", "+30분")
k2.metric("목표 달성률", "45%")
k3.metric("오늘의 평가", "Fighting 🍊")

# 프로젝트별 비중 (Progress)
st.caption("프로젝트별 비중")
st.progress(60, text="CTA 공부 (60%)")
st.progress(30, text="업무/사업 (30%)")

st.text_area("✍️ 오늘의 회고/메모", placeholder="오늘 하루는 어땠나요?")
st.button("💾 모든 기록 저장하기", type="primary", use_container_width=True)
