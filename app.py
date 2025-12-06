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

# [설정] 순공 시간에서 제외할 활동
NON_STUDY_TASKS = ["점심 식사 및 신체 유지 (운동)", "저녁 식사 및 익일 식사 준비", "식사", "운동", "휴식"]

# [설정] 카테고리 정의
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
    return [
        {"plan_time": "08:00", "category": "CTA 공부", "task": "아침 백지 복습", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "13:00", "category": "건강/운동", "task": "점심 식사 및 신체 유지 (운동)", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "19:00", "category": "건강/운동", "task": "저녁 식사 및 익일 식사 준비", "accumulated": 0, "last_start": None, "is_running": False},
        {"plan_time": "21:00", "category": "CTA 공부", "task": "당일 학습 백지 복습", "accumulated": 0, "last_start": None, "is_running": False},
    ]

# [데이터 정제] 화면 그리기 직전에 카테고리 오류 자동 수정
def sanitize_tasks(tasks):
    for t in tasks:
        # 필수 키 없으면 추가
        if 'is_running' not in t: t['is_running'] = False
        if 'accumulated' not in t: t['accumulated'] = 0
        if 'last_start' not in t: t['last_start'] = None
        if 'category' not in t: t['category'] = "CTA 공부"
        
        # 키워드 기반 카테고리 강제 교정 (DB 데이터 오류 해결용)
        content = t.get('task', '')
        if any(x in content for x in ["식사", "점심", "저녁", "운동", "헬스"]):
            t['category'] = "건강/운동"
        elif any(x in content for x in ["복습", "학습", "강의", "기출"]):
            t['category'] = "CTA 공부"
    return tasks

# [설정 저장]
def update_setting(key, value):
    try:
        client = get_gspread_client()
        if client is None: return False
        try: sheet = client.open("CTA_Study_Data").worksheet("Settings")
        except: 
            try:
                sheet = client.open("CTA_Study_Data").add_worksheet(title="Settings", rows=100, cols=2)
                sheet.append_row(["Key", "Value"])
            except: return False

        if key == "project_goals": # 날짜 객체 처리
            val_copy = []
            for item in value:
                c = item.copy()
                if isinstance(c.get('date'), (datetime.date, datetime.datetime)): c['date'] = str(c['date'])
                val_copy.append(c)
            json_val = json.dumps(val_copy, ensure_ascii=False)
        else:
            json_val = json.dumps(value, ensure_ascii=False)
        
        try:
            cell = sheet.find(key)
            sheet.update_cell(cell.row, 2, json_val)
        except: sheet.append_row([key, json_val])
        return True
    except: return False

# [설정 로드]
def load_settings():
    defaults = {
        "telegram_id": "",
        "project_goals": [{"category": "CTA 공부", "name": "1차 시험", "date": datetime.date(2026, 4, 25)}],
        "inbox_items": [],
        "favorite_tasks": []
    }
    try:
        client = get_gspread_client()
        if client is None: return defaults
        try: sheet = client.open("CTA_Study_Data").worksheet("Settings")
        except: return defaults
        
        for row in sheet.get_all_records():
            k = row.get('Key')
            v = row.get('Value')
            if k in defaults and v:
                try:
                    parsed = json.loads(v)
                    if k == 'project_goals':
                        for g in parsed:
                            if isinstance(g.get('date'), str):
                                g['date'] = datetime.datetime.strptime(g['date'], '%Y-%m-%d').date()
                    defaults[k] = parsed
                except: pass
        return defaults
    except: return defaults

# [데일리 저장]
def save_to_google_sheets(date, total_seconds, status, wakeup, tasks, target, d_day, favs, reflection):
    try:
        client = get_gspread_client()
        if client is None: return True
        sheet = client.open("CTA_Study_Data").sheet1
        row = [str(date), round(total_seconds/3600, 2), status, "성공" if wakeup else "실패", 
               json.dumps(tasks), target, str(d_day), json.dumps(favs), reflection]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False

