import streamlit as st
import pandas as pd
import datetime
import time
import gspread
import json 
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. 앱 기본 설정 ---
st.set_page_config(page_title="CTA 합격 메이커", page_icon="📝", layout="wide")

# --- 2. 헬퍼 함수 ---
def get_gspread_client():
    """Google Sheet 클라이언트 객체를 반환합니다."""
    if "gcp_service_account" not in st.secrets:
        return None
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# [수정] daily_reflection 인자를 추가
def save_to_google_sheets(date, total_seconds, status, wakeup_success, tasks, target_time, d_day_date, favorite_tasks, daily_reflection):
    try:
        client = get_gspread_client()
        if client is None: return True 
        sheet = client.open("CTA_Study_Data").sheet1 
        
        tasks_json = json.dumps(tasks)
        favorites_json = json.dumps(favorite_tasks) 
        
        # [수정] row에 daily_reflection 추가
        row = [
            str(date), 
            round(total_seconds/3600, 2), 
            status, 
            "성공" if wakeup_success else "실패", 
            tasks_json,
            target_time, 
            str(d_day_date),
            favorites_json,
            daily_reflection # <--- 저장
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False

# [수정] load_persistent_data 함수: daily_reflection 로드 로직 추가
def load_persistent_data():
    client = get_gspread_client()
    if client is None: return [], 10.0, datetime.date(2026, 5, 1), [], ""

    try:
        sheet = client.open("CTA_Study_Data").sheet1 
        records = sheet.get_all_records()
        
        default_d_day = datetime.date(2026, 5, 1)
        default_favorites = [
            {"plan_time": "08:00", "task": "전일 복습 (백지)", "key": "08:00_전일 복습 (백지)"},
            {"plan_time": "21:00", "task": "세법학 암기", "key": "21:00_세법학 암기"}
        ]
        
        if records:
            df = pd.DataFrame(records)
            last_record = df.iloc[-1]
            today_date_str = datetime.date.today().strftime('%Y-%m-%d')
            
            # 1. Tasks 로드
            tasks = []
            if last_record.get('날짜') == today_date_str and last_record.get('Tasks_JSON'):
                 tasks = json.loads(last_record['Tasks_JSON'])
                 for task in tasks:
                    task['is_running'] = False 
                    task['last_start'] = None
            
            # 2. Settings 로드
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

            # 3. Favorites 로드
            favorites = default_favorites
            if last_record.get('Favorites_JSON'):
                try:
                    favorites = json.loads(last_record['Favorites_JSON'])
                except:
                    pass
            
            # [추가] 4. Reflection 로드 (오늘 날짜 기록이 있다면)
            daily_reflection = ""
            if last_record.get('날짜') == today_date_str:
                daily_reflection = last_record.get('Daily_Reflection', "")


            return tasks, target_time, d_day_date, favorites, daily_reflection
            
        return [], 10.0, default_d_day, default_favorites, ""

    except Exception as e:
        # st.warning(f"데이터 로드 중 오류: {e}") 
        return [], 10.0, datetime.date(2026, 5, 1), default_favorites, ""

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

# --- 3. 세션 및 데이터 초기화 (앱 시작 시 데이터 로드) ---
initial_tasks, initial_target_time, initial_d_day_date, initial_favorites, initial_reflection = load_persistent_data()

if 'tasks' not in st.session_state:
    st.session_state.tasks = initial_tasks 
if 'target_time' not in st.session_state:
    st.session_state.target_time = initial_target_time
if 'd_day_date' not in st.session_state:
    st.session_state.d_day_date = initial_d_day_date
if 'favorite_tasks' not in st.session_state:
    st.session_state.favorite_tasks = initial_favorites
# [추가] 일기 세션 초기화
if 'daily_reflection' not in st.session_state:
    st.session_state.daily_reflection = initial_reflection


if 'wakeup_checked' not in st.session_state:
    if initial_reflection and "7시 기상 성공" in initial_reflection: # 간단하게 과거 기록에서 불러오는 임시 로직
         st.session_state.wakeup_checked = True 
    else:
        st.session_state.wakeup_checked = False
    
# --- 4. 사이드바 (설정 & 즐겨찾기 관리) ---
with st.sidebar:
    st.header("⚙️ 설정")
    
    st.subheader("시험 목표 설정")
    new_d_day = st.date_input("시험 예정일 (D-Day)", value=st.session_state.d_day_date)
    if new_d_day != st.session_state.d_day_date:
        st.session_state.d_day_date = new_d_day
        st.rerun()

    st.markdown("---") 
    
    st.subheader("⭐️ 즐겨찾는 루틴 관리")
    
    with st.form("favorite_form", clear_on_submit=True):
        fav_time = st.time_input("루틴 시간", value=datetime.time(9, 0), key="fav_time")
        fav_task = st.text_input("루틴 내용", placeholder="예: 백지 복습", key="fav_task")
        submitted = st.form_submit_button("즐겨찾기 추가")
        
        if submitted and fav_task:
            new_fav = {
                "plan_time": fav_time.strftime("%H:%M"), 
                "task": fav_task, 
                "key": f"{fav_time.strftime('%H:%M')}_{fav_task}"
            }
            if new_fav not in st.session_state.favorite_tasks:
                st.session_state.favorite_tasks.append(new_fav)
                st.session_state.favorite_tasks.sort(key=lambda x: x['plan_time'])
                st.success("루틴이 추가되었습니다!")
            else:
                st.warning("이미 등록된 루틴입니다.")

    if st.session_state.favorite_tasks:
        fav_options = [f"{f['plan_time']} - {f['task']}" for f in st.session_state.favorite_tasks]
        fav_to_delete = st.multiselect("삭제할 루틴 선택", options=fav_options)
        if st.button("선택 루틴 삭제", type="secondary"):
            if fav_to_delete:
                keys_to_delete = [opt.split(" - ", 1) for opt in fav_to_delete]
                keys_to_delete = [f"{k[0]}_{k[1]}" for k in keys_to_delete]
                
                st.session_state.favorite_tasks = [
                    f for f in st.session_state.favorite_tasks if f['key'] not in keys_to_delete
                ]
                st.success("루틴이 삭제되었습니다.")
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
                else: st.warning("이미 오늘의 타임테이블에 있는 할 일입니다.")
    else: st.info("등록된 즐겨찾는 루틴이 없습니다. 설정창에서 추가하세요.")
        
    st.markdown("---")

    st.markdown("##### ➕ 수동으로 타임테이블 추가")
    col_input1, col_input2, col_btn = st.columns([1, 3, 1], vertical_alignment="bottom")
    with col_input1:
        plan_time = st.time_input("시작 시간", value=datetime.time(9, 0), key="manual_time")
    with col_input2:
        new_task = st.text_input("학습할 과목/내용", placeholder="예: 재무회계 기출풀이", key="manual_task")
    with col_btn:
        if st.button("추가하기", use_container_width=True, type="primary"):
            if new_task:
                st.session_state.tasks.append({
                    "plan_time": plan_time.strftime("%H:%M"),
                    "task": new_task,
                    "accumulated": 0,
                    "last_start": None,
                    "is_running": False
                })
                st.rerun()

    st.markdown("---")

    # 3. 리스트 출력 (타임테이블)
    st.session_state.tasks.sort(key=lambda x: x['plan_time'])

    total_seconds = 0
    
    for idx, task in enumerate(st.session_state.tasks):
        c1, c2, c3, c4 = st.columns([1, 3, 2, 0.5], vertical_alignment="center")
        
        with c1: st.markdown(f"**⏰ {task['plan_time']}**")
        with c2: st.markdown(f"{task['task']}")

        with c3:
            current_duration = task['accumulated']
            if task['is_running']: current_duration += time.time() - task['last_start']
            
            t_col1, t_col2 = st.columns([2, 1])
            with t_col1: st.markdown(f"⏱️ `{format_time(current_duration)}`")
            with t_col2:
                if task['is_running']:
                    if st.button("⏹️", key=f"stop_{idx}"):
                        task['accumulated'] += time.time() - task['last_start']
                        task['is_running'] = False
                        task['last_start'] = None
                        st.rerun()
                else:
                    if st.button("▶️", key=f"start_{idx}"):
                        task['is_running'] = True
                        task['last_start'] = time.time()
                        st.rerun()

        with c4:
            if st.button("🗑️", key=f"del_{idx}"):
                del st.session_state.tasks[idx]
                st.rerun()
        
        if task['is_running']: total_seconds += (task['accumulated'] + (time.time() - task['last_start']))
        else: total_seconds += task['accumulated']

    st.divider()

    # 4. 하루 마무리 & 일기
    new_target_time = st.number_input("오늘 목표(시간)", min_value=1.0, value=st.session_state.target_time, step=0.5)
    if new_target_time != st.session_state.target_time:
        st.session_state.target_time = new_target_time
    
    total_hours = total_seconds / 3600
    status = get_status_color(total_hours, st.session_state.target_time)

    m1, m2, m3 = st.columns(3)
    m1.metric("총 순공 시간", format_time(total_seconds))
    m2.metric("목표 달성률", f"{(total_hours / st.session_state.target_time)*100:.1f}%")
    m3.metric("오늘의 평가", status)
    
    # [추가] 일일 학습 일기 입력
    st.markdown("##### 📝 오늘의 성과 정리 (백지 복습 결과 포함)")
    new_reflection = st.text_area(
        "오늘의 학습 성과와 느낀 점을 자유롭게 기록해 주세요. (가장 효과적인 백지 복습 내용이나, 집중이 잘 안된 이유 등)",
        value=st.session_state.daily_reflection, 
        height=150,
        key="reflection_input"
    )
    if new_reflection != st.session_state.daily_reflection:
        st.session_state.daily_reflection = new_reflection


    # [수정] save_to_google_sheets 호출 시 daily_reflection 데이터 전달
    if st.button("💾 구글 시트에 기록 저장하기", type="primary", use_container_width=True):
        if save_to_google_sheets(
            today, 
            total_seconds, 
            status, 
            st.session_state.wakeup_checked, 
            st.session_state.tasks,
            st.session_state.target_time, 
            st.session_state.d_day_date,
            st.session_state.favorite_tasks,
            st.session_state.daily_reflection # <--- 일기 저장
        ):
            st.success("✅ 모든 기록(일기 포함)이 영구 저장되었습니다!")
        else: st.error("저장 실패.")

# ---------------------------------------------------------
# [모드 2] 월간 뷰
# ---------------------------------------------------------
else:
    st.subheader("🗓️ 월간 기록 대시보드")
    try:
        client = get_gspread_client()
        if client and "gcp_service_account" in st.secrets:
            sheet = client.open("CTA_Study_Data").sheet1
            
            records = sheet.get_all_records()
            if records:
                df = pd.DataFrame(records)
                
                columns_to_display = [col for col in df.columns if col not in ['Tasks_JSON', 'Target_Time', 'DDay_Date', 'Favorites_JSON', 'Daily_Reflection']]
                
                st.dataframe(df[columns_to_display], use_container_width=True)
                
                if '기상성공여부' in df.columns:
                    success_count = len(df[df['기상성공여부'] == '성공'])
                    st.info(f"누적 기록: {len(df)}일 | 기상 성공 횟수: {success_count}회")
            else: st.info("아직 저장된 기록이 없습니다.")
        else: st.warning("구글 시트 연동 설정(Secrets)이 필요합니다.")
    except Exception as e: st.warning(f"데이터 로드 중 오류: {e}")
