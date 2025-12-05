import streamlit as st
import pandas as pd
import datetime
import time
import gspread
import json 
from oauth2client.service_account import ServiceAccountCredentials

# ---------------------------------------------------------
# [기능] 타이머 작동 시 자동 새로고침 (실시간 초 흐름)
# ---------------------------------------------------------
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    def st_autorefresh(interval, key): pass

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
    default_favs = [
        {"plan_time": "08:00", "task": "아침 백지 복습", "key": "def_1"},
        {"plan_time": "21:00", "task": "당일 학습 백지 복습", "key": "def_2"}
    ]
    # 기본 반환값
    base_data = (get_default_tasks(), 10.0, datetime.date(2026, 5, 1), default_favs, "")
    
    if client is None: return base_data

    try:
        sheet = client.open("CTA_Study_Data").sheet1 
        records = sheet.get_all_records()
        
        if records:
            df = pd.DataFrame(records)
            last_record = df.iloc[-1]
            today_str = datetime.date.today().strftime('%Y-%m-%d')
            
            # 1. 할 일 목록 (오늘 기록이 있으면 로드, 없으면 기본값)
            tasks = get_default_tasks()
            daily_reflection = ""
            if last_record.get('날짜') == today_str:
                if last_record.get('Tasks_JSON'):
                    try:
                        loaded = json.loads(last_record['Tasks_JSON'])
                        for t in loaded: 
                            t['is_running'] = False
                            t['last_start'] = None
                        tasks = loaded
                    except: pass
                daily_reflection = last_record.get('Daily_Reflection', "")

            # 2. 설정값 (날짜 상관없이 최신값)
            target_time = 10.0
            try: target_time = float(last_record.get('Target_Time', 10.0))
            except: pass
            
            d_day_date = datetime.date(2026, 5, 1)
            try: 
                d_str = last_record.get('DDay_Date')
                if d_str: d_day_date = datetime.datetime.strptime(str(d_str), '%Y-%m-%d').date()
            except: pass

            favorites = default_favs
            try:
                if last_record.get('Favorites_JSON'):
                    favorites = json.loads(last_record['Favorites_JSON'])
            except: pass

            return tasks, target_time, d_day_date, favorites, daily_reflection

        return base_data
    except: return base_data

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

# --- 3. 데이터 로드 (최초 1회) ---
if 'data_loaded' not in st.session_state:
    init_tasks, init_target, init_dday, init_favs, init_reflect = load_persistent_data()
    st.session_state.tasks = init_tasks 
    st.session_state.target_time = init_target
    st.session_state.d_day_date = init_dday
    st.session_state.favorite_tasks = init_favs
    st.session_state.daily_reflection = init_reflect
    st.session_state.wakeup_checked = False
    st.session_state.data_loaded = True

