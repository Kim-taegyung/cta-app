import streamlit as st
import pandas as pd
import datetime
import time
import gspread
import json
import calendar
from oauth2client.service_account import ServiceAccountCredentials

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

# --- 4. 사이드바 ---
with st.sidebar:
    st.header("🗂️ 메뉴")
    if st.button("📅 Monthly View (캘린더)", use_container_width=True):
        st.session_state.view_mode = "Monthly View (캘린더)"
        st.rerun()
    if st.button("📝 Daily View (플래너)", use_container_width=True):
        st.session_state.view_mode = "Daily View (플래너)"
        st.rerun()
    if st.button("📊 Dashboard (대시보드)", use_container_width=True):
        st.session_state.view_mode = "Dashboard (대시보드)"
        st.rerun()

    st.markdown("---")
    
    # [수정] 즐겨찾기 관리 기능 복구
    if st.session_state.view_mode == "Daily View (플래너)":
        st.subheader("⚙️ 설정")
        
        # 데이터 로드 로직
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
            st.caption("➕ 수동으로 할 일 추가하기")
            try:
                c1, c2, c3 = st.columns([1, 3, 1], vertical_alignment="bottom")
            except TypeError:
                c1, c2, c3 = st.columns([1, 3, 1])
                
            with c1: input_time = st.time_input("시작 시간", value=datetime.time(9,0))
            with c2: input_task = st.text_input("내용 입력", placeholder="과목명 등")
            with c3: 
                if st.button("등록", use_container_width=True):
                    t_time_str = input_time.strftime("%H:%M")
                    # [수정 1] 중복 시간 체크 로직
                    existing_times = [t['plan_time'] for t in st.session_state.tasks]
                    if t_time_str in existing_times:
                         st.warning(f"⚠️ {t_time_str}에 이미 일정이 있습니다.")
                    else:
                        st.session_state.tasks.append({"plan_time": t_time_str, "task": input_task, "accumulated": 0, "last_start": None, "is_running": False})
                        st.rerun()

        st.markdown("---")
        
        # 한국 시간 기준 오늘 날짜 계산
        curr_utc = datetime.datetime.utcnow()
        curr_kst = curr_utc + datetime.timedelta(hours=9)
        today_kst = curr_kst.date()

        # 시간순 정렬
        st.session_state.tasks.sort(key=lambda x: x['plan_time'])
        total_seconds = 0
        
        # [수정 2] 리스트 출력 및 수정 기능 구현
        # 인덱스(i)를 사용하여 리스트를 순회하며 바로 수정 가능하게 함
        for i, task in enumerate(st.session_state.tasks):
            # 입력창이 들어가야 하므로 컬럼 비율을 조금 조정했습니다.
            c1, c2, c3, c4 = st.columns([1.2, 3, 2.2, 0.5], vertical_alignment="center")
            
            # 1. 시간 수정 (Time Input)
            with c1:
                # 문자열 "HH:MM"을 time 객체로 변환
                try:
                    t_obj = datetime.datetime.strptime(task['plan_time'], "%H:%M").time()
                except:
                    t_obj = datetime.time(0,0)

                # 타이머가 돌고 있으면 수정 불가능하게(disabled) 처리
                new_time_val = st.time_input(
                    "시간", 
                    value=t_obj, 
                    key=f"edit_time_{i}_{task['plan_time']}", 
                    label_visibility="collapsed",
                    disabled=task['is_running'] 
                )
                
                # 시간이 변경되었다면 리스트 업데이트 후 리런 (재정렬 위해)
                new_time_str = new_time_val.strftime("%H:%M")
                if new_time_str != task['plan_time']:
                    # 시간 변경 시에도 중복 체크 (선택 사항이나, 복잡해질 수 있어 여기선 단순 변경 허용하되 겹치면 경고 없이 덮어씌워질 수 있음. 
                    # 안전을 위해 중복 체크 추가)
                    existing_times_check = [t['plan_time'] for j, t in enumerate(st.session_state.tasks) if j != i]
                    if new_time_str in existing_times_check:
                         st.toast("⚠️ 이미 존재하는 시간입니다.", icon="🚫")
                    else:
                        task['plan_time'] = new_time_str
                        st.rerun()

            # 2. 내용 수정 (Text Input)
            with c2:
                new_task_name = st.text_input(
                    "내용", 
                    value=task['task'], 
                    key=f"edit_task_{i}_{task['task']}", 
                    label_visibility="collapsed",
                    disabled=task['is_running']
                )
                if new_task_name != task['task']:
                    task['task'] = new_task_name
                    # 텍스트만 바뀔 때는 굳이 리런 안 해도 되지만, 확실한 저장을 위해
                    # session state는 참조형이라 자동 반영됨.

            # 3. 타이머 및 버튼
            with c3:
                dur = task['accumulated']
                if task.get('is_running'): dur += time.time() - task['last_start']
                
                t1, t2 = st.columns([1, 1.5])
                t1.markdown(f"⏱️ `{format_time(dur)}`")
                
                if sel_date == today_kst:
                    if task.get('is_running'):
                        if t2.button("⏹️ 중지", key=f"stop_{i}", use_container_width=True): 
                            task['accumulated'] += time.time() - task['last_start']
                            task['is_running'] = False
                            st.rerun()
                    else:
                        # 시작 버튼은 Primary 컬러로 강조
                        if t2.button("▶️ 시작", key=f"start_{i}", use_container_width=True):
                            task['is_running'] = True
                            task['last_start'] = time.time()
                            st.rerun()
                else:
                    t2.caption("-")
            
            # 4. 삭제 버튼
            with c4:
                if st.button("x", key=f"del_{i}"):
                    del st.session_state.tasks[i]
                    st.rerun()
            
            # 총 공부 시간 계산
            if task['task'] not in NON_STUDY_TASKS:
                if task.get('is_running'): total_seconds += (task['accumulated'] + (time.time() - task['last_start']))
                else: total_seconds += task['accumulated']

        st.divider()
        
        # ... (이하 하단 저장 로직은 기존과 동일) ...
        st.session_state.target_time = st.number_input("목표 시간", value=st.session_state.target_time, step=0.5)
        hours = total_seconds / 3600
        status = get_status_color(hours, st.session_state.target_time)
        
        k1, k2, k3 = st.columns(3)
        k1.metric("총 순공 시간", format_time(total_seconds))
        k2.metric("달성률", f"{(hours/st.session_state.target_time)*100:.1f}%")
        k3.metric("평가", status)
        
        st.session_state.daily_reflection = st.text_area("학습 일기", value=st.session_state.daily_reflection, height=100)
        
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




