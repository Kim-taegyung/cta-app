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
# 1. 앱 기본 설정
# ---------------------------------------------------------
st.set_page_config(page_title="CTA 합격 메이커", page_icon="📝", layout="wide")

# [설정] 순공 시간에서 제외할 활동 리스트
NON_STUDY_TASKS = [
    "점심 식사 및 신체 유지 (운동)", 
    "저녁 식사 및 익일 식사 준비"
]

# [설정] 멀티 프로젝트 카테고리 정의
PROJECT_CATEGORIES = ["CTA 공부", "업무/사업", "건강/운동", "기타/생활"]
CATEGORY_COLORS = {"CTA 공부": "blue", "업무/사업": "orange", "건강/운동": "green", "기타/생활": "gray"}

# ---------------------------------------------------------
# 2. 헬퍼 함수
# ---------------------------------------------------------
@st.cache_resource(ttl=3600)
def get_gspread_client():
    if "gcp_service_account" not in st.secrets: return None
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_default_tasks():
    # 기본 템플릿 (카테고리 정확히 명시)
    return [
        {"plan_time": "08:00", "category": "CTA 공부", "task": "아침 백지 복습", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "13:00", "category": "건강/운동", "task": "점심 식사 및 신체 유지 (운동)", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "19:00", "category": "건강/운동", "task": "저녁 식사 및 익일 식사 준비", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "21:00", "category": "CTA 공부", "task": "당일 학습 백지 복습", "accumulated": 0, "last_start": None, "is_running": False},
    ]

# [설정 저장]
def update_setting(key, value):
    try:
        client = get_gspread_client()
        if client is None: return False
        
        try:
            sheet = client.open("CTA_Study_Data").worksheet("Settings")
        except:
            try:
                sheet = client.open("CTA_Study_Data").add_worksheet(title="Settings", rows=100, cols=2)
                sheet.append_row(["Key", "Value"])
            except: return False

        if key == "project_goals":
            value_to_save = []
            for item in value:
                item_copy = item.copy()
                if isinstance(item_copy.get('date'), (datetime.date, datetime.datetime)):
                    item_copy['date'] = str(item_copy['date'])
                value_to_save.append(item_copy)
            json_val = json.dumps(value_to_save, ensure_ascii=False)
        else:
            json_val = json.dumps(value, ensure_ascii=False)
        
        try:
            cell = sheet.find(key)
            sheet.update_cell(cell.row, 2, json_val)
        except gspread.exceptions.CellNotFound:
            sheet.append_row([key, json_val])
        return True
    except Exception: return False

# [설정 로드]
def load_settings():
    default_settings = {
        "telegram_id": "",
        "project_goals": [{"category": "CTA 공부", "name": "1차 시험", "date": datetime.date(2026, 4, 25)}],
        "inbox_items": [],
        "favorite_tasks": [
            {"plan_time": "09:00", "category": "CTA 공부", "task": "오전 학습 세션", "key": "def_1"},
        ]
    }
    
    try:
        client = get_gspread_client()
        if client is None: return default_settings
        
        try: sheet = client.open("CTA_Study_Data").worksheet("Settings")
        except: return default_settings

        records = sheet.get_all_records()
        for row in records:
            k = row.get('Key')
            v = row.get('Value')
            if k in default_settings and v:
                try:
                    loaded_val = json.loads(v)
                    if k == 'project_goals':
                        for g in loaded_val:
                            if isinstance(g.get('date'), str):
                                g['date'] = datetime.datetime.strptime(g['date'], '%Y-%m-%d').date()
                    default_settings[k] = loaded_val
                except: pass
        return default_settings
    except: return default_settings

# [데일리 로그 저장]
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

