import streamlit as st
import pandas as pd
import datetime
import time
import gspread
import json 
import streamlit.components.v1 as components 
from oauth2client.service_account import ServiceAccountCredentials

# ---------------------------------------------------------
# [기능 추가] 타이머 실시간 작동을 위한 자동 새로고침
# ---------------------------------------------------------
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    def st_autorefresh(interval, key): pass

# [새 함수] 캐시 초기화 및 세션 재시작
def clear_cache_and_restart():
    """모든 캐시와 세션 상태를 삭제하고 재시작합니다."""
    st.cache_data.clear()
    st.cache_resource.clear()
    st.session_state.clear()
    st.rerun()

# [새 함수] JavaScript 시계
def display_realtime_clock():
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

# --- 1. 앱 기본 설정 ---
st.set_page_config(page_title="CTA 합격 메이커", page_icon="📝", layout="wide")

# [설정] 순공 시간에서 제외할 활동 리스트
NON_STUDY_TASKS = [
    "점심 식사 및 신체 유지 (운동)", 
    "저녁 식사 및 익일 식사 준비"
]

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

@st.cache_data(show_spinner=False)
def load_persistent_data():
    client = get_gspread_client()
    default_favorites = [
        {"plan_time": "08:00", "task": "아침 백지 복습", "key": "def_1"},
        {"plan_time": "21:00", "task": "당일 학습 백지 복습", "key": "def_2"}
    ]
    if client is None: return get_default_tasks(), 10.0, datetime.date(2026, 5, 1), default_favorites, ""

    try:
        sheet = client.open("CTA_Study_Data").sheet1 
        records = sheet.get_all_records()
        default_d_day = datetime.date(2026, 5, 1)
        
        tasks = get_default_tasks()
        target_time = 10.0
        d_day_date = default_d_day
        favorites = default_favorites
        daily_reflection = ""

        if records:
            df = pd.DataFrame(records)
            last_record = df.iloc[-1]
            today_date_str = datetime.date.today().strftime('%Y-%m-%d')
            
            if last_record.get('날짜') == today_date_str:
                if last_record.get('Tasks_JSON'):
                     tasks = json.loads(last_record['Tasks_JSON'])
                     for task in tasks:
                        task['is_running'] = False 
                        task['last_start'] = None
                else: tasks = [] 
            
            target_time_raw = last_record.get('Target_Time', 10.0) 
            try: target_time = float(target_time_raw)
            except: target_time = 10.0
            
            d_day_date_str = last_record.get('DDay_Date')
            if d_day_date_str:
                try: d_day_date = datetime.datetime.strptime(str(d_day_date_str), '%Y-%m-%d').date()
                except: pass

            if last_record.get('Favorites_JSON'):
                try: favorites = json.loads(last_record['Favorites_JSON'])
                except: pass
            
            if last_record.get('날짜') == today_date_str:
                daily_reflection = last_record.get('Daily_Reflection', "")

        return tasks, target_time, d_day_date, favorites, daily_reflection

    except Exception:
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

# --- 3. 데이터 로드 및 세션 초기화 ---
initial_tasks, initial_target_time, initial_d_day_date, initial_favorites, initial_reflection = load_persistent_data()

if 'tasks' not in st.session_state: st.session_state.tasks = initial_tasks 
if 'target_time' not in st.session_state: st.session_state.target_time = initial_target_time
if 'd_day_date' not in st.session_state: st.session_state.d_day_date = initial_d_day_date
if 'favorite_tasks' not in st.session_state: st.session_state.favorite_tasks = initial_favorites
if 'daily_reflection' not in st.session_state: st.session_state.daily_reflection = initial_reflection
if 'wakeup_checked' not in st.session_state:
    if initial_reflection and "7시 기상 성공" in initial_reflection: st.session_state.wakeup_checked = True 
    else: st.session_state.wakeup_checked = False
    