# --- 4. 사이드바 (설정) ---
with st.sidebar:
    st.header("⚙️ 설정")
    
    # 캐시 리셋 버튼 (비상용)
    if st.button("🔄 데이터/화면 새로고침"):
        st.cache_data.clear()
        st.session_state.clear()
        st.rerun()
    
    st.markdown("---")
    new_d_day = st.date_input("시험 예정일", value=st.session_state.d_day_date)
    if new_d_day != st.session_state.d_day_date:
        st.session_state.d_day_date = new_d_day
        st.rerun()

    st.markdown("---")
    st.subheader("⭐️ 즐겨찾기 관리")
    with st.form("fav_form", clear_on_submit=True):
        f_time = st.time_input("시간", value=datetime.time(9,0))
        f_task = st.text_input("내용")
        if st.form_submit_button("추가"):
            st.session_state.favorite_tasks.append({"plan_time": f_time.strftime("%H:%M"), "task": f_task, "key": f"{time.time()}"})
            st.rerun()
            
    if st.session_state.favorite_tasks:
        f_list = [f"{t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks]
        del_target = st.selectbox("삭제할 루틴", ["선택하세요"] + f_list)
        if st.button("삭제"):
            if del_target != "선택하세요":
                idx = f_list.index(del_target)
                del st.session_state.favorite_tasks[idx]
                st.rerun()

# --- 5. 메인 UI ---
today = datetime.date.today()
d_day_delta = (st.session_state.d_day_date - today).days
d_day_str = f"D-{d_day_delta}" if d_day_delta > 0 else "D-Day"

st.title(f"📝 CTA 합격 메이커 ({d_day_str})")
mode = st.radio("모드", ["Daily View", "Monthly View"], horizontal=True, label_visibility="collapsed")

if mode == "Daily View":
    # 타이머 작동 시 1초마다 리프레시
    if any(t.get('is_running') for t in st.session_state.tasks):
        st_autorefresh(interval=1000, key="timer_running")

    st.subheader(f"📅 {today.strftime('%Y-%m-%d')}")
    is_wakeup = st.checkbox("☀️ 7시 기상 성공!", value=st.session_state.wakeup_checked)
    st.session_state.wakeup_checked = is_wakeup
    
    st.divider()

    # 즐겨찾기 추가
    if st.session_state.favorite_tasks:
        col_fav1, col_fav2 = st.columns([4, 1], vertical_alignment="bottom")
        with col_fav1:
            sel_fav = st.selectbox("즐겨찾기 추가", ["선택하세요"] + [f"{t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks], label_visibility="collapsed")
        with col_fav2:
            if st.button("추가", use_container_width=True):
                if sel_fav != "선택하세요":
                    t_time, t_task = sel_fav.split(" - ", 1)
                    st.session_state.tasks.append({"plan_time": t_time, "task": t_task, "accumulated": 0, "last_start": None, "is_running": False})
                    st.rerun()

    st.markdown("---")

    # 수동 추가
    c1, c2, c3 = st.columns([1, 3, 1], vertical_alignment="bottom")
    with c1: input_time = st.time_input("시간", value=datetime.time(9,0))
    with c2: input_task = st.text_input("내용 입력", placeholder="과목명")
    with c3: 
        if st.button("등록", use_container_width=True):
            st.session_state.tasks.append({"plan_time": input_time.strftime("%H:%M"), "task": input_task, "accumulated": 0, "last_start": None, "is_running": False})
            st.rerun()

    st.markdown("---")

    # [수정된 리스트 UI] 버튼 칸을 확실하게 확보
    st.session_state.tasks.sort(key=lambda x: x['plan_time'])
    total_seconds = 0
    
    for i, task in enumerate(st.session_state.tasks):
        # 5개 칸으로 명확히 분리: [시간] [내용] [타이머시간] [시작/중지] [삭제]
        c1, c2, c3, c4, c5 = st.columns([1, 3, 1.2, 0.8, 0.5], vertical_alignment="center")
        
        with c1: st.text(f"{task['plan_time']}")
        with c2: st.markdown(f"**{task['task']}**")
        
        # 타이머 계산
        dur = task['accumulated']
        if task.get('is_running'): dur += time.time() - task['last_start']
        
        with c3: st.markdown(f"⏱️ `{format_time(dur)}`")
        
        # 버튼 (Unique Key 적용)
        unique_key = f"{i}_{task['task']}_{task['plan_time']}"
        with c4:
            if task.get('is_running'):
                if st.button("⏹️ 중지", key=f"stop_{unique_key}"):
                    task['accumulated'] += time.time() - task['last_start']
                    task['is_running'] = False
                    st.rerun()
            else:
                if st.button("▶️ 시작", key=f"start_{unique_key}"):
                    task['is_running'] = True
                    task['last_start'] = time.time()
                    st.rerun()
        
        with c5:
            if st.button("x", key=f"del_{unique_key}"):
                del st.session_state.tasks[i]
                st.rerun()
        
        if task['task'] not in NON_STUDY_TASKS:
            if task.get('is_running'): total_seconds += (task['accumulated'] + (time.time() - task['last_start']))
            else: total_seconds += task['accumulated']

    st.divider()
    
    st.session_state.target_time = st.number_input("목표 시간", value=float(st.session_state.target_time), step=0.5)
    hours = total_seconds / 3600
    status = get_status_color(hours, st.session_state.target_time)
    
    k1, k2, k3 = st.columns(3)
    k1.metric("총 순공 시간", format_time(total_seconds))
    k2.metric("달성률", f"{(hours/st.session_state.target_time)*100:.1f}%")
    k3.metric("평가", status)
    
    st.session_state.daily_reflection = st.text_area("학습 일기", value=st.session_state.daily_reflection)
    
    if st.button("💾 구글 시트에 기록 저장하기", type="primary", use_container_width=True):
        if save_to_google_sheets(today, total_seconds, status, st.session_state.wakeup_checked, st.session_state.tasks, st.session_state.target_time, st.session_state.d_day_date, st.session_state.favorite_tasks, st.session_state.daily_reflection):
            st.success("저장되었습니다!")
        else: st.error("저장 실패")

else:
    # Monthly View
    st.title("📊 통합 대시보드")
    try:
        client = get_gspread_client()
        if client:
            sheet = client.open("CTA_Study_Data").sheet1
            records = sheet.get_all_records()
            if records:
                df = pd.DataFrame(records)
                df_latest = df.groupby('날짜').last().reset_index()
                cols = [c for c in df.columns if c not in ['Tasks_JSON', 'Target_Time', 'DDay_Date', 'Favorites_JSON']]
                st.dataframe(df_latest[cols], use_container_width=True)
            else:
                st.info("데이터 없음")
    except:
        st.error("데이터 로드 실패")