# [데일리 로드]
def load_data_for_date(target_date):
    data = {'tasks': get_default_tasks(), 'target_time': 10.0, 'daily_reflection': "", 'wakeup_checked': False}
    client = get_gspread_client()
    if client is None: return data
    try:
        sheet = client.open("CTA_Study_Data").sheet1
        records = sheet.get_all_records()
        if records:
            df = pd.DataFrame(records)
            day_records = df[df['날짜'] == target_date.strftime('%Y-%m-%d')]
            if not day_records.empty:
                last = day_records.iloc[-1]
                if last.get('Tasks_JSON'):
                    try: 
                        loaded = json.loads(last['Tasks_JSON'])
                        data['tasks'] = sanitize_tasks(loaded) # 로드 즉시 정제
                    except: pass
                data['daily_reflection'] = last.get('Daily_Reflection', "")
                data['wakeup_checked'] = (last.get('기상성공여부') == '성공')
                try: data['target_time'] = float(last.get('Target_Time', 10.0))
                except: pass
        return data
    except: return data

def format_time(seconds):
    m, s = divmod(seconds, 60); h, m = divmod(m, 60)
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
    s = load_settings()
    st.session_state.telegram_id = s['telegram_id']
    st.session_state.project_goals = s['project_goals']
    st.session_state.inbox_items = s['inbox_items']
    st.session_state.favorite_tasks = s['favorite_tasks']
    st.session_state.settings_loaded = True

if 'view_mode' not in st.session_state: st.session_state.view_mode = "Daily View (플래너)"
if 'selected_date' not in st.session_state: st.session_state.selected_date = datetime.date.today()
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.date.today().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.date.today().month
if 'tasks' not in st.session_state: st.session_state.tasks = get_default_tasks()

# ---------------------------------------------------------
# 4. 팝업 UI
# ---------------------------------------------------------
@st.dialog("📥 Inbox 관리", width="large")
def manage_inbox_modal():
    if st.session_state.inbox_items:
        st.write("###### 📋 보관된 항목")
        for i, item in enumerate(st.session_state.inbox_items):
            c1, c2, c3 = st.columns([1, 4, 1], vertical_alignment="center")
            c1.caption(f"[{item['category']}]")
            c2.write(f"**{item['task']}**")
            if c3.button("삭제", key=f"rm_inb_{i}"):
                 del st.session_state.inbox_items[i]
                 update_setting("inbox_items", st.session_state.inbox_items)
                 st.rerun()
            st.divider()
    else: st.info("비어있음")
    
    st.write("###### ➕ 추가")
    with st.form("inbox_add"):
        c1, c2 = st.columns([1, 2])
        cat = c1.selectbox("카테고리", PROJECT_CATEGORIES)
        task = c2.text_input("할 일")
        if st.form_submit_button("저장"):
            st.session_state.inbox_items.append({"category": cat, "task": task, "created_at": str(datetime.datetime.now())})
            update_setting("inbox_items", st.session_state.inbox_items)
            st.rerun()

@st.dialog("🎯 목표 관리")
def show_goal_manager():
    if st.session_state.project_goals:
        for i, g in enumerate(st.session_state.project_goals):
            c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="center")
            c1.markdown(f"**[{g['category']}]**")
            c2.write(f"{g['name']} ({g['date']})")
            if c3.button("삭제", key=f"del_g_{i}"):
                del st.session_state.project_goals[i]
                update_setting("project_goals", st.session_state.project_goals)
                st.rerun()
    else: st.info("목표 없음")
    
    st.write("###### ➕ 추가")
    with st.form("goal_add"):
        c1, c2 = st.columns(2)
        cat = c1.selectbox("카테고리", PROJECT_CATEGORIES)
        name = c2.text_input("목표명")
        d_date = st.date_input("날짜")
        if st.form_submit_button("등록"):
            st.session_state.project_goals.append({"category": cat, "name": name, "date": d_date})
            st.session_state.project_goals.sort(key=lambda x: x['date'])
            update_setting("project_goals", st.session_state.project_goals)
            st.rerun()