# --- 4. 사이드바 UI ---
with st.sidebar:
    st.header("⚙️ 설정")
    
    # [수정] 오류 해결용 캐시 초기화 버튼
    if st.button("🔴 날짜/데이터 오류 시 클릭 (초기화)", type="primary"):
        clear_cache_and_restart()
    
    st.markdown("---")
    
    st.subheader("시험 목표")
    new_d_day = st.date_input("시험 예정일", value=st.session_state.d_day_date)
    if new_d_day != st.session_state.d_day_date:
        st.session_state.d_day_date = new_d_day
        st.rerun()

    st.markdown("---") 
    
    st.subheader("🎧 몰입 사운드")
    sound_tab1, sound_tab2 = st.tabs(["기본", "유튜브"])
    with sound_tab1:
        sound_option = st.radio("배경음", ["무음", "빗소리", "카페", "알파파"], label_visibility="collapsed")
        if sound_option == "빗소리": st.audio("https://cdn.pixabay.com/download/audio/2022/07/04/audio_14e5b9f7a7.mp3", loop=True)
        elif sound_option == "카페": st.audio("https://cdn.pixabay.com/download/audio/2021/08/09/audio_88447e769f.mp3", loop=True)
        elif sound_option == "알파파": st.audio("https://cdn.pixabay.com/download/audio/2022/03/09/audio_c8c8a73467.mp3", loop=True)
    with sound_tab2:
        y_url = st.text_input("URL 입력")
        if y_url: st.video(y_url)

    st.markdown("---") 
    
    st.subheader("⭐️ 즐겨찾기 관리")
    with st.form("favorite_form", clear_on_submit=True):
        f_time = st.time_input("시간", value=datetime.time(9, 0))
        f_task = st.text_input("내용")
        if st.form_submit_button("추가"):
            st.session_state.favorite_tasks.append({"plan_time": f_time.strftime("%H:%M"), "task": f_task, "key": f"{time.time()}"})
            st.rerun()

    if st.session_state.favorite_tasks:
        f_opts = [f"{t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks]
        d_target = st.selectbox("삭제할 루틴", ["선택"] + f_opts)
        if st.button("삭제"):
            if d_target != "선택":
                idx = f_opts.index(d_target)
                del st.session_state.favorite_tasks[idx]
                st.rerun()

# --- 5. 메인 UI ---
today = datetime.date.today()
d_day_delta = (st.session_state.d_day_date - today).days
d_day_str = f"D-{d_day_delta}" if d_day_delta > 0 else (f"D+{abs(d_day_delta)}" if d_day_delta < 0 else "D-Day")

st.title(f"📝 CTA 합격 메이커 ({d_day_str})")
mode = st.radio("모드", ["Daily View", "Monthly View"], horizontal=True, label_visibility="collapsed")

if mode == "Daily View":
    # [수정] 타이머가 돌고 있을 때만 1초마다 자동 새로고침 (실시간 시계 효과)
    if any(t.get('is_running') for t in st.session_state.tasks):
        st_autorefresh(interval=1000, key="timer_running")

    st.subheader(f"📅 {today.strftime('%Y-%m-%d')}")
    display_realtime_clock() 
    
    is_wakeup = st.checkbox("☀️ 7시 기상 성공!", value=st.session_state.wakeup_checked)
    st.session_state.wakeup_checked = is_wakeup
    
    st.divider()

    # 즐겨찾기 추가
    if st.session_state.favorite_tasks:
        col_fav1, col_fav2 = st.columns([4, 1], vertical_alignment="bottom")
        with col_fav1:
            fav_opts = [f"{t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks]
            sel_fav = st.selectbox("즐겨찾기에서 추가", ["선택하세요"] + fav_opts, label_visibility="collapsed")
        with col_fav2:
            if st.button("추가", use_container_width=True, key="fav_add_btn"):
                if sel_fav != "선택하세요":
                    t_time, t_task = sel_fav.split(" - ", 1)
                    st.session_state.tasks.append({"plan_time": t_time, "task": t_task, "accumulated": 0, "last_start": None, "is_running": False})
                    st.rerun()
    
    st.markdown("---")

    # 수동 추가 (정렬 수정 및 에러 방지)
    st.caption("➕ 수동으로 할 일 추가")
    c1, c2, c3 = st.columns([1, 3, 1], vertical_alignment="bottom")
    with c1: input_time = st.time_input("시간", value=datetime.time(9,0), key="manual_time_picker")
    with c2: input_task = st.text_input("내용", key="manual_task_input")
    with c3: 
        if st.button("등록", use_container_width=True, key="manual_add_btn"):
            if input_task:
                st.session_state.tasks.append({"plan_time": input_time.strftime("%H:%M"), "task": input_task, "accumulated": 0, "last_start": None, "is_running": False})
                st.rerun()

    st.markdown("---")

    # 리스트 출력
    st.session_state.tasks.sort(key=lambda x: x['plan_time'])
    total_seconds = 0
    
    for i, task in enumerate(st.session_state.tasks):
        c1, c2, c3, c4 = st.columns([1, 3, 2, 0.5], vertical_alignment="center")
        with c1: st.text(f"{task['plan_time']}")
        with c2: st.markdown(f"**{task['task']}**")
        with c3:
            dur = task['accumulated']
            if task.get('is_running'): dur += time.time() - task['last_start']
            
            t1, t2 = st.columns([1, 1])
            t1.markdown(f"⏱️ `{format_time(dur)}`")
            
            # [수정] 중복 키 에러 방지를 위해 key에 index와 task 이름 포함
            btn_key_base = f"btn_{i}_{task['task']}"
            if task.get('is_running'):
                if t2.button("⏹️", key=f"stop_{btn_key_base}"):
                    task['accumulated'] += time.time() - task['last_start']
                    task['is_running'] = False
                    st.rerun()
            else:
                if t2.button("▶️", key=f"start_{btn_key_base}"):
                    task['is_running'] = True
                    task['last_start'] = time.time()
                    st.rerun()
        with c4:
            if st.button("x", key=f"del_{btn_key_base}"):
                del st.session_state.tasks[i]
                st.rerun()
        
        if task['task'] not in NON_STUDY_TASKS:
            if task.get('is_running'): total_seconds += (task['accumulated'] + (time.time() - task['last_start']))
            else: total_seconds += task['accumulated']

    st.divider()

    # [수정] float 에러 방지를 위해 float() 형변환 적용
    st.session_state.target_time = st.number_input("오늘 목표(시간)", value=float(st.session_state.target_time), step=0.5)
    
    hours = total_seconds / 3600
    status = get_status_color(hours, st.session_state.target_time)

    m1, m2, m3 = st.columns(3)
    m1.metric("총 순공 시간", format_time(total_seconds))
    m2.metric("목표 달성률", f"{(hours/st.session_state.target_time)*100:.1f}%")
    m3.metric("오늘의 평가", status)
    
    st.session_state.daily_reflection = st.text_area("학습 일기", value=st.session_state.daily_reflection)

    if st.button("💾 구글 시트에 기록 저장하기", type="primary", use_container_width=True):
        if save_to_google_sheets(today, total_seconds, status, st.session_state.wakeup_checked, st.session_state.tasks, st.session_state.target_time, st.session_state.d_day_date, st.session_state.favorite_tasks, st.session_state.daily_reflection):
            st.success("✅ 저장 완료!")
        else: st.error("저장 실패.")

else:
    # Monthly View
    try:
        client = get_gspread_client()
        if client and "gcp_service_account" in st.secrets:
            sheet = client.open("CTA_Study_Data").sheet1
            records = sheet.get_all_records()
            if records:
                df = pd.DataFrame(records)
                df_latest = df.groupby('날짜').last().reset_index()
                columns_to_display = [col for col in df_latest.columns if col not in ['Tasks_JSON', 'Target_Time', 'DDay_Date', 'Favorites_JSON']]
                st.dataframe(df_latest[columns_to_display], use_container_width=True)
                if '기상성공여부' in df_latest.columns:
                    success_count = len(df_latest[df_latest['기상성공여부'] == '성공'])
                    st.info(f"누적 기록: {len(df_latest)}일 | 기상 성공 횟수: {success_count}회")
            else: st.info("아직 저장된 기록이 없습니다.")
        else: st.warning("구글 시트 연동 설정(Secrets)이 필요합니다.")
    except Exception as e: st.warning(f"데이터 로드 중 오류: {e}")
