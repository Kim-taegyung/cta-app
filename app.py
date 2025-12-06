import streamlit as st
import pandas as pd
import datetime
import time
import gspread
import json
import uuid
import calendar
from oauth2client.service_account import ServiceAccountCredentials
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    def st_autorefresh(interval, key): pass

# ---------------------------------------------------------
# 1. 앱 기본 설정 & 상수
# ---------------------------------------------------------
st.set_page_config(page_title="CTA 합격 메이커 V2", page_icon="🔥", layout="wide")

# 카테고리 정의
PROJECT_CATEGORIES = ["CTA 공부", "업무/사업", "건강/운동", "기타/생활"]
CATEGORY_COLORS = {"CTA 공부": "blue", "업무/사업": "orange", "건강/운동": "green", "기타/생활": "gray"}
NON_STUDY_CATEGORIES = ["건강/운동", "기타/생활"] # 집중 시간에서 제외할 카테고리

# ---------------------------------------------------------
# 2. DB 연결 및 CRUD 함수 (RDB 방식)
# ---------------------------------------------------------
@st.cache_resource(ttl=3600)
def get_client():
    if "gcp_service_account" not in st.secrets: return None
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    return gspread.authorize(creds)

def get_sheet(sheet_name):
    client = get_client()
    if not client: return None
    try: return client.open("CTA_Study_Data").worksheet(sheet_name)
    except: return None 

# --- [A] Settings (설정) ---
def load_settings():
    defaults = {
        "telegram_id": "",
        "project_goals": [{"category": "CTA 공부", "name": "1차 시험", "date": str(datetime.date(2026, 4, 25))}]
    }
    sh = get_sheet("Settings")
    if not sh: return defaults
    
    try:
        records = sh.get_all_records()
        for r in records:
            k, v = r.get("Key"), r.get("Value")
            if k in defaults and v:
                defaults[k] = json.loads(v)
        return defaults
    except: return defaults

def save_setting(key, value):
    sh = get_sheet("Settings")
    if not sh: return
    try:
        val_str = json.dumps(value, ensure_ascii=False)
        cell = sh.find(key)
        if cell: sh.update_cell(cell.row, 2, val_str)
        else: sh.append_row([key, val_str])
    except: pass

# --- [B] Daily Task (하루의 데이터 읽기/쓰기) ---
def load_day_data(target_date):
    """
    선택한 날짜의 (1) 마스터 정보(기상,일기 등)와 (2) 상세 할 일 목록을 가져옵니다.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    data = {
        "tasks": [], 
        "master": {"wakeup": False, "reflection": "", "total_time": 0}
    }
    
    client = get_client()
    if not client: return data

    try:
        # 1. Master Data Load
        sh_master = client.open("CTA_Study_Data").worksheet("Daily_Master")
        masters = sh_master.get_all_records()
        day_m = next((item for item in masters if str(item["날짜"]) == date_str), None)
        if day_m:
            data["master"]["wakeup"] = (day_m.get("기상성공") == "TRUE")
            data["master"]["reflection"] = day_m.get("한줄평", "")
            data["master"]["total_time"] = float(day_m.get("총집중시간(초)", 0))

        # 2. Task Details Load
        sh_detail = client.open("CTA_Study_Data").worksheet("Task_Details")
        details = sh_detail.get_all_records()
        # 해당 날짜의 할 일만 필터링
        data["tasks"] = [d for d in details if str(d["날짜"]) == date_str]
        
        # UI용 가공 (accumulated 등)
        for t in data["tasks"]:
            t['is_running'] = False
            t['last_start'] = None
            t['accumulated'] = float(t.get('소요시간(초)', 0))
            
        return data
    except Exception as e:
        print(f"로드 에러: {e}")
        return data

def save_day_data(target_date, tasks, master_data):
    """
    해당 날짜의 기존 데이터를 정리하고 현재 상태로 저장합니다.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    client = get_client()
    if not client: return False
    
    try:
        doc = client.open("CTA_Study_Data")
        
        # 1. Master Update (Upsert)
        sh_m = doc.worksheet("Daily_Master")
        cell = None
        try: cell = sh_m.find(date_str)
        except: pass
        
        row_data = [date_str, "TRUE" if master_data['wakeup'] else "FALSE", master_data['total_time'], master_data['reflection']]
        
        if cell:
            rng = f"A{cell.row}:D{cell.row}"
            sh_m.update(rng, [row_data])
        else:
            sh_m.append_row(row_data)
            
        # 2. Tasks Update (Delete Old -> Insert New)
        sh_d = doc.worksheet("Task_Details")
        
        # 기존 해당 날짜 행들 찾아서 삭제 (역순 삭제가 안전)
        all_vals = sh_d.col_values(2) # B열이 날짜
        rows_to_delete = [i+1 for i, d in enumerate(all_vals) if d == date_str]
        
        for r_idx in reversed(rows_to_delete):
            sh_d.delete_rows(r_idx)
            
        # 새 데이터 추가
        new_rows = []
        for t in tasks:
            # 현재 돌아가는 타이머 시간까지 합산해서 저장
            curr_acc = t['accumulated']
            if t.get('is_running'): curr_acc += (time.time() - t['last_start'])
            
            new_rows.append([
                str(t.get('ID', uuid.uuid4())), # ID
                date_str,                       # 날짜
                t.get('시간', '00:00'),          # 시간
                t.get('카테고리', '기타'),       # 카테고리
                t.get('할일_Main', ''),          # Main
                t.get('할일_Sub', ''),           # Sub
                t.get('상태', '진행중'),         # 상태
                round(curr_acc, 2),             # 소요시간
                t.get('참고자료', '')            # 링크
            ])
        
        if new_rows:
            sh_d.append_rows(new_rows)
            
        return True
    except Exception as e:
        st.error(f"저장 중 오류: {e}")
        return False