def perform_save(target_mode=None):
    today = datetime.date.today()
    goals = [g for g in st.session_state.project_goals if g['date'] >= today]
    main_d = min(goals, key=lambda x: x['date'])['date'] if goals else today
    
    total = 0
    for t in st.session_state.tasks:
        if t['task'] not in NON_STUDY_TASKS:
            dur = t['accumulated']
            if t.get('is_running'): dur += time.time() - t['last_start']
            total += dur
            
    hours = total / 3600
    status = get_status_color(hours, st.session_state.target_time)
    
    if save_to_google_sheets(st.session_state.selected_date, total, status, st.session_state.wakeup_checked,
                             st.session_state.tasks, st.session_state.target_time, main_d,
                             st.session_state.favorite_tasks, st.session_state.daily_reflection):
        st.toast("✅ 저장 완료!")
        time.sleep(0.5)
        if target_mode:
            st.session_state.view_mode = target_mode
            st.rerun()
    else: st.error("저장 실패")

@st.dialog("페이지 이동")
def confirm_nav(target):
    st.write("저장하고 이동하시겠습니까?")
    c1, c2, c3 = st.columns(3)
    if c1.button("저장 & 이동"): perform_save(target)
    if c2.button("이동만"): 
        st.session_state.view_mode = target; st.rerun()
    if c3.button("취소"): st.rerun()

# ---------------------------------------------------------
# 5. 사이드바
# ---------------------------------------------------------
with st.sidebar:
    st.title("🗂️ 메뉴")
    def nav(t):
        if st.session_state.view_mode == "Daily View (플래너)" and st.session_state.view_mode != t: confirm_nav(t)
        else: st.session_state.view_mode = t; st.rerun()

    if st.button("📅 캘린더", use_container_width=True): nav("Monthly View (캘린더)")
    if st.button("📝 플래너", use_container_width=True): nav("Daily View (플래너)")
    if st.button("📊 대시보드", use_container_width=True): nav("Dashboard (대시보드)")
    
    st.markdown("---")
    if st.button(f"📥 Inbox ({len(st.session_state.inbox_items)})", use_container_width=True): manage_inbox_modal()

    if st.session_state.view_mode == "Daily View (플래너)":
        st.markdown("---")
        st.subheader("🎯 목표")
        if st.session_state.project_goals:
            for g in st.session_state.project_goals:
                delta = (g['date'] - datetime.date.today()).days
                d_str = f"D-{delta}" if delta >= 0 else f"D+{-delta}"
                st.caption(f"[{g['category']}] {g['name']} ({d_str})")
        else: st.caption("없음")
        if st.button("목표 설정"): show_goal_manager()

        st.markdown("---")
        # 데이터 로드 트리거
        if 'loaded_date' not in st.session_state or st.session_state.loaded_date != st.session_state.selected_date:
            data = load_data_for_date(st.session_state.selected_date)
            st.session_state.tasks = sanitize_tasks(data['tasks']) # 로드 즉시 정제
            st.session_state.target_time = data['target_time']
            st.session_state.daily_reflection = data['daily_reflection']
            st.session_state.wakeup_checked = data['wakeup_checked']
            st.session_state.loaded_date = st.session_state.selected_date

        st.subheader("⭐️ 즐겨찾기")
        with st.form("fav_add"):
            c_cat = st.selectbox("카테고리", PROJECT_CATEGORIES)
            c_time = st.time_input("시간", value=datetime.time(9,0))
            c_task = st.text_input("내용")
            if st.form_submit_button("생성"):
                st.session_state.favorite_tasks.append({
                    "category": c_cat, "plan_time": c_time.strftime("%H:%M"), "task": c_task
                })
                st.session_state.favorite_tasks.sort(key=lambda x: x['plan_time'])
                update_setting("favorite_tasks", st.session_state.favorite_tasks)
                st.rerun()
        
        if st.session_state.favorite_tasks:
            fav_strs = ["선택하세요"] + [f"[{t['category']}] {t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks]
            del_target = st.selectbox("삭제", fav_strs)
            if st.button("삭제하기"):
                if del_target != "선택하세요":
                    idx = fav_strs.index(del_target) - 1
                    del st.session_state.favorite_tasks[idx]
                    update_setting("favorite_tasks", st.session_state.favorite_tasks)
                    st.rerun()

    st.markdown("---")
    with st.expander("⚙️ 설정"):
        st.session_state.telegram_id = st.text_input("텔레그램 ID", value=st.session_state.telegram_id)
        if st.button("ID 저장"): update_setting("telegram_id", st.session_state.telegram_id)

# ---------------------------------------------------------
# 6. 메인 뷰
# ---------------------------------------------------------
main_col, chat_col = st.columns([2.3, 1])

with main_col:
    # ------------------
    # VIEW 1: Calendar
    # ------------------
    if st.session_state.view_mode == "Monthly View (캘린더)":
        st.title("📅 월간 스케줄")
        c1, c2, c3 = st.columns([1, 5, 1])
        if c1.button("◀"):
            if st.session_state.cal_month==1: st.session_state.cal_month=12; st.session_state.cal_year-=1
            else: st.session_state.cal_month-=1
            st.rerun()
        c2.markdown(f"<h3 style='text-align: center;'>{st.session_state.cal_year}년 {st.session_state.cal_month}월</h3>", unsafe_allow_html=True)
        if c3.button("▶"):
            if st.session_state.cal_month==12: st.session_state.cal_month=1; st.session_state.cal_year+=1
            else: st.session_state.cal_month+=1
            st.rerun()

        # Status Map Load
        status_map = {}
        try:
            client = get_gspread_client()
            if client:
                recs = client.open("CTA_Study_Data").sheet1.get_all_records()
                df = pd.DataFrame(recs)
                last_df = df.groupby('날짜').last().reset_index()
                for _, r in last_df.iterrows(): status_map[r['날짜']] = r['상태']
        except: pass

        # Draw Calendar
        cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
        cols = st.columns(7)
        days = ['월','화','수','목','금','토','일']
        for i, d in enumerate(days): cols[i].markdown(f"**{d}**", unsafe_allow_html=True)
        
        for week in cal:
            cols = st.columns(7)
            for i, d in enumerate(week):
                if d == 0: cols[i].write("")
                else:
                    d_obj = datetime.date(st.session_state.cal_year, st.session_state.cal_month, d)
                    d_str = d_obj.strftime('%Y-%m-%d')
                    icon = "⚪"
                    if d_str in status_map:
                        s = status_map[d_str]
                        if "Good" in s: icon = "🟢"
                        elif "Normal" in s: icon = "🟡"
                        elif "Bad" in s: icon = "🔴"
                    if cols[i].button(f"{d} {icon}", key=f"cal_{d}", use_container_width=True):
                        go_to_daily(d_obj)

    # ------------------
    # VIEW 2: Daily
    # ------------------
    elif st.session_state.view_mode == "Daily View (플래너)":
        if any(t.get('is_running') for t in st.session_state.tasks): st_autorefresh(interval=1000, key="ref")
        
        # [자동 정제] 화면 그릴때마다 실행
        st.session_state.tasks = sanitize_tasks(st.session_state.tasks)

        sel_date = st.session_state.selected_date
        today = datetime.date.today()
        
        # Header D-Day
        goals = [g for g in st.session_state.project_goals if g['date'] >= today]
        if goals:
            main_g = min(goals, key=lambda x: x['date'])
            delta = (main_g['date'] - sel_date).days
            d_str = f"D-{delta}" if delta >= 0 else f"D+{-delta}"
            st.title(f"📝 {sel_date} ({main_g['name']} {d_str})")
        else: st.title(f"📝 {sel_date}")

        # Goal Metrics
        if st.session_state.project_goals:
            cols = st.columns(len(st.session_state.project_goals))
            for i, g in enumerate(st.session_state.project_goals):
                delta = (g['date'] - today).days
                cols[i].metric(f"[{g['category']}] {g['name']}", str(g['date']), f"D-{delta}")
            st.divider()

        c1, c2 = st.columns([1, 2])
        c1.markdown("##### ☀️ 루틴 체크")
        st.session_state.wakeup_checked = c1.checkbox("7시 기상 성공!", value=st.session_state.wakeup_checked)
        
        c2.markdown("##### 🚀 즐겨찾기 추가")
        if st.session_state.favorite_tasks:
            # [심플 로직] 선택된 텍스트와 일치하는 것을 찾아 추가
            fav_strs = ["선택하세요"] + [f"[{t['category']}] {t['plan_time']} - {t['task']}" for t in st.session_state.favorite_tasks]
            sel_fav = c2.selectbox("루틴 선택", fav_strs, label_visibility="collapsed")
            if c2.button("추가", use_container_width=True):
                if sel_fav != "선택하세요":
                    # 1. 원본 객체 찾기
                    found = None
                    for t in st.session_state.favorite_tasks:
                        if f"[{t['category']}] {t['plan_time']} - {t['task']}" == sel_fav:
                            found = t
                            break
                    # 2. 리스트에 추가 (중복 시간 경고)
                    existing_times = [task['plan_time'] for task in st.session_state.tasks]
                    if found['plan_time'] in existing_times:
                        st.warning(f"⚠️ {found['plan_time']}에 이미 일정이 있습니다.")
                    else:
                        st.session_state.tasks.append({
                            "plan_time": found['plan_time'], "category": found['category'],
                            "task": found['task'], "accumulated": 0, "last_start": None, "is_running": False
                        })
                        # 3. 추가 후 정렬
                        st.session_state.tasks.sort(key=lambda x: x['plan_time'])
                        st.rerun()

        st.markdown("---")
        
        # 수동 추가
        with st.container():
            st.caption("➕ 할 일 등록")
            c1, c2, c3, c4 = st.columns([1, 1.5, 3, 1], vertical_alignment="bottom")
            in_time = c1.time_input("시작", value=datetime.time(9,0))
            in_cat = c2.selectbox("프로젝트", PROJECT_CATEGORIES)
            in_task = c3.text_input("내용")
            if c4.button("등록", use_container_width=True):
                t_str = in_time.strftime("%H:%M")
                existing_times = [task['plan_time'] for task in st.session_state.tasks]
                if t_str in existing_times:
                    st.warning(f"⚠️ {t_str}에 이미 일정이 있습니다.")
                else:
                    st.session_state.tasks.append({
                        "plan_time": t_str, "category": in_cat, "task": in_task,
                        "accumulated": 0, "last_start": None, "is_running": False
                    })
                    st.session_state.tasks.sort(key=lambda x: x['plan_time'])
                    st.rerun()

        st.markdown("---")
        
        # [Task List]
        st.subheader("📋 오늘의 할 일")
        
        total_sec = 0
        cat_stats = {c: 0 for c in PROJECT_CATEGORIES}
        
        for i, t in enumerate(st.session_state.tasks):
            # Layout
            c1, c2, c3, c4, c5, c6 = st.columns([1.3, 1.2, 3.5, 1.2, 1, 0.5], vertical_alignment="center")
            
            # Time
            try: t_obj = datetime.datetime.strptime(t['plan_time'], "%H:%M").time()
            except: t_obj = datetime.time(0,0)
            new_time = c1.time_input("time", value=t_obj, key=f"t_{i}", label_visibility="collapsed", disabled=t['is_running'])
            if new_time.strftime("%H:%M") != t['plan_time']:
                t['plan_time'] = new_time.strftime("%H:%M")
                st.session_state.tasks.sort(key=lambda x: x['plan_time'])
                st.rerun()
            
            # Category
            c2.markdown(f":{CATEGORY_COLORS.get(t['category'], 'gray')}[**{t['category']}**]")
            
            # Task
            t['task'] = c3.text_input("task", value=t['task'], key=f"tk_{i}", label_visibility="collapsed", disabled=t['is_running'])
            
            # Timer
            dur = t['accumulated']
            if t['is_running']: dur += time.time() - t['last_start']
            c4.markdown(f"⏱️ **`{format_time(dur)}`**")
            
            # Button
            if sel_date == datetime.date.today():
                if t['is_running']:
                    if c5.button("⏹️ 중지", key=f"stp_{i}", use_container_width=True):
                        t['accumulated'] += time.time() - t['last_start']
                        t['is_running'] = False; st.rerun()
                else:
                    if c5.button("▶️ 시작", key=f"str_{i}", use_container_width=True, type="primary"):
                        t['is_running'] = True; t['last_start'] = time.time(); st.rerun()
            
            # Delete
            if c6.button("🗑️", key=f"del_{i}", disabled=t['is_running']):
                del st.session_state.tasks[i]; st.rerun()
            
            # Stats
            if t['task'] not in NON_STUDY_TASKS:
                curr = t['accumulated']
                if t['is_running']: curr += time.time() - t['last_start']
                total_sec += curr
                if t['category'] in cat_stats: cat_stats[t['category']] += curr
                else: cat_stats[t['category']] = curr

        st.markdown("---")
        
        # Report
        st.subheader("📊 집중 리포트")
        hours = total_sec / 3600
        target = st.session_state.target_time
        
        m1, m2, m3 = st.columns(3)
        m1.metric("총 시간", format_time(total_sec))
        m2.metric("달성률", f"{(hours/target)*100:.1f}%")
        m3.metric("평가", get_status_color(hours, target))
        
        if total_sec > 0:
            for cat in PROJECT_CATEGORIES:
                sec = cat_stats.get(cat, 0)
                if sec > 0:
                    ratio = sec / total_sec
                    st.caption(f"{cat}: {format_time(sec)} ({ratio*100:.1f}%)")
                    st.progress(ratio)
        
        st.divider()
        st.session_state.target_time = st.number_input("목표 시간", value=st.session_state.target_time, step=0.5)
        st.session_state.daily_reflection = st.text_area("회고", value=st.session_state.daily_reflection)
        
        if st.button("💾 저장하기", type="primary", use_container_width=True):
            perform_save()

    # ------------------
    # VIEW 3: Dashboard
    # ------------------
    elif st.session_state.view_mode == "Dashboard (대시보드)":
        st.title("📊 통합 대시보드")
        try:
            client = get_gspread_client()
            if client:
                df = pd.DataFrame(client.open("CTA_Study_Data").sheet1.get_all_records())
                if not df.empty:
                    df['날짜'] = pd.to_datetime(df['날짜'])
                    # 최근 7일 그래프
                    st.subheader("📅 최근 7일 학습 추세")
                    recent = df.sort_values('날짜').tail(7)
                    st.line_chart(recent, x='날짜', y='공부시간(시간)')
                    
                    st.subheader("📋 전체 기록")
                    st.dataframe(df[['날짜', '공부시간(시간)', '상태', 'Daily_Reflection']].sort_values('날짜', ascending=False), use_container_width=True)
                else: st.info("데이터 없음")
        except Exception as e: st.error(f"로드 실패: {e}")

with chat_col:
    st.header("💬 AI Chat")
    st.caption("AI Assistant")
    if "messages" not in st.session_state: st.session_state.messages = []
    with st.container(height=600, border=True):
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
    if p := st.chat_input("질문 입력..."):
        st.session_state.messages.append({"role": "user", "content": p})
        with st.chat_message("user"): st.markdown(p)
        with st.chat_message("assistant"):
            ans = f"Echo: {p}"
            st.markdown(ans)
        st.session_state.messages.append({"role": "assistant", "content": ans})
        st.rerun()