# [데이터 로드 + 자동 복구 기능]
def load_data_for_date(target_date):
    client = get_gspread_client()
    data = {
        'tasks': get_default_tasks(),
        'target_time': 10.0,
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
                            
                            # [자동 복구 로직] 과거 데이터의 카테고리가 이상하면 내용 기반으로 자동 수정
                            task_name = t.get('task', '')
                            if "점심" in task_name or "저녁" in task_name or "운동" in task_name:
                                if t.get('category') != "건강/운동": t['category'] = "건강/운동"
                            elif "복습" in task_name or "학습" in task_name:
                                if t.get('category') == "미지정" or not t.get('category'): 
                                    t['category'] = "CTA 공부"
                                    
                        data['tasks'] = loaded_tasks
                    except: pass
                
                data['daily_reflection'] = last_record.get('Daily_Reflection', "")
                if last_record.get('기상성공여부') == '성공': data['wakeup_checked'] = True
                try: data['target_time'] = float(last_record.get('Target_Time', 10.0))
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

# ---------------------------------------------------------
# 3. 세션 초기화
# ---------------------------------------------------------
if 'settings_loaded' not in st.session_state:
    settings = load_settings()
    st.session_state.telegram_id = settings['telegram_id']
    st.session_state.project_goals = settings['project_goals']
    st.session_state.inbox_items = settings['inbox_items']
    st.session_state.favorite_tasks = settings['favorite_tasks']
    st.session_state.settings_loaded = True

if 'view_mode' not in st.session_state: st.session_state.view_mode = "Daily View (플래너)"
if 'selected_date' not in st.session_state: st.session_state.selected_date = datetime.date.today()
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.date.today().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.date.today().month
if 'tasks' not in st.session_state: st.session_state.tasks = get_default_tasks()


# ---------------------------------------------------------
# 4. 팝업 및 기능
# ---------------------------------------------------------
@st.dialog("📥 Inbox 관리", width="large")
def manage_inbox_modal():
    st.caption("생각나는 아이디어나 할 일을 보관하고 관리하세요.")
    if st.session_state.inbox_items:
        st.write("###### 📋 보관된 항목")
        for i, item in enumerate(st.session_state.inbox_items):
            c1, c2, c3 = st.columns([1, 4, 1], vertical_alignment="center")
            c1.caption(f"[{item['category']}]")
            c2.write(f"**{item['task']}**")
            if item.get('memo'): c2.caption(f"└ {item['memo']}")
            if c3.button("삭제", key=f"rm_inbox_pop_{i}"):
                 del st.session_state.inbox_items[i]
                 update_setting("inbox_items", st.session_state.inbox_items)
                 st.rerun()
            st.divider()
    else: st.info("보관함이 비어있습니다.")

    st.write("###### ➕ 새 항목 추가")
    with st.form("inbox_add_form", clear_on_submit=True):
        c1, c2 = st.columns([1, 2])
        with c1: 
            cat = st.selectbox("카테고리", PROJECT_CATEGORIES)
            priority = st.selectbox("우선순위", ["높음", "보통", "낮음"], index=1)
        with c2:
            task_name = st.text_input("할 일 내용", placeholder="예: 세법 개정안 확인하기")
            memo = st.text_area("메모 (선택)", height=80, placeholder="구체적인 내용이나 링크 등")
        
        if st.form_submit_button("보관함에 저장"):
            new_item = {
                "category": cat, "task": task_name, "priority": priority, "memo": memo,
                "created_at": str(datetime.datetime.now())
            }
            st.session_state.inbox_items.append(new_item)
            update_setting("inbox_items", st.session_state.inbox_items)
            st.toast(f"✅ Inbox 저장 완료!")
            st.rerun()

@st.dialog("🎯 목표(D-Day) 관리")
def show_goal_manager():
    st.write("프로젝트별 주요 목표일을 관리하세요.")
    if st.session_state.project_goals:
        for i, goal in enumerate(st.session_state.project_goals):
            c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="center")
            c1.markdown(f"**[{goal['category']}]**")
            c2.write(f"{goal['name']} ({goal['date']})")
            if c3.button("삭제", key=f"del_goal_{i}"):
                del st.session_state.project_goals[i]
                update_setting("project_goals", st.session_state.project_goals)
                st.rerun()
    else: st.info("등록된 목표가 없습니다.")

    st.markdown("---")
    st.write("###### ➕ 새 목표 추가")
    with st.form("add_goal_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        cat = c1.selectbox("카테고리", PROJECT_CATEGORIES, key="goal_cat")
        name = c2.text_input("목표명 (예: 2차 시험)", key="goal_name")
        d_date = st.date_input("목표 날짜", key="goal_date")
        
        if st.form_submit_button("목표 등록"):
            st.session_state.project_goals.append({"category": cat, "name": name, "date": d_date})
            st.session_state.project_goals.sort(key=lambda x: x['date'])
            update_setting("project_goals", st.session_state.project_goals)
            st.rerun()

def perform_save(target_mode=None):
    today = datetime.date.today()
    future_goals = [g for g in st.session_state.project_goals if g['date'] >= today]
    main_d_day = min(future_goals, key=lambda x: x['date'])['date'] if future_goals else today

    cur_total = 0
    for t in st.session_state.tasks:
        if t['task'] not in NON_STUDY_TASKS:
            dur = t['accumulated']
            if t.get('is_running'): dur += time.time() - t['last_start']
            cur_total += dur
    cur_hours = cur_total / 3600
    cur_status = get_status_color(cur_hours, st.session_state.target_time)
    
    success = save_to_google_sheets(
        st.session_state.selected_date, cur_total, cur_status, st.session_state.wakeup_checked, 
        st.session_state.tasks, st.session_state.target_time, main_d_day, 
        st.session_state.favorite_tasks, st.session_state.daily_reflection
    )
    if success:
        st.toast("✅ 저장 완료!")
        time.sleep(0.5)
        if target_mode:
            st.session_state.view_mode = target_mode
            st.rerun()
    else: st.error("저장 실패")

@st.dialog("페이지 이동 확인")
def confirm_navigation_modal(target_mode):
    st.write("저장하지 않은 내용은 사라집니다. 이동하시겠습니까?")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("💾 저장 & 이동", use_container_width=True): perform_save(target_mode)
    with c2:
        if st.button("이동만 하기", use_container_width=True):
            st.session_state.view_mode = target_mode
            st.rerun()
    with c3:
        if st.button("취소", use_container_width=True): st.rerun()


# ---------------------------------------------------------
# 5. 사이드바 UI
# ---------------------------------------------------------
with st.sidebar:
    st.title("🗂️ 메뉴")
    
    def try_navigate(target):
        if st.session_state.view_mode == "Daily View (플래너)" and st.session_state.view_mode != target:
            confirm_navigation_modal(target)
        else:
            st.session_state.view_mode = target
            st.rerun()

    if st.button("📅 Monthly View", use_container_width=True): try_navigate("Monthly View (캘린더)")
    if st.button("📝 Daily View", use_container_width=True): try_navigate("Daily View (플래너)")
    if st.button("📊 Dashboard", use_container_width=True): try_navigate("Dashboard (대시보드)")
    
    st.markdown("---")
    
    inbox_cnt = len(st.session_state.inbox_items)
    if st.button(f"📥 Inbox 관리 ({inbox_cnt})", use_container_width=True):
        manage_inbox_modal()

    if st.session_state.view_mode == "Daily View (플래너)":
        st.markdown("---")
        st.subheader("🎯 목표 (D-Day)")
        today = datetime.date.today()
        if st.session_state.project_goals:
            for g in st.session_state.project_goals:
                delta = (g['date'] - today).days
                d_str = f"D-{delta}" if delta > 0 else (f"D+{-delta}" if delta < 0 else "D-Day")
                cat_color = CATEGORY_COLORS.get(g['category'], "gray")
                st.markdown(f":{cat_color}[**{g['name']}**]")
                st.caption(f"{d_str} ({g['date']})")
        else: st.caption("등록된 목표 없음")
        
        if st.button("목표 설정", use_container_width=True):
            show_goal_manager()

        st.markdown("---")
        
        # [데이터 로드] 즐겨찾기(Favorites)는 제외하고 로드
        if 'loaded_date' not in st.session_state or st.session_state.loaded_date != st.session_state.selected_date:
            data = load_data_for_date(st.session_state.selected_date)
            st.session_state.tasks = data['tasks']
            st.session_state.target_time = data['target_time']
            st.session_state.daily_reflection = data['daily_reflection']
            st.session_state.wakeup_checked = data['wakeup_checked']
            st.session_state.loaded_date = st.session_state.selected_date

        st.subheader("⭐️ 즐겨찾기 관리")
        with st.form("fav_manage_form", clear_on_submit=True):
            f_cat = st.selectbox("카테고리", PROJECT_CATEGORIES)
            f_time = st.time_input("시간", value=datetime.time(9,0))
            f_task = st.text_input("루틴 내용")
            if st.form_submit_button("루틴 생성"):
                st.session_state.favorite_tasks.append({
                    "category": f_cat, "plan_time": f_time.strftime("%H:%M"), 
                    "task": f_task, "key": f"{time.time()}"
                })
                st.session_state.favorite_tasks.sort(key=lambda x: x['plan_time'])
                update_setting("favorite_tasks", st.session_state.favorite_tasks)
                st.rerun()
        
        if st.session_state.favorite_tasks:
            # 삭제용 리스트 (안전하게 인덱스 처리)
            fav_del_list = [f"[{t.get('category','-')}] {t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks]
            del_target = st.selectbox("삭제할 루틴", ["선택하세요"] + fav_del_list)
            if st.button("선택한 루틴 삭제"):
                if del_target != "선택하세요":
                    idx = fav_del_list.index(del_target)
                    del st.session_state.favorite_tasks[idx]
                    update_setting("favorite_tasks", st.session_state.favorite_tasks)
                    st.rerun()

    st.markdown("---")
    with st.expander("⚙️ 사용자 설정", expanded=False):
        st.session_state.telegram_id = st.text_input("텔레그램 ID", value=st.session_state.telegram_id)
        if st.button("ID 저장"):
            update_setting("telegram_id", st.session_state.telegram_id)
            st.toast("저장되었습니다.")


# ---------------------------------------------------------
# 6. 메인 화면 구성
# ---------------------------------------------------------
main_col, chat_col = st.columns([2.3, 1])

with main_col:
    # [VIEW 1] Monthly View
    if st.session_state.view_mode == "Monthly View (캘린더)":
        st.title("📅 월간 스케줄")
        col_prev, col_curr, col_next = st.columns([1, 5, 1])
        with col_prev:
            if st.button("◀"):
                if st.session_state.cal_month == 1:
                    st.session_state.cal_month = 12; st.session_state.cal_year -= 1
                else: st.session_state.cal_month -= 1
                st.rerun()
        with col_curr:
            st.markdown(f"<h3 style='text-align: center;'>{st.session_state.cal_year}년 {st.session_state.cal_month}월</h3>", unsafe_allow_html=True)
        with col_next:
            if st.button("▶"):
                if st.session_state.cal_month == 12:
                    st.session_state.cal_month = 1; st.session_state.cal_year += 1
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
                    for _, row in df_latest.iterrows(): status_map[row['날짜']] = row['상태']
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
                    if cols[i].button(f"{day} {status_icon}", key=f"cal_{day}", use_container_width=True):
                        go_to_daily(curr_date)

    # [VIEW 2] Daily View
    elif st.session_state.view_mode == "Daily View (플래너)":
        if any(t.get('is_running') for t in st.session_state.tasks):
            st_autorefresh(interval=1000, key="timer_refresh")

        sel_date = st.session_state.selected_date
        today = datetime.date.today()
        future_goals = [g for g in st.session_state.project_goals if g['date'] >= today]
        
        if future_goals:
            primary_goal = min(future_goals, key=lambda x: x['date'])
            d_day_delta = (primary_goal['date'] - sel_date).days
            d_str = f"D-{d_day_delta}" if d_day_delta >= 0 else f"D+{-d_day_delta}"
            header_text = f"📝 {sel_date.strftime('%Y-%m-%d')} ({primary_goal['name']} {d_str})"
        else:
            header_text = f"📝 {sel_date.strftime('%Y-%m-%d')} (목표 설정 필요)"

        curr_utc = datetime.datetime.utcnow()
        curr_kst = curr_utc + datetime.timedelta(hours=9)
        today_kst = curr_kst.date()
        
        st.title(header_text)
        
        # 목표 현황판 (Metric)
        if st.session_state.project_goals:
            cols = st.columns(len(st.session_state.project_goals))
            for i, goal in enumerate(st.session_state.project_goals):
                delta = (goal['date'] - today).days
                d_label = f"D-{delta}" if delta > 0 else (f"D+{-delta}" if delta < 0 else "D-Day")
                delta_color = "inverse" if delta <= 3 and delta >= 0 else "normal"
                with cols[i]:
                    st.metric(
                        label=f"[{goal['category']}] {goal['name']}",
                        value=str(goal['date']),
                        delta=d_label,
                        delta_color=delta_color
                    )
            st.divider()

        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown("##### ☀️ 루틴 체크")
            is_wakeup = st.checkbox("7시 기상 성공!", value=st.session_state.wakeup_checked)
            st.session_state.wakeup_checked = is_wakeup
        with c2:
            st.markdown("##### 🚀 즐겨찾기 추가")
            if st.session_state.favorite_tasks:
                # [안전한 로직] 텍스트 매칭 대신, 인덱스(순서)를 사용하여 정확한 객체 가져오기
                fav_opts = [None] + list(range(len(st.session_state.favorite_tasks)))
                
                def format_fav_option(idx):
                    if idx is None: return "선택하세요"
                    t = st.session_state.favorite_tasks[idx]
                    return f"[{t.get('category','-')}] {t['plan_time']} - {t['task']}"

                sel_idx = st.selectbox("루틴 선택", fav_opts, format_func=format_fav_option, label_visibility="collapsed")
                
                if st.button("추가", use_container_width=True):
                    if sel_idx is not None:
                        fav_obj = st.session_state.favorite_tasks[sel_idx]
                        existing_times = [t['plan_time'] for t in st.session_state.tasks]
                        if fav_obj['plan_time'] in existing_times:
                            st.warning(f"⚠️ {fav_obj['plan_time']}에 이미 일정이 있습니다.")
                        else:
                            st.session_state.tasks.append({
                                "plan_time": fav_obj['plan_time'], 
                                "category": fav_obj.get('category', 'CTA 공부'),
                                "task": fav_obj['task'], "accumulated": 0, 
                                "last_start": None, "is_running": False
                            })
                            st.rerun()

        st.markdown("---")
        
        # 수동 추가
        with st.container():
            st.caption("➕ 할 일 등록")
            c1, c2, c3, c4 = st.columns([1, 1.5, 3, 1], vertical_alignment="bottom")
            with c1: input_time = st.time_input("시작", value=datetime.time(9,0))
            with c2: input_cat = st.selectbox("프로젝트", PROJECT_CATEGORIES, label_visibility="visible")
            with c3: input_task = st.text_input("내용", placeholder="내용 입력")
            with c4:
                if st.button("등록", use_container_width=True):
                    st.session_state.tasks.append({
                        "plan_time": input_time.strftime("%H:%M"), "category": input_cat,
                        "task": input_task, "accumulated": 0, "last_start": None, "is_running": False
                    })
                    st.rerun()

        st.markdown("---")
        
        # 할 일 리스트
        st.subheader("📋 오늘의 할 일")
        st.session_state.tasks.sort(key=lambda x: x['plan_time'])
        
        total_seconds = 0
        cat_stats = {cat: 0 for cat in PROJECT_CATEGORIES}
        
        if not st.session_state.tasks: st.info("등록된 할 일이 없습니다.")

        for i, task in enumerate(st.session_state.tasks):
            c_time, c_cat, c_task, c_timer, c_btn, c_del = st.columns([1.3, 1.2, 3.5, 1.2, 1, 0.5], vertical_alignment="center")
            
            with c_time: 
                try: t_obj = datetime.datetime.strptime(task['plan_time'], "%H:%M").time()
                except: t_obj = datetime.time(0,0)
                new_time = st.time_input("time", value=t_obj, key=f"time_{i}", label_visibility="collapsed", disabled=task['is_running'])
                if new_time.strftime("%H:%M") != task['plan_time']:
                    task['plan_time'] = new_time.strftime("%H:%M"); st.rerun()

            with c_cat:
                cat = task.get('category', 'CTA 공부')
                color = CATEGORY_COLORS.get(cat, 'gray')
                st.markdown(f":{color}[**{cat}**]") 

            with c_task:
                task['task'] = st.text_input("task", value=task['task'], key=f"task_input_{i}", label_visibility="collapsed", disabled=task['is_running'])
                
            with c_timer:
                dur = task['accumulated']
                if task.get('is_running'): dur += time.time() - task['last_start']
                st.markdown(f"⏱️ **`{format_time(dur)}`**")
                
            with c_btn:
                if sel_date == today_kst:
                    if task.get('is_running'):
                        if st.button("⏹️ 중지", key=f"stop_{i}", use_container_width=True):
                            task['accumulated'] += time.time() - task['last_start']
                            task['is_running'] = False; st.rerun()
                    else:
                        if st.button("▶️ 시작", key=f"start_{i}", use_container_width=True, type="primary"):
                            task['is_running'] = True; task['last_start'] = time.time(); st.rerun()
                else: st.caption("-")
                        
            with c_del:
                if st.button("🗑️", key=f"del_{i}", disabled=task.get('is_running')):
                    del st.session_state.tasks[i]; st.rerun()
            
            if task['task'] not in NON_STUDY_TASKS:
                current_dur = task['accumulated']
                if task.get('is_running'): current_dur += (time.time() - task['last_start'])
                total_seconds += current_dur
                if cat in cat_stats: cat_stats[cat] += current_dur
                else: cat_stats[cat] = current_dur

        st.markdown("---")
        
        # 리포트 및 저장
        st.subheader("📊 오늘의 집중 리포트")
        total_hours = total_seconds / 3600
        target = st.session_state.target_time if st.session_state.target_time > 0 else 1 
        
        m1, m2, m3 = st.columns(3)
        m1.metric("총 집중 시간", format_time(total_seconds))
        m2.metric("목표 달성률", f"{(total_hours/target)*100:.1f}%")
        m3.metric("평가", get_status_color(total_hours, st.session_state.target_time))
        
        st.write("###### 📈 프로젝트별 투입 비율")
        if total_seconds > 0:
            for cat in PROJECT_CATEGORIES:
                sec = cat_stats.get(cat, 0)
                if sec > 0:
                    ratio = sec / total_seconds
                    color_name = CATEGORY_COLORS.get(cat, "gray")
                    st.caption(f":{color_name}[{cat}] : {format_time(sec)} ({ratio*100:.1f}%)")
                    st.progress(ratio)
        else: st.info("아직 집중 시간이 기록되지 않았습니다.")

        st.divider()
        st.session_state.target_time = st.number_input("목표 시간 (시간)", value=st.session_state.target_time, step=0.5)
        st.session_state.daily_reflection = st.text_area("✍️ 학습 일기 / 메모", value=st.session_state.daily_reflection, height=100)
        
        if st.button(f"💾 {sel_date} 기록 저장하기", type="primary", use_container_width=True):
            today = datetime.date.today()
            future_goals = [g for g in st.session_state.project_goals if g['date'] >= today]
            main_d_day = min(future_goals, key=lambda x: x['date'])['date'] if future_goals else today
            
            if save_to_google_sheets(sel_date, total_seconds, get_status_color(total_hours, st.session_state.target_time), st.session_state.wakeup_checked, st.session_state.tasks, st.session_state.target_time, main_d_day, st.session_state.favorite_tasks, st.session_state.daily_reflection):
                st.success("저장되었습니다!")
            else: st.error("저장 실패")

    # [VIEW 3] Dashboard
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
                else: st.info("아직 데이터가 없습니다.")
        except: st.error("데이터 로드 중 오류가 발생했습니다.")

with chat_col:
    st.header("💬 AI Chat")
    st.caption("공부 중 궁금한 점을 물어보세요.")
    if "messages" not in st.session_state: st.session_state.messages = []
    with st.container(height=600, border=True):
        for message in st.session_state.messages:
            with st.chat_message(message["role"]): st.markdown(message["content"])
    if prompt := st.chat_input("질문을 입력하세요..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            response = f"입력하신 내용: {prompt} \n(AI 연결 시 답변이 표시됩니다)"
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()