# --- [C] Templates (템플릿) ---
def get_templates():
    sh = get_sheet("Templates")
    if not sh: return []
    try: return sh.get_all_records()
    except: return []

# ---------------------------------------------------------
# 3. 세션 및 초기화
# ---------------------------------------------------------
if 'init' not in st.session_state:
    settings = load_settings()
    st.session_state.telegram_id = settings.get('telegram_id', '')
    st.session_state.project_goals = settings.get('project_goals', [])
    st.session_state.tasks = []
    st.session_state.master = {"wakeup": False, "reflection": "", "total_time": 0}
    st.session_state.view_mode = "Daily View"
    st.session_state.selected_date = datetime.date.today()
    st.session_state.loaded_date = None
    st.session_state.init = True

# ---------------------------------------------------------
# 4. UI 컴포넌트
# ---------------------------------------------------------
def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# [팝업] 목표 관리
@st.dialog("🎯 목표(D-Day) 관리")
def goal_manager():
    st.caption("가장 급한 목표가 메인 화면에 표시됩니다.")
    if st.session_state.project_goals:
        for i, g in enumerate(st.session_state.project_goals):
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.markdown(f"**{g['category']}**")
            c2.write(f"{g['name']} ({g['date']})")
            if c3.button("삭제", key=f"del_g_{i}"):
                del st.session_state.project_goals[i]
                save_setting("project_goals", st.session_state.project_goals)
                st.rerun()
    
    with st.form("new_goal"):
        c1, c2 = st.columns(2)
        cat = c1.selectbox("카테고리", PROJECT_CATEGORIES)
        nm = c2.text_input("목표명")
        dt = st.date_input("목표일")
        if st.form_submit_button("추가"):
            st.session_state.project_goals.append({"category": cat, "name": nm, "date": str(dt)})
            st.session_state.project_goals.sort(key=lambda x: x['date'])
            save_setting("project_goals", st.session_state.project_goals)
            st.rerun()

# ---------------------------------------------------------
# 5. 메인 로직 (Daily View)
# ---------------------------------------------------------
def render_daily_view():
    # 1초 리프레시 (타이머 작동 시)
    if any(t.get('is_running') for t in st.session_state.tasks):
        st_autorefresh(interval=1000, key="timer_tick")

    sel_date = st.session_state.selected_date
    
    # [데이터 로드] 날짜가 바뀌었으면 DB에서 가져옴
    if st.session_state.loaded_date != sel_date:
        data = load_day_data(sel_date)
        st.session_state.tasks = data['tasks']
        st.session_state.master = data['master']
        st.session_state.loaded_date = sel_date

    # [헤더] D-Day
    today = datetime.date.today()
    future_goals = [g for g in st.session_state.project_goals if g['date'] >= str(today)]
    header_suffix = ""
    if future_goals:
        pg = min(future_goals, key=lambda x: x['date'])
        d_obj = datetime.datetime.strptime(pg['date'], '%Y-%m-%d').date()
        delta = (d_obj - sel_date).days
        d_str = f"D-{delta}" if delta >= 0 else f"D+{-delta}"
        header_suffix = f"({pg['name']} {d_str})"
    
    st.title(f"📝 {sel_date.strftime('%Y-%m-%d')} {header_suffix}")

    # [상단 컨트롤] 루틴 로드 & 기상 인증
    c1, c2 = st.columns([1, 2], vertical_alignment="center")
    with c1:
        st.session_state.master['wakeup'] = st.checkbox("☀️ 7시 기상 성공!", value=st.session_state.master['wakeup'])
    with c2:
        # 템플릿 불러오기 기능
        templates = get_templates()
        if templates:
            t_names = list(set([t['템플릿명'] for t in templates]))
            sel_temp = st.selectbox("📥 루틴(템플릿) 불러오기", ["선택하세요"] + t_names, label_visibility="collapsed")
            if st.button("적용", use_container_width=True):
                if sel_temp != "선택하세요":
                    new_tasks = [t for t in templates if t['템플릿명'] == sel_temp]
                    for nt in new_tasks:
                        st.session_state.tasks.append({
                            "ID": str(uuid.uuid4()),
                            "시간": nt['시간'],
                            "카테고리": nt['카테고리'],
                            "할일_Main": nt['할일_Main'],
                            "할일_Sub": nt.get('할일_Sub', ''),
                            "상태": "예정",
                            "소요시간(초)": 0,
                            "참고자료": "",
                            "accumulated": 0, "is_running": False
                        })
                    st.rerun()
        else:
            st.caption("등록된 템플릿이 없습니다. (구글 시트 'Templates' 탭에 추가하세요)")
    
    st.divider()

    # [할 일 입력 (Add Task)]
    with st.expander("➕ 새로운 할 일 추가", expanded=True):
        with st.form("add_task_form", clear_on_submit=True):
            c_time, c_cat = st.columns([1, 1])
            i_time = c_time.time_input("시작 시간", datetime.time(9,0))
            i_cat = c_cat.selectbox("카테고리", PROJECT_CATEGORIES)
            
            i_main = st.text_input("메인 목표 (예: 오전 학습 세션)")
            i_sub = st.text_area("세부 목표 (줄바꿈으로 구분)", height=60, placeholder="- 강의 3강 수강\n- 기출문제 10개 풀기")
            i_link = st.text_input("참고 링크/자료")
            
            if st.form_submit_button("등록"):
                st.session_state.tasks.append({
                    "ID": str(uuid.uuid4()),
                    "시간": i_time.strftime("%H:%M"),
                    "카테고리": i_cat,
                    "할일_Main": i_main,
                    "할일_Sub": i_sub,
                    "상태": "예정",
                    "소요시간(초)": 0,
                    "참고자료": i_link,
                    "accumulated": 0, "is_running": False
                })
                st.rerun()

    # [할 일 리스트 (Tree View)]
    if not st.session_state.tasks:
        st.info("등록된 일정이 없습니다.")
    else:
        # 시간순 정렬
        st.session_state.tasks.sort(key=lambda x: x['시간'])
        
        total_focus_sec = 0
        
        for i, t in enumerate(st.session_state.tasks):
            # 1. Main Row
            cat_color = CATEGORY_COLORS.get(t['카테고리'], "gray")
            
            with st.container(border=True):
                # Header: 시간 | 카테고리 | 메인 할일 | 타이머 | 버튼
                c1, c2, c3, c4, c5 = st.columns([1, 1.2, 3.5, 1.2, 1.5], vertical_alignment="center")
                
                c1.text(t['시간'])
                c2.markdown(f":{cat_color}[**{t['카테고리']}**]")
                c3.markdown(f"**{t['할일_Main']}**")
                
                # 타이머 로직
                curr_dur = t['accumulated']
                if t['is_running']: curr_dur += (time.time() - t['last_start'])
                c4.markdown(f"⏱️ `{format_time(curr_dur)}`")
                
                # 버튼 (오늘 날짜만 가능)
                if sel_date == datetime.date.today():
                    if t['is_running']:
                        if c5.button("⏹️ 중지", key=f"stop_{i}", use_container_width=True):
                            t['accumulated'] += (time.time() - t['last_start'])
                            t['is_running'] = False
                            st.rerun()
                    else:
                        if c5.button("▶️ 시작", key=f"start_{i}", use_container_width=True, type="primary"):
                            t['is_running'] = True
                            t['last_start'] = time.time()
                            st.rerun()
                else:
                    c5.caption("-")
                
                # 2. Detail Row (Expander for Details)
                has_detail = bool(t['할일_Sub'] or t['참고자료'])
                exp_label = "🔽 세부 목표 및 메모" if has_detail else "🔽 세부 내용 추가"
                
                with st.expander(exp_label):
                    new_sub = st.text_area("세부 목표", value=t['할일_Sub'], key=f"sub_{i}", height=100)
                    new_link = st.text_input("자료 링크", value=t['참고자료'], key=f"link_{i}")
                    
                    if new_sub != t['할일_Sub'] or new_link != t['참고자료']:
                        t['할일_Sub'] = new_sub
                        t['참고자료'] = new_link
                    
                    if st.button("🗑️ 이 할 일 삭제", key=f"del_{i}"):
                        del st.session_state.tasks[i]
                        st.rerun()

            # 통계 집계
            if t['카테고리'] not in NON_STUDY_CATEGORIES:
                total_focus_sec += curr_dur

    st.markdown("---")
    
    # [하단 통계 및 저장]
    st.subheader("📊 Daily Report")
    
    st.session_state.master['total_time'] = total_focus_sec
    hours = total_focus_sec / 3600
    
    k1, k2 = st.columns(2)
    k1.metric("총 집중 시간", format_time(total_focus_sec))
    k2.metric("평가", "Good" if hours >= 8 else ("Not Bad" if hours >= 5 else "Keep Going"))
    
    st.session_state.master['reflection'] = st.text_area("✍️ 오늘의 회고", value=st.session_state.master['reflection'])
    
    if st.button("💾 모든 기록 저장하기 (Save All)", type="primary", use_container_width=True):
        if save_day_data(sel_date, st.session_state.tasks, st.session_state.master):
            st.success("✅ 안전하게 저장되었습니다!")
        else:
            st.error("❌ 저장 실패. 네트워크를 확인하세요.")

