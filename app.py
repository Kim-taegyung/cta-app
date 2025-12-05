import streamlit as st
import pandas as pd
import datetime
import time
import gspread
import json
import calendar
from oauth2client.service_account import ServiceAccountCredentials
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    def st_autorefresh(interval, key): pass

# ---------------------------------------------------------
# [기능 추가] 타이머 실시간 작동을 위한 자동 새로고침
# ---------------------------------------------------------
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    # 패키지가 없을 경우를 대비한 더미 함수 (에러 방지)
    def st_autorefresh(interval, key): pass

# --- 1. 앱 기본 설정 ---
st.set_page_config(page_title="CTA 합격 메이커", page_icon="📝", layout="wide")

# [설정] 순공 시간에서 제외할 활동 리스트
NON_STUDY_TASKS = [
    "점심 식사 및 신체 유지 (운동)", 
    "저녁 식사 및 익일 식사 준비"
]

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

def get_default_tasks():
    return [
        {"plan_time": "08:00", "task": "아침 백지 복습", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "13:00", "task": "점심 식사 및 신체 유지 (운동)", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "19:00", "task": "저녁 식사 및 익일 식사 준비", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "21:00", "task": "당일 학습 백지 복습", "accumulated": 0, "last_start": None, "is_running": False},
    ]

def save_to_google_sheets(date, total_seconds, status, wakeup_success, tasks, target_time, d_day_date, favorite_tasks, daily_reflection):
    try:
        client = get_gspread_client()
        if client is None: return True 
        sheet = client.open("CTA_Study_Data").sheet1 
        
        tasks_json = json.dumps(tasks)
        favorites_json = json.dumps(favorite_tasks) 
        
        row = [str(date), round(total_seconds/3600, 2), status, "성공" if wakeup_success else "실패", tasks_json, target_time, str(d_day_date), favorites_json, daily_reflection]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False

def load_data_for_date(target_date):
    client = get_gspread_client()
    default_favs = [
        {"plan_time": "08:00", "task": "아침 백지 복습", "key": "def_1"},
        {"plan_time": "21:00", "task": "당일 학습 백지 복습", "key": "def_2"}
    ]
    data = {
        'tasks': get_default_tasks(),
        'target_time': 10.0,
        'd_day_date': datetime.date(2026, 5, 1),
        'favorites': default_favs,
        'daily_reflection': "",
        'wakeup_checked': False
    }
    
    if client is None: return data

    try:
        sheet = client.open("CTA_Study_Data").sheet1 
        records = sheet.get_all_records()
        
        if records:
            df = pd.DataFrame(records)
            target_str = target_date.strftime('%Y-%m-%d')
            
            day_records = df[df['날짜'] == target_str]
            if not day_records.empty:
                last_record = day_records.iloc[-1]
                if last_record.get('Tasks_JSON'):
                    try:
                        loaded_tasks = json.loads(last_record['Tasks_JSON'])
                        for t in loaded_tasks: 
                            t['is_running'] = False
                            t['last_start'] = None
                        data['tasks'] = loaded_tasks
                    except: pass
                else: data['tasks'] = []
                
                data['daily_reflection'] = last_record.get('Daily_Reflection', "")
                if last_record.get('기상성공여부') == '성공': data['wakeup_checked'] = True

            ref_record = last_record if not day_records.empty else df.iloc[-1]
            try: data['target_time'] = float(ref_record.get('Target_Time', 10.0))
            except: pass
            
            d_day_str = ref_record.get('DDay_Date')
            if d_day_str:
                try: data['d_day_date'] = datetime.datetime.strptime(str(d_day_str), '%Y-%m-%d').date()
                except: pass
                
            if ref_record.get('Favorites_JSON'):
                try: data['favorites'] = json.loads(ref_record['Favorites_JSON'])
                except: pass

        return data
    except: return data

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

def go_to_daily(date):
    st.session_state.selected_date = date
    st.session_state.view_mode = "Daily View (플래너)"
    st.rerun()

# --- 3. 세션 초기화 ---
if 'view_mode' not in st.session_state: st.session_state.view_mode = "Monthly View (캘린더)"
if 'selected_date' not in st.session_state: st.session_state.selected_date = datetime.date.today()
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.date.today().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.date.today().month


# --- 4. 사이드바 (네비게이션 및 설정) ---

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

# [기능] 저장 로직 분리 (재사용을 위해 함수화)
def perform_save(target_mode=None):
    # 현재 데이터 계산
    cur_total = 0
    for t in st.session_state.tasks:
        if t['task'] not in NON_STUDY_TASKS:
            dur = t['accumulated']
            if t.get('is_running'): dur += time.time() - t['last_start']
            cur_total += dur
    
    cur_hours = cur_total / 3600
    cur_status = get_status_color(cur_hours, st.session_state.target_time)
    
    # 저장 실행
    success = save_to_google_sheets(
        st.session_state.selected_date, 
        cur_total, 
        cur_status, 
        st.session_state.wakeup_checked, 
        st.session_state.tasks, 
        st.session_state.target_time, 
        st.session_state.d_day_date, 
        st.session_state.favorite_tasks, 
        st.session_state.daily_reflection
    )
    
    if success:
        st.toast("✅ 저장 완료!")
        time.sleep(0.5)
        if target_mode:
            st.session_state.view_mode = target_mode
            st.rerun()
    else:
        st.error("저장 실패")

# [기능] 모달 팝업창 정의 (st.dialog 사용)
@st.dialog("페이지 이동 확인")
def confirm_navigation_modal(target_mode):
    st.write("저장하지 않은 내용은 사라집니다.")
    st.write("저장하고 이동하시겠습니까?")
    
    # 버튼 디자인 개선 (붉은색 제거, 깔끔한 배치)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 촌스러운 붉은색(type='primary') 제거 -> 기본 버튼 사용
        if st.button("💾 저장 후 이동", use_container_width=True):
            perform_save(target_mode)
            
    with col2:
        if st.button("이동만 하기", use_container_width=True):
            st.session_state.view_mode = target_mode
            st.rerun()
            
    with col3:
        if st.button("취소", use_container_width=True):
            st.rerun()

