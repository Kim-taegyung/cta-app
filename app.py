import streamlit as st
import pandas as pd
import datetime
import time
import gspread
import json 
import streamlit.components.v1 as components 
from oauth2client.service_account import ServiceAccountCredentials

# =========================================================================
# [새로운 헬퍼 함수] 캐시 초기화 및 세션 재시작 함수
# =========================================================================
def clear_cache_and_restart():
    """모든 캐시와 세션 상태를 삭제하고 재시작합니다."""
    st.cache_data.clear()
    st.cache_resource.clear()
    if 'session_initialized_date' in st.session_state:
         del st.session_state.session_initialized_date # 플래그 삭제
    st.rerun()

def display_realtime_clock():
    """JavaScript를 사용하여 실시간 시계를 매초 업데이트합니다."""
    components.html("""
    <script>
    function updateClock() {
        const now = new Date();
        const options = {year: 'numeric', month: '2-digit', day: '2-digit'};
        const dateString = now.toLocaleDateString('ko-KR', options).replace(/ /g, '').replace(/\.$/, '').replace(/\./g, '-');
        const timeString = String(now.getHours()).padStart(2, 0) + ":" + 
                           String(now.getMinutes()).padStart(2, 0) + ":" + 
                           String(now.getSeconds()).padStart(2, 0);
        document.getElementById('realtime-clock').innerHTML = dateString + ' | ' + timeString;
    }
    setInterval(updateClock, 1000);
    updateClock();
    </script>
    <div id="realtime-clock" style="font-size: 16px; font-weight: bold; color: #FF4B4B;"></div>
    """, height=30)
# =========================================================================
# (이하 기존 코드는 동일하게 이어집니다.)
# =========================================================================


# --- 1. 앱 기본 설정 ---
st.set_page_config(page_title="CTA 합격 메이커", page_icon="📝", layout="wide")

# [추가] 순공 시간에서 제외할 활동 리스트 정의
NON_STUDY_TASKS = [
    "점심 식사 및 신체 유지 (운동)", 
    "저녁 식사 및 익일 식사 준비"
]

# --- 2. 헬퍼 함수 ---
@st.cache_resource(ttl=3600) 
def get_gspread_client():
    """Google Sheet 클라이언트 객체를 반환합니다."""
    if "gcp_service_account" not in st.secrets:
        return None
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_default_tasks():
    """새로운 날에 자동으로 로드될 고정 루틴을 정의합니다."""
    return [
        {"plan_time": "08:00", "task": "아침 백지 복습", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "13:00", "task": "점심 식사 및 신체 유지 (운동)", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "19:00", "task": "저녁 식사 및 익일 식사 준비", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "21:00", "task": "저녁 백지 복습/정리", "accumulated": 0, "last_start": None, "is_running": False},
    ]