# ---------------------------------------------------------
# 6. 메인 실행부 (Router)
# ---------------------------------------------------------
# 사이드바
with st.sidebar:
    st.title("🗂️ 메뉴")
    if st.button("📝 Daily Planner", use_container_width=True): 
        st.session_state.view_mode = "Daily View"
        st.rerun()
    if st.button("📊 Dashboard", use_container_width=True): 
        st.session_state.view_mode = "Dashboard"
        st.rerun()
        
    st.markdown("---")
    st.subheader("🎯 목표 관리")
    if st.session_state.project_goals:
        today = datetime.date.today()
        for g in st.session_state.project_goals:
            delta = (datetime.datetime.strptime(g['date'], '%Y-%m-%d').date() - today).days
            d_str = f"D-{delta}" if delta >= 0 else f"D+{-delta}"
            st.caption(f"**{g['name']}** ({d_str})")
    if st.button("목표 설정 팝업"): goal_manager()

    st.markdown("---")
    with st.expander("⚙️ 고급 설정"):
        tel_id = st.text_input("텔레그램 ID", value=st.session_state.telegram_id)
        if st.button("ID 저장"):
            st.session_state.telegram_id = tel_id
            save_setting("telegram_id", tel_id)

# 메인 화면 라우팅
if st.session_state.view_mode == "Daily View":
    render_daily_view()
    
elif st.session_state.view_mode == "Dashboard":
    st.title("📊 대시보드")
    client = get_client()
    if client:
        try:
            df = pd.DataFrame(client.open("CTA_Study_Data").worksheet("Daily_Master").get_all_records())
            if not df.empty:
                st.subheader("📅 일별 집중 시간 추이")
                st.line_chart(df, x="날짜", y="총집중시간(초)")
            else:
                st.info("아직 데이터가 없습니다.")
        except: st.error("데이터 로드 실패")