# [사이드바 UI 구성]
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

    # [기존 기능 유지] 즐겨찾기 관리 (Daily View일 때만 표시)
    if st.session_state.view_mode == "Daily View (플래너)":
        st.subheader("⚙️ 설정")
        
        # 데이터 로드 트리거
        if 'loaded_date' not in st.session_state or st.session_state.loaded_date != st.session_state.selected_date:
            data = load_data_for_date(st.session_state.selected_date)
            st.session_state.tasks = data['tasks']
            st.session_state.target_time = data['target_time']
            st.session_state.d_day_date = data['d_day_date']
            st.session_state.favorite_tasks = data['favorites']
            st.session_state.daily_reflection = data['daily_reflection']
            st.session_state.wakeup_checked = data['wakeup_checked']
            st.session_state.loaded_date = st.session_state.selected_date

        new_d_day = st.date_input("시험 예정일", value=st.session_state.d_day_date)
        if new_d_day != st.session_state.d_day_date:
            st.session_state.d_day_date = new_d_day
            st.rerun()
            
        st.markdown("---")
        st.subheader("⭐️ 즐겨찾기 관리")
        with st.form("fav_manage_form", clear_on_submit=True):
            f_time = st.time_input("시간", value=datetime.time(9,0))
            f_task = st.text_input("루틴 내용")
            if st.form_submit_button("루틴 생성"):
                st.session_state.favorite_tasks.append({"plan_time": f_time.strftime("%H:%M"), "task": f_task, "key": f"{time.time()}"})
                st.session_state.favorite_tasks.sort(key=lambda x: x['plan_time'])
                st.rerun()
        
        if st.session_state.favorite_tasks:
            fav_list = [f"{t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks]
            del_target = st.selectbox("삭제할 루틴", ["선택하세요"] + fav_list)
            if st.button("선택한 루틴 삭제"):
                if del_target != "선택하세요":
                    idx = fav_list.index(del_target)
                    del st.session_state.favorite_tasks[idx]
                    st.rerun()

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


# --- 5. 메인 UI 레이아웃 설정 (3분할: 사이드바 | 메인 | 채팅) ---

# 메인 화면과 채팅창의 비율을 2.3 : 1 정도로 분할 (취향에 따라 [3, 1] 등으로 조정 가능)
main_col, chat_col = st.columns([2.3, 1])

# ---------------------------------------------------------
# [LEFT COLUMN] 메인 컨텐츠 영역 (기존 플래너/캘린더 기능)
# ---------------------------------------------------------
with main_col:
    
    # [VIEW 1] Monthly View (캘린더)
    if st.session_state.view_mode == "Monthly View (캘린더)":
        st.title("📅 월간 스케줄")
        
        col_prev, col_curr, col_next = st.columns([1, 5, 1])
        with col_prev:
            if st.button("◀"):
                if st.session_state.cal_month == 1:
                    st.session_state.cal_month = 12
                    st.session_state.cal_year -= 1
                else: st.session_state.cal_month -= 1
                st.rerun()
        with col_curr:
            st.markdown(f"<h3 style='text-align: center;'>{st.session_state.cal_year}년 {st.session_state.cal_month}월</h3>", unsafe_allow_html=True)
        with col_next:
            if st.button("▶"):
                if st.session_state.cal_month == 12:
                    st.session_state.cal_month = 1
                    st.session_state.cal_year += 1
                else: st.session_state.cal_month += 1
                st.rerun()

        status_map = {}
        try:
            client = get_gspread_client()
            if client:
                sheet = client.open("CTA_Study_Data").sheet1
                records = sheet.get_all_records()
                if records:
                    df = pd.DataFrame(records)
                    df_latest = df.groupby('날짜').last().reset_index()
                    for _, row in df_latest.iterrows():
                        status_map[row['날짜']] = row['상태']
        except: pass

        cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
        week_days = ['월', '화', '수', '목', '금', '토', '일']
        
        cols = st.columns(7)
        for i, day in enumerate(week_days): cols[i].markdown(f"**{day}**", unsafe_allow_html=True)
        
        for week in cal:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day == 0: cols[i].write("")
                else:
                    curr_date = datetime.date(st.session_state.cal_year, st.session_state.cal_month, day)
                    d_str = curr_date.strftime('%Y-%m-%d')
                    
                    status_icon = "⚪"
                    if d_str in status_map:
                        if "Good" in status_map[d_str]: status_icon = "🟢"
                        elif "Normal" in status_map[d_str]: status_icon = "🟡"
                        elif "Bad" in status_map[d_str]: status_icon = "🔴"
                    
                    label = f"{day} {status_icon}"
                    if cols[i].button(label, key=f"cal_{day}", use_container_width=True):
                        go_to_daily(curr_date)

    # [VIEW 2] Daily View (플래너)
    elif st.session_state.view_mode == "Daily View (플래너)":
        # 타이머 작동 중일 때만 자동 새로고침
        if any(t.get('is_running') for t in st.session_state.tasks):
            st_autorefresh(interval=1000, key="timer_refresh")

        sel_date = st.session_state.selected_date
        d_day_delta = (st.session_state.d_day_date - sel_date).days
        d_day_str = f"D-{d_day_delta}" if d_day_delta > 0 else "D-Day"
        
        st.title(f"📝 {sel_date.strftime('%Y-%m-%d')} ({d_day_str})")
        
        # --- 상단 루틴 체크 및 즐겨찾기 ---
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown("##### ☀️ 루틴 체크")
            is_wakeup = st.checkbox("7시 기상 성공!", value=st.session_state.wakeup_checked)
            st.session_state.wakeup_checked = is_wakeup
        with c2:
            st.markdown("##### 🚀 즐겨찾기 추가")
            if st.session_state.favorite_tasks:
                fav_opts = [f"{t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks]
                sel_fav = st.selectbox("루틴 선택", ["선택하세요"] + fav_opts, label_visibility="collapsed")
                
                if st.button("추가", use_container_width=True):
                    if sel_fav != "선택하세요":
                        t_time, t_task = sel_fav.split(" - ", 1)
                        # [수정 1] 중복 시간 체크 로직
                        existing_times = [t['plan_time'] for t in st.session_state.tasks]
                        if t_time in existing_times:
                            st.warning(f"⚠️ {t_time}에 이미 일정이 있습니다. 시간을 조정해주세요.")
                        else:
                            st.session_state.tasks.append({"plan_time": t_time, "task": t_task, "accumulated": 0, "last_start": None, "is_running": False})
                            st.rerun()

        st.markdown("---")
        
        # --- 수동 할 일 추가 ---
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
        
        # ---------------------------------------------------------
        # ---------------------------------------------------------
    # [1] 할 일 리스트 출력 및 제어 (수정됨)
    # ---------------------------------------------------------
    st.subheader("📋 오늘의 할 일")

    # 시간순 정렬
    st.session_state.tasks.sort(key=lambda x: x['plan_time'])
    
    # 통계 집계 변수 초기화
    total_seconds = 0
    cat_stats = {cat: 0 for cat in PROJECT_CATEGORIES} 
    
    # 리스트에 할 일이 없을 때 안내 문구
    if not st.session_state.tasks:
        st.info("👆 위 입력창에서 '등록' 버튼을 눌러 오늘의 할 일을 추가해보세요!")

    # [UI 헤더] 리스트 상단에 작은 제목을 달아 정렬을 더 명확하게 함 (선택 사항)
    # h_c1, h_c2, h_c3, h_c4, h_c5, h_c6 = st.columns([1.3, 1.2, 3.5, 1.2, 1, 0.5])
    # h_c1.caption("시간")
    # h_c2.caption("프로젝트")
    # h_c3.caption("할 일")
    # h_c4.caption("집중 시간")

    # 할 일 루프 시작
    for i, task in enumerate(st.session_state.tasks):
        # [레이아웃 수정] 시간 | 카테고리 | 내용 | 타이머 | 버튼 | 삭제
        # vertical_alignment="center"로 모든 요소를 수직 중앙 정렬
        c_time, c_cat, c_task, c_timer, c_btn, c_del = st.columns([1.3, 1.2, 3.5, 1.2, 1, 0.5], vertical_alignment="center")
        
        # 1. [시간] (타이머 작동 중 수정 불가)
        with c_time: 
            try: t_obj = datetime.datetime.strptime(task['plan_time'], "%H:%M").time()
            except: t_obj = datetime.time(0,0)
            
            new_time = st.time_input(
                "time", 
                value=t_obj, 
                key=f"time_{i}", 
                label_visibility="collapsed", 
                disabled=task['is_running'] # [수정] 작동 중 비활성화
            )
            if new_time.strftime("%H:%M") != task['plan_time']:
                task['plan_time'] = new_time.strftime("%H:%M")
                st.rerun()

        # 2. [카테고리] (별도 컬럼으로 분리하여 정렬)
        with c_cat:
            cat = task.get('category', 'CTA 공부')
            color = CATEGORY_COLORS.get(cat, 'gray')
            # 뱃지 형태로 중앙 정렬 표시
            st.markdown(f":{color}[**{cat}**]") 

        # 3. [내용] (타이머 작동 중 수정 불가)
        with c_task:
            task['task'] = st.text_input(
                "task", 
                value=task['task'], 
                key=f"task_input_{i}", 
                label_visibility="collapsed",
                disabled=task['is_running'] # [수정] 작동 중 비활성화
            )
            
        # 4. [타이머] 시간 표시
        with c_timer:
            dur = task['accumulated']
            if task.get('is_running'): 
                dur += time.time() - task['last_start']
            
            # 디지털 시계 느낌 (굵게)
            st.markdown(f"⏱️ **`{format_time(dur)}`**")
            
        # 5. [버튼] 시작/중지
        with c_btn:
            if sel_date == today_kst:
                if task.get('is_running'):
                    if st.button("⏹️ 중지", key=f"stop_{i}", use_container_width=True):
                        task['accumulated'] += time.time() - task['last_start']
                        task['is_running'] = False
                        st.rerun()
                else:
                    # 시작하지 않았을 때만 활성화
                    if st.button("▶️ 시작", key=f"start_{i}", use_container_width=True, type="primary"):
                        task['is_running'] = True
                        task['last_start'] = time.time()
                        st.rerun()
            else:
                st.caption("-")
                    
        # 6. [삭제]
        with c_del:
            # 작동 중엔 삭제도 막는 것이 안전함
            if st.button("🗑️", key=f"del_{i}", disabled=task.get('is_running')):
                del st.session_state.tasks[i]
                st.rerun()
        
        # --- [통계 데이터 집계] ---
        if task['task'] not in NON_STUDY_TASKS:
            current_dur = task['accumulated']
            if task.get('is_running'): 
                current_dur += (time.time() - task['last_start'])
            
            total_seconds += current_dur
            
            if cat in cat_stats:
                cat_stats[cat] += current_dur
            else:
                cat_stats[cat] = current_dur
        
        # ---------------------------------------------------------
        # [2] 하단 집중 리포트 (실시간 반영)
        # ---------------------------------------------------------
        st.subheader("📊 오늘의 집중 리포트")
        
        total_hours = total_seconds / 3600
        target = st.session_state.target_time if st.session_state.target_time > 0 else 1 
        
        # 1. 메트릭 (Metric)
        m1, m2, m3 = st.columns(3)
        m1.metric("총 집중 시간", format_time(total_seconds), help="식사/휴식 시간을 제외한 순수 집중 시간입니다.")
        m2.metric("목표 달성률", f"{(total_hours/target)*100:.1f}%")
        m3.metric("평가", get_status_color(total_hours, st.session_state.target_time))
        
        # 2. 프로젝트별 투입 비율 (Progress Bar)
        st.write("###### 📈 프로젝트별 투입 비율")
        
        if total_seconds > 0:
            for cat in PROJECT_CATEGORIES:
                sec = cat_stats.get(cat, 0)
                if sec > 0:
                    ratio = sec / total_seconds
                    color_name = CATEGORY_COLORS.get(cat, "gray")
                    
                    # 라벨 표시 (예: CTA 공부: 02:30:00 (50%))
                    st.caption(f":{color_name}[{cat}] : {format_time(sec)} ({ratio*100:.1f}%)")
                    # 프로그레스 바
                    st.progress(ratio)
        else:
            st.info("아직 집중 시간이 기록되지 않았습니다. 타이머를 시작해보세요!")
    
        st.divider()
        
        if st.button(f"💾 {sel_date} 기록 저장하기", type="primary", use_container_width=True):
            if save_to_google_sheets(sel_date, total_seconds, status, st.session_state.wakeup_checked, st.session_state.tasks, st.session_state.target_time, st.session_state.d_day_date, st.session_state.favorite_tasks, st.session_state.daily_reflection):
                st.success("저장되었습니다!")
            else: st.error("저장 실패")
    # [VIEW 3] Dashboard (대시보드)
    elif st.session_state.view_mode == "Dashboard (대시보드)":
        st.title("📊 통합 대시보드")
        try:
            client = get_gspread_client()
            if client:
                sheet = client.open("CTA_Study_Data").sheet1
                records = sheet.get_all_records()
                if records:
                    df = pd.DataFrame(records)
                    df_latest = df.groupby('날짜').last().reset_index()
                    
                    total_days = len(df_latest)
                    wakeup_success = len(df_latest[df_latest['기상성공여부'] == '성공']) if '기상성공여부' in df_latest.columns else 0
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("누적 학습일", f"{total_days}일")
                    m2.metric("기상 성공", f"{wakeup_success}회")
                    if '공부시간(시간)' in df_latest.columns:
                        avg_time = df_latest['공부시간(시간)'].mean()
                        m3.metric("평균 공부시간", f"{avg_time:.1f}시간")

                    st.divider()
                    st.subheader("📋 일별 상세 기록")
                    cols = [c for c in df_latest.columns if c not in ['Tasks_JSON', 'Target_Time', 'DDay_Date', 'Favorites_JSON']]
                    st.dataframe(df_latest[cols], use_container_width=True)
                else:
                    st.info("아직 데이터가 없습니다.")
        except:
            st.error("데이터 로드 중 오류가 발생했습니다.")

# ---------------------------------------------------------
# [RIGHT COLUMN] 우측 채팅 화면 (새로 추가됨)
# ---------------------------------------------------------
with chat_col:
    st.header("💬 AI Chat")
    st.caption("공부 중 궁금한 점을 물어보세요.")
    
    # 채팅 기록 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 채팅 기록 표시 (컨테이너를 사용하여 높이 제한 가능)
    with st.container(height=600, border=True):
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # 채팅 입력창
    if prompt := st.chat_input("질문을 입력하세요..."):
        # 사용자 메시지 표시
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 응답 (현재는 Echo 기능, 추후 AI 연결 가능)
        with st.chat_message("assistant"):
            response = f"입력하신 내용: {prompt} \n(AI 연결 시 답변이 표시됩니다)"
            st.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()