def save_to_google_sheets(date, total_seconds, status, wakeup_success, tasks, target_time, d_day_date, favorite_tasks, daily_reflection):
    try:
        client = get_gspread_client()
        if client is None: return True 
        sheet = client.open("CTA_Study_Data").sheet1 
        
        tasks_json = json.dumps(tasks)
        favorites_json = json.dumps(favorite_tasks) 
        
        row = [
            str(date), 
            round(total_seconds/3600, 2), 
            status, 
            "성공" if wakeup_success else "실패", 
            tasks_json,
            target_time, 
            str(d_day_date),
            favorites_json,
            daily_reflection
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False

@st.cache_data(show_spinner=False) # 데이터 로드 자체는 캐시
def load_persistent_data():
    client = get_gspread_client()
    default_favorites = [
        {"plan_time": "08:00", "task": "아침 백지 복습", "key": "08:00_아침 백지 복습"},
        {"plan_time": "21:00", "task": "당일 학습 백지 복습", "key": "21:00_당일 학습 백지 복습"}
    ]
    if client is None: return get_default_tasks(), 10.0, datetime.date(2026, 5, 1), default_favorites, ""

    try:
        sheet = client.open("CTA_Study_Data").sheet1 
        records = sheet.get_all_records()
        default_d_day = datetime.date(2026, 5, 1)
        
        tasks = get_default_tasks()
        is_today_loaded = False
        target_time = 10.0
        d_day_date = default_d_day
        favorites = default_favorites
        daily_reflection = ""

        if records:
            df = pd.DataFrame(records)
            last_record = df.iloc[-1]
            today_date_str = datetime.date.today().strftime('%Y-%m-%d')
            
            if last_record.get('날짜') == today_date_str:
                is_today_loaded = True
                if last_record.get('Tasks_JSON'):
                     tasks = json.loads(last_record['Tasks_JSON'])
                     for task in tasks:
                        task['is_running'] = False 
                        task['last_start'] = None
                else:
                    tasks = [] 
            
            target_time_raw = last_record.get('Target_Time', 10.0) 
            try:
                target_time = float(target_time_raw)
            except (ValueError, TypeError):
                target_time = 10.0
            
            d_day_date_str = last_record.get('DDay_Date')
            d_day_date = default_d_day
            if d_day_date_str:
                try:
                    d_day_date = datetime.datetime.strptime(str(d_day_date_str), '%Y-%m-%d').date()
                except ValueError:
                    d_day_date = default_d_day

            if last_record.get('Favorites_JSON'):
                try:
                    favorites = json.loads(last_record['Favorites_JSON'])
                except:
                    pass
            
            if is_today_loaded:
                daily_reflection = last_record.get('Daily_Reflection', "")

        return tasks, target_time, d_day_date, favorites, daily_reflection

    except Exception as e:
        return get_default_tasks(), 10.0, datetime.date(2026, 5, 1), default_favorites, ""

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

# --- 3. 세션 및 데이터 초기화 ---
# [수정] 강제 초기화 로직이 제거되었으므로, 이 블록은 그대로 유지
initial_tasks, initial_target_time, initial_d_day_date, initial_favorites, initial_reflection = load_persistent_data()

if 'tasks' not in st.session_state: st.session_state.tasks = initial_tasks 
if 'target_time' not in st.session_state: st.session_state.target_time = initial_target_time
if 'd_day_date' not in st.session_state: st.session_state.d_day_date = initial_d_day_date
if 'favorite_tasks' not in st.session_state: st.session_state.favorite_tasks = initial_favorites
if 'daily_reflection' not in st.session_state: st.session_state.daily_reflection = initial_reflection
if 'wakeup_checked' not in st.session_state:
    if initial_reflection and "7시 기상 성공" in initial_reflection: st.session_state.wakeup_checked = True 
    else: st.session_state.wakeup_checked = False
    
# --- 4. 사이드바 (설정 & 사운드 & 루틴) ---
with st.sidebar:
    st.header("⚙️ 설정")
    
    # [수정] 캐시 초기화 버튼 추가
    if st.button("🔴 날짜/데이터 초기화 및 새로고침", type="primary"):
        clear_cache_and_restart()
    st.caption("날짜가 어제 날짜로 고정되었거나 데이터가 꼬였을 때 눌러주세요.")
    st.markdown("---") 
    
    st.subheader("시험 목표 설정")
    new_d_day = st.date_input("시험 예정일 (D-Day)", value=st.session_state.d_day_date)
    if new_d_day != st.session_state.d_day_date:
        st.session_state.d_day_date = new_d_day
        st.rerun()

    st.markdown("---") 
    
    st.subheader("🎧 몰입 사운드 (Focus Sound)")
    sound_option = st.selectbox("사운드 선택", ["선택 안 함", "빗소리 (Rain)", "카페 소음 (Cafe)", "알파파 (Alpha Waves)"])
    
    if sound_option == "빗소리 (Rain)":
        st.audio("https://cdn.pixabay.com/download/audio/2022/07/04/audio_14e5b9f7a7.mp3", format="audio/mp3", loop=True)
        st.caption("☔ 차분한 빗소리로 잡념을 씻어냅니다.")
    elif sound_option == "카페 소음 (Cafe)":
        st.audio("https://cdn.pixabay.com/download/audio/2021/08/09/audio_88447e769f.mp3", format="audio/mp3", loop=True)
        st.caption("☕ 적당한 소음이 집중력을 높입니다.")
    elif sound_option == "알파파 (Alpha Waves)":
        st.audio("https://cdn.pixabay.com/download/audio/2022/03/09/audio_c8c8a73467.mp3", format="audio/mp3", loop=True)
        st.caption("🧠 뇌파를 안정시켜 학습 효율을 극대화합니다.")

    st.markdown("---") 
    
    st.subheader("⭐️ 즐겨찾는 루틴 관리")
    with st.form("favorite_form", clear_on_submit=True):
        fav_time = st.time_input("루틴 시간", value=datetime.time(9, 0), key="fav_time")
        fav_task = st.text_input("루틴 내용", placeholder="예: 백지 복습", key="fav_task")
        submitted = st.form_submit_button("즐겨찾기 추가")
        if submitted and fav_task:
            new_fav = {"plan_time": fav_time.strftime("%H:%M"), "task": fav_task, "key": f"{fav_time.strftime('%H:%M')}_{fav_task}"}
            if new_fav not in st.session_state.favorite_tasks:
                st.session_state.favorite_tasks.append(new_fav)
                st.session_state.favorite_tasks.sort(key=lambda x: x['plan_time'])
                st.success("추가됨!")
                st.rerun()

    if st.session_state.favorite_tasks:
        fav_options = [f"{f['plan_time']} - {f['task']}" for f in st.session_state.favorite_tasks]
        fav_to_delete = st.multiselect("삭제할 루틴 선택", options=fav_options)
        if st.button("선택 루틴 삭제", type="secondary"):
            if fav_to_delete:
                keys_to_delete = [opt.split(" - ", 1) for opt in fav_to_delete]
                keys_to_delete = [f"{k[0]}_{k[1]}" for k in keys_to_delete]
                
                st.session_state.favorite_tasks = [f for f in st.session_state.favorite_tasks if f['key'] not in keys_to_delete]
                st.rerun()

# --- 5. 메인 UI ---
today = datetime.date.today()
d_day_delta = (st.session_state.d_day_date - today).days
d_day_str = f"D-{d_day_delta}" if d_day_delta > 0 else (f"D+{abs(d_day_delta)}" if d_day_delta < 0 else "D-Day")

st.title(f"📝 CTA 합격 메이커 ({d_day_str})")
mode = st.radio("모드 선택", ["Daily View (오늘의 공부)", "Monthly View (대시보드)"], horizontal=True)

# ---------------------------------------------------------
# [모드 1] 데일리 뷰
# ---------------------------------------------------------
if mode == "Daily View (오늘의 공부)":
    st.subheader(f"📅 {today.strftime('%Y-%m-%d')}")
    display_realtime_clock() 
    
    st.markdown("##### ☀️ 아침 루틴")
    is_wakeup = st.checkbox("7시 기상 성공!", value=st.session_state.wakeup_checked, key="wakeup_chk")
    st.session_state.wakeup_checked = is_wakeup 
    st.divider()

    st.markdown("##### 🚀 즐겨찾는 루틴 즉시 추가")
    if st.session_state.favorite_tasks:
        fav_options = [f"{f['plan_time']} - {f['task']}" for f in st.session_state.favorite_tasks]
        col_fav1, col_fav2 = st.columns([4, 1])
        with col_fav1:
            selected_fav_option = st.selectbox("등록된 루틴 선택", options=fav_options, label_visibility="collapsed")
        with col_fav2:
            if st.button("추가", use_container_width=True, key="add_fav_btn"):
                time_str, task_str = selected_fav_option.split(" - ", 1)
                if not any(t['plan_time'] == time_str and t['task'] == task_str for t in st.session_state.tasks):
                    st.session_state.tasks.append({
                        "plan_time": time_str,
                        "task": task_str,
                        "accumulated": 0,
                        "last_start": None,
                        "is_running": False
                    })
                    st.rerun()
                else: st.warning("이미 등록된 할 일입니다.")
    else: st.info("등록된 즐겨찾는 루틴이 없습니다.")
        
    st.markdown("---")

    st.markdown("##### ➕ 수동으로 타임테이블 추가")
    col_input1, col_input2, col_btn = st.columns([1, 3, 1], vertical_alignment="bottom")
    with col_input1:
        plan_time = st.time_input("시작 시간", value=datetime.time(9, 0), key="manual_time")
    with col_input2:
        new_task = st.text_input("학습할 과목/내용", placeholder="예: 재무회계 기출풀이", key="manual_time")
    with col_btn:
