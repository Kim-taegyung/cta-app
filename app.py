import streamlit as st
import pandas as pd
import datetime
import time
import json
import calendar
from oauth2client.service_account import ServiceAccountCredentials
# 자동 새로고침 패키지 (없으면 pip install streamlit-autorefresh)
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    def st_autorefresh(interval, key): pass

# --- 1. 앱 기본 설정 및 상수 ---
st.set_page_config(page_title="CTA 합격 메이커", page_icon="📝", layout="wide")

# [설정] 순공 시간에서 제외할 활동
NON_STUDY_TASKS = ["점심 식사", "저녁 식사", "휴식"]

# [신규] 멀티 프로젝트 카테고리 정의
PROJECT_CATEGORIES = ["CTA 공부", "업무/사업", "건강/운동", "기타/생활"]
CATEGORY_COLORS = {"CTA 공부": "blue", "업무/사업": "orange", "건강/운동": "green", "기타/생활": "gray"}

# --- 2. 헬퍼 함수 ---
@st.cache_resource(ttl=3600)
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def format_time(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

def get_status_color(achieved, target):
    if target == 0: return "⚪"
    ratio = (achieved / target) * 100
    if ratio >= 80: return "🟢 Good"
    elif ratio >= 50: return "🟡 Normal"
    else: return "🔴 Bad"

# [신규] Inbox(할일 보관함) 모달 팝업
@st.dialog("📥 Inbox (생각 보관함)")
def show_inbox_modal():
    st.write("떠오르는 아이디어나 나중에 할 일을 기록해두세요.")
    
    with st.form("inbox_form", clear_on_submit=True):
        c1, c2 = st.columns([1, 2])
        with c1: 
            cat = st.selectbox("카테고리", PROJECT_CATEGORIES)
            priority = st.selectbox("우선순위", ["높음", "보통", "낮음"], index=1)
        with c2:
            task_name = st.text_input("할 일 내용", placeholder="예: 세법 개정안 확인하기")
            memo = st.text_area("메모 (선택)", height=80, placeholder="구체적인 내용이나 링크 등")
        
        if st.form_submit_button("보관함에 저장"):
            # 임시 세션 저장 (추후 DB 연결 시 이 부분 수정)
            new_item = {
                "category": cat,
                "task": task_name,
                "priority": priority,
                "memo": memo,
                "created_at": str(datetime.datetime.now())
            }
            st.session_state.inbox_items.append(new_item)
            st.toast(f"✅ Inbox에 저장됨: {task_name}")
            st.rerun()

# [신규] 사이드바 네비게이션 팝업 (저장 확인)
@st.dialog("페이지 이동 확인")
def confirm_navigation_modal(target_mode):
    st.write("저장하지 않은 내용은 사라집니다.\n저장하고 이동하시겠습니까?")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("💾 저장 후 이동", use_container_width=True):
            # (저장 로직 호출 - 간소화를 위해 pass 처리, 실제로는 save_to_google_sheets 호출)
            st.toast("저장되었습니다! (시뮬레이션)")
            time.sleep(0.5)
            st.session_state.view_mode = target_mode
            st.rerun()
    with c2:
        if st.button("이동만 하기", use_container_width=True):
            st.session_state.view_mode = target_mode
            st.rerun()
    with c3:
        if st.button("취소", use_container_width=True):
            st.rerun()

# --- 3. 세션 초기화 ---
if 'view_mode' not in st.session_state: st.session_state.view_mode = "Daily View (플래너)"
if 'selected_date' not in st.session_state: st.session_state.selected_date = datetime.date.today()
if 'tasks' not in st.session_state: st.session_state.tasks = []
if 'inbox_items' not in st.session_state: st.session_state.inbox_items = [] # Inbox 데이터
if 'telegram_id' not in st.session_state: st.session_state.telegram_id = "" # 텔레그램 ID
# ... 기타 필요한 세션 변수들 (cal_year, target_time 등은 생략했으나 실제 코드엔 포함 필요)

# --- 4. 사이드바 (UI 개선) ---
with st.sidebar:
    st.title("🗂️ 메뉴")
    
    # [1] 네비게이션
    def try_navigate(target):
        if st.session_state.view_mode == "Daily View (플래너)" and st.session_state.view_mode != target:
            confirm_navigation_modal(target)
        else:
            st.session_state.view_mode = target
            st.rerun()

    if st.button("📅 Monthly View", use_container_width=True): try_navigate("Monthly View (캘린더)")
    if st.button("📝 Daily View", use_container_width=True): try_navigate("Daily View (플래너)")
    if st.button("📊 Dashboard", use_container_width=True): try_navigate("Dashboard (대시보드)")
    
    # [신규] Inbox 버튼 (메뉴 하단 배치)
    st.markdown("---")
    if st.button("📥 Inbox (할일 보관함)", use_container_width=True):
        show_inbox_modal()
    
    # [신규] 사용자 설정 (텔레그램 ID)
    st.markdown("---")
    with st.expander("⚙️ 사용자 설정", expanded=True):
        st.session_state.telegram_id = st.text_input(
            "텔레그램 ID", 
            value=st.session_state.telegram_id, 
            placeholder="숫자 ID 입력",
            help="알림을 받을 Telegram User ID를 입력하세요."
        )
        if st.button("ID 저장"):
            st.toast("텔레그램 ID가 설정되었습니다.")

    # [신규] 즐겨찾기 관리 (Daily View일 때만 표시, 카테고리 추가)
    if st.session_state.view_mode == "Daily View (플래너)":
        st.markdown("---")
        st.subheader("⭐️ 즐겨찾기 루틴")
        with st.form("fav_form", clear_on_submit=True):
            f_cat = st.selectbox("카테고리", PROJECT_CATEGORIES)
            f_time = st.time_input("시간", value=datetime.time(9,0))
            f_task = st.text_input("루틴 내용")
            if st.form_submit_button("루틴 생성"):
                if 'favorite_tasks' not in st.session_state: st.session_state.favorite_tasks = []
                st.session_state.favorite_tasks.append({
                    "category": f_cat,
                    "plan_time": f_time.strftime("%H:%M"), 
                    "task": f_task
                })
                st.session_state.favorite_tasks.sort(key=lambda x: x['plan_time'])
                st.rerun()
        
        # 삭제 UI 생략 (기존과 동일)

# --- 5. 메인 UI ---

# [VIEW 2] Daily View (플래너)
if st.session_state.view_mode == "Daily View (플래너)":
    # 타이머 갱신
    if any(t.get('is_running') for t in st.session_state.tasks):
        st_autorefresh(interval=1000, key="timer_refresh")
        
    st.title(f"📝 {st.session_state.selected_date.strftime('%Y-%m-%d')} 플래너")
    
    # 상단 정보 (기상 인증 등 - 생략 없이 기존 유지하면 됨)
    
    st.markdown("---")
    
    # [신규] 수동 할 일 추가 (카테고리 포함)
    with st.container():
        st.caption("➕ 할 일 등록 (카테고리 분류)")
        # 레이아웃: 시간 | 카테고리 | 내용 | 버튼
        c1, c2, c3, c4 = st.columns([1, 1.5, 3, 1], vertical_alignment="bottom")
        
        with c1: input_time = st.time_input("시작", value=datetime.time(9,0))
        with c2: input_cat = st.selectbox("프로젝트", PROJECT_CATEGORIES, label_visibility="visible") # 레이블 보이게 수정
        with c3: input_task = st.text_input("내용", placeholder="업무/학습 내용")
        with c4:
            if st.button("등록", use_container_width=True):
                # 데이터 구조에 'category' 추가
                st.session_state.tasks.append({
                    "plan_time": input_time.strftime("%H:%M"),
                    "category": input_cat,
                    "task": input_task,
                    "accumulated": 0,
                    "last_start": None,
                    "is_running": False
                })
                st.rerun()

    st.markdown("---")
    
    # 할 일 리스트 출력
    st.session_state.tasks.sort(key=lambda x: x['plan_time'])
    total_seconds = 0
    cat_stats = {cat: 0 for cat in PROJECT_CATEGORIES} # 카테고리별 시간 집계용
    
    for i, task in enumerate(st.session_state.tasks):
        # UI: 시간 | (색상띠)내용 | 타이머/버튼 | 삭제
        c1, c2, c3, c4 = st.columns([1, 3, 2, 0.5], vertical_alignment="center")
        
        with c1: 
            # 시간 수정 가능하게
            new_time = st.time_input("t", value=datetime.datetime.strptime(task['plan_time'], "%H:%M").time(), key=f"t_{i}", label_visibility="collapsed", disabled=task['is_running'])
            if new_time.strftime("%H:%M") != task['plan_time']:
                task['plan_time'] = new_time.strftime("%H:%M")
                st.rerun()
                
        with c2:
            # [UI] 카테고리 색상 뱃지 + 내용
            cat = task.get('category', 'CTA 공부')
            color = CATEGORY_COLORS.get(cat, 'gray')
            st.markdown(f":{color}[**[{cat}]**]") 
            task['task'] = st.text_input("task", value=task['task'], key=f"k_{i}", label_visibility="collapsed", disabled=task['is_running'])
            
        with c3:
            dur = task['accumulated']
            if task.get('is_running'): dur += time.time() - task['last_start']
            
            t1, t2 = st.columns([1, 1.2])
            t1.markdown(f"⏱️ `{format_time(dur)}`")
            
            # (오늘 날짜 체크 로직은 생략, 실제엔 포함)
            if task.get('is_running'):
                if t2.button("⏹️ 중지", key=f"stop_{i}", use_container_width=True):
                    task['accumulated'] += time.time() - task['last_start']
                    task['is_running'] = False
                    st.rerun()
            else:
                if t2.button("▶️ 시작", key=f"start_{i}", use_container_width=True):
                    task['is_running'] = True
                    task['last_start'] = time.time()
                    st.rerun()
                    
        with c4:
            if st.button("x", key=f"d_{i}"):
                del st.session_state.tasks[i]
                st.rerun()
        
        # [통계 집계]
        current_dur = task['accumulated']
        if task.get('is_running'): current_dur += (time.time() - task['last_start'])
        
        if task['task'] not in NON_STUDY_TASKS:
            total_seconds += current_dur
            # 카테고리별 합산
            cat_key = task.get('category', 'CTA 공부')
            if cat_key in cat_stats:
                cat_stats[cat_key] += current_dur

    st.divider()
    
    # [신규] 하단 통계 섹션 (순공시간 -> 집중시간, 비율 표시)
    st.subheader("📊 오늘의 집중 리포트")
    
    # 1. 총 집중시간
    total_hours = total_seconds / 3600
    if 'target_time' not in st.session_state: st.session_state.target_time = 10.0
    
    k1, k2, k3 = st.columns(3)
    k1.metric("총 집중 시간", format_time(total_seconds), delta="순공 시간")
    k2.metric("목표 달성률", f"{(total_hours/st.session_state.target_time)*100:.1f}%")
    k3.metric("평가", get_status_color(total_hours, st.session_state.target_time))
    
    # 2. 카테고리별 투입 비율 (Progress Bar)
    st.write("###### 📈 프로젝트별 투입 비율")
    if total_seconds > 0:
        for cat, sec in cat_stats.items():
            if sec > 0:
                ratio = sec / total_seconds
                st.caption(f"{cat}: {format_time(sec)} ({ratio*100:.1f}%)")
                st.progress(ratio, text=None)
                # Streamlit의 progress 색상은 테마를 따르므로, 
                # 색상을 커스텀하려면 CSS나 차트 라이브러리를 써야하지만, 
                # 일단 기본 progress바로 비율을 보여줍니다.
    else:
        st.info("아직 측정된 집중 시간이 없습니다.")

    # 저장 버튼 영역 (생략)
    
# [VIEW 1, 3] Monthly, Dashboard 등은 기존 코드 유지
elif st.session_state.view_mode == "Monthly View (캘린더)":
    st.title("📅 캘린더 (준비중)")
elif st.session_state.view_mode == "Dashboard (대시보드)":
    st.title("📊 대시보드 (준비중)")
