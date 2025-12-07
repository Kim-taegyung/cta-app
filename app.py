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
st.set_page_config(page_title="아르칸(Arkan) V2", page_icon="🔥", layout="wide")

PROJECT_CATEGORIES = ["CTA 공부", "업무/사업", "건강/운동", "기타/생활"]
CATEGORY_COLORS = {"CTA 공부": "blue", "업무/사업": "orange", "건강/운동": "green", "기타/생활": "gray"}
NON_STUDY_CATEGORIES = ["건강/운동", "기타/생활"] 

# ---------------------------------------------------------
# 2. DB 연결 및 CRUD 함수
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

# --- Settings ---
def load_settings():
    defaults = {
        "telegram_id": "",
        "project_goals": [{"category": "CTA 공부", "name": "1차 시험", "date": str(datetime.date(2026, 4, 25))}],
        "inbox_items": [] 
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

# --- Daily Task ---
def load_day_data(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    data = {"tasks": [], "master": {"wakeup": False, "reflection": "", "total_time": 0}}
    client = get_client()
    if not client: return data

    try:
        sh_master = client.open("CTA_Study_Data").worksheet("Daily_Master")
        masters = sh_master.get_all_records()
        day_m = next((item for item in masters if str(item["날짜"]) == date_str), None)
        if day_m:
            data["master"]["wakeup"] = (str(day_m.get("기상성공")).upper() == "TRUE")
            data["master"]["reflection"] = day_m.get("한줄평", "")
            data["master"]["total_time"] = float(day_m.get("총집중시간(초)", 0))

        sh_detail = client.open("CTA_Study_Data").worksheet("Task_Details")
        details = sh_detail.get_all_records()
        data["tasks"] = [d for d in details if str(d["날짜"]) == date_str]
        
        for t in data["tasks"]:
            t['is_running'] = False
            t['last_start'] = None
            t['accumulated'] = float(t.get('소요시간(초)', 0))
        return data
    except: return data

def save_day_data(target_date, tasks, master_data):
    date_str = target_date.strftime("%Y-%m-%d")
    client = get_client()
    if not client: return False
    try:
        doc = client.open("CTA_Study_Data")
        
        # Master Save
        sh_m = doc.worksheet("Daily_Master")
        cell = None
        try: cell = sh_m.find(date_str)
        except: pass
        row_data = [date_str, "TRUE" if master_data['wakeup'] else "FALSE", master_data['total_time'], master_data['reflection']]
        if cell: sh_m.update(range_name=f"A{cell.row}:D{cell.row}", values=[row_data])
        else: sh_m.append_row(row_data)
            
        # Task Save (삭제 후 재입력)
        sh_d = doc.worksheet("Task_Details")
        all_records = sh_d.get_all_records()
        kept_records = [r for r in all_records if str(r.get("날짜")) != date_str]
        
        sh_d.clear()
        sh_d.append_row(["ID", "날짜", "시간", "카테고리", "할일_Main", "할일_Sub", "상태", "소요시간(초)", "참고자료"])
        
        rows_to_add = []
        for r in kept_records: rows_to_add.append(list(r.values()))
        
        for t in tasks:
            curr_acc = t['accumulated']
            if t.get('is_running'): curr_acc += (time.time() - t['last_start'])
            rows_to_add.append([
                str(t.get('ID', uuid.uuid4())), date_str, t.get('시간', '00:00'),
                t.get('카테고리', '기타'), t.get('할일_Main', ''), t.get('할일_Sub', ''),
                t.get('상태', '진행중'), round(curr_acc, 2), t.get('참고자료', '')
            ])
        if rows_to_add: sh_d.append_rows(rows_to_add)
        return True
    except Exception as e:
        st.error(f"저장 오류: {e}")
        return False

# --- Templates ---
def get_templates():
    sh = get_sheet("Templates")
    if not sh: return []
    try: return sh.get_all_records()
    except: return []

def add_template_row(name, time_str, cat, main, sub):
    sh = get_sheet("Templates")
    if not sh: return
    try: sh.append_row([name, time_str, cat, main, sub])
    except: pass

def delete_template_row(row_idx):
    sh = get_sheet("Templates")
    if not sh: return
    try: sh.delete_rows(row_idx)
    except: pass

# --- Context Saver ---
def get_last_work_context():
    sh = get_sheet("Task_Details")
    if not sh: return None
    try:
        records = sh.get_all_records()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        for r in reversed(records):
            if r.get("카테고리") == "업무/사업" and r.get("날짜") != today_str:
                return r
        return None
    except: return None

# --- AI Suggestion ---
def generate_ai_suggestion(category, main_input):
    suggestions = []
    if category == "CTA 공부":
        if "세법" in main_input: suggestions = ["- 법인세 3강 수강", "- 익금/손금 암기", "- 기출 10문제"]
        else: suggestions = ["- 진도 3강 수강", "- 백지 복습 20분", "- 핵심 키워드 정리"]
    elif category == "업무/사업":
        if "앱" in main_input: suggestions = ["- UI/UX 스케치", "- DB 설계 점검", "- 버그 수정"]
        else: suggestions = ["- 메일 회신", "- 주간 우선순위 설정", "- 뉴스 스크랩"]
    elif category == "건강/운동":
        suggestions = ["- 스트레칭 10분", "- 유산소 30분", "- 스쿼트 3세트"]
    else: suggestions = ["- 책상 정리", "- 내일 계획", "- 명상"]
    return "\n".join(suggestions)

# ---------------------------------------------------------
# 3. 초기화
# ---------------------------------------------------------
if 'init' not in st.session_state:
    settings = load_settings()
    st.session_state.telegram_id = settings.get('telegram_id', '')
    st.session_state.project_goals = settings.get('project_goals', [])
    st.session_state.inbox_items = settings.get('inbox_items', [])
    st.session_state.tasks = []
    st.session_state.master = {"wakeup": False, "reflection": "", "total_time": 0}
    st.session_state.view_mode = "Daily View"
    st.session_state.selected_date = datetime.date.today()
    st.session_state.loaded_date = None
    st.session_state.ai_suggestion_temp = ""
    st.session_state.init = True

# ---------------------------------------------------------
# 4. 팝업 UI (Dialogs)
# ---------------------------------------------------------
@st.dialog("📝 템플릿 관리", width="large")
def manage_templates_modal():
    st.caption("자주 사용하는 루틴을 세트로 만드세요. (업무용은 여기서 만들면 '업무 템플릿' 팝업에 뜹니다)")
    with st.form("new_temp", clear_on_submit=True):
        c1, c2 = st.columns([1.5, 1])
        t_name = c1.text_input("템플릿명 (예: 평일, 업무기본)")
        t_time = c2.time_input("시간", datetime.time(9,0))
        c3, c4 = st.columns([1, 2])
        t_cat = c3.selectbox("카테고리", PROJECT_CATEGORIES)
        t_main = c4.text_input("할 일")
        if st.form_submit_button("추가"):
            if t_name and t_main:
                add_template_row(t_name, t_time.strftime("%H:%M"), t_cat, t_main, "")
                st.rerun()
            else: st.warning("내용 필수")
    
    st.divider()
    st.write("###### 📋 목록")
    templates = get_templates()
    if templates:
        for i, t in enumerate(templates):
            c1, c2, c3, c4 = st.columns([1.5, 3, 1, 0.5], vertical_alignment="center")
            c1.caption(f"[{t['템플릿명']}] {t['시간']}")
            c2.write(f"**{t['할일_Main']}**")
            c3.caption(t['카테고리'])
            if c4.button("x", key=f"del_tm_{i}"):
                delete_template_row(i + 2)
                st.rerun()
    else: st.info("없음")

# [NEW] 업무 템플릿 (체크리스트 & 문맥기억)
@st.dialog("💼 업무 루틴 가져오기", width="large")
def manage_work_template_modal():
    st.caption("오늘 처리할 업무를 선택하세요.")
    
    # 1. 문맥 기억 (Context Saver)
    last_work = get_last_work_context()
    if last_work:
        st.markdown("##### 🔔 어제 하던 일 (Context)")
        with st.container(border=True):
            c1, c2 = st.columns([0.1, 0.9])
            resume = c1.checkbox("resume", label_visibility="collapsed", value=True, key="ctx_chk")
            c2.markdown(f"**[{last_work['카테고리']}] {last_work['할일_Main']}**")
            if last_work.get('할일_Sub'): c2.caption(f"└ {last_work['할일_Sub']}")
    
    st.markdown("---")
    
    # 2. 업무 템플릿 (체크리스트)
    st.markdown("##### 📋 업무 리스트 (선택)")
    templates = get_templates()
    # 카테고리가 '업무/사업'인 것만 필터링
    work_templates = [t for t in templates if t['카테고리'] == '업무/사업']
    
    selected_works = []
    
    if work_templates:
        cols = st.columns(2)
        for i, t in enumerate(work_templates):
            with cols[i % 2]:
                if st.checkbox(f"[{t['시간']}] {t['할일_Main']}", key=f"wk_{i}"):
                    selected_works.append(t)
    else:
        st.info("등록된 업무 템플릿이 없습니다. '템플릿 관리'에서 추가하세요.")

    st.markdown("---")
    if st.button("선택 항목 추가하기", type="primary", use_container_width=True):
        # 문맥 추가
        if last_work and st.session_state.get("ctx_chk"):
            st.session_state.tasks.append({
                "ID": str(uuid.uuid4()), "시간": datetime.datetime.now().strftime("%H:%M"), 
                "카테고리": last_work['카테고리'], "할일_Main": f"{last_work['할일_Main']} (이어서)",
                "할일_Sub": last_work['할일_Sub'], "상태": "예정", "소요시간(초)": 0, "참고자료": last_work['참고자료'],
                "accumulated": 0, "is_running": False
            })
        
        # 체크리스트 추가
        for wt in selected_works:
            st.session_state.tasks.append({
                "ID": str(uuid.uuid4()), "시간": wt['시간'], "카테고리": wt['카테고리'],
                "할일_Main": wt['할일_Main'], "할일_Sub": wt.get('할일_Sub', ''),
                "상태": "예정", "소요시간(초)": 0, "참고자료": "",
                "accumulated": 0, "is_running": False
            })
        
        st.rerun()

@st.dialog("🎯 목표 관리")
def goal_manager():
    if st.session_state.project_goals:
        for i, g in enumerate(st.session_state.project_goals):
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.markdown(f"**[{g['category']}]**")
            c2.write(f"{g['name']} ({g['date']})")
            if c3.button("삭제", key=f"del_gl_{i}"):
                del st.session_state.project_goals[i]
                save_setting("project_goals", st.session_state.project_goals)
                st.rerun()
    with st.form("new_gl"):
        c1, c2 = st.columns(2)
        cat = c1.selectbox("카테고리", PROJECT_CATEGORIES)
        nm = c2.text_input("목표명")
        dt = st.date_input("날짜")
        if st.form_submit_button("추가"):
            st.session_state.project_goals.append({"category": cat, "name": nm, "date": str(dt)})
            st.session_state.project_goals.sort(key=lambda x: x['date'])
            save_setting("project_goals", st.session_state.project_goals)
            st.rerun()

@st.dialog("📥 Inbox 관리", width="large")
def manage_inbox_modal():
    if st.session_state.inbox_items:
        for i, item in enumerate(st.session_state.inbox_items):
            c1, c2, c3 = st.columns([1, 4, 1], vertical_alignment="center")
            c1.caption(f"[{item['category']}]")
            c2.write(f"**{item['task']}**")
            if c3.button("삭제", key=f"rm_ib_{i}"):
                 del st.session_state.inbox_items[i]
                 save_setting("inbox_items", st.session_state.inbox_items)
                 st.rerun()
            st.divider()
    with st.form("inb_add"):
        c1, c2 = st.columns([1, 2])
        cat = c1.selectbox("카테고리", PROJECT_CATEGORIES)
        task = c2.text_input("할 일")
        if st.form_submit_button("저장"):
            st.session_state.inbox_items.append({"category": cat, "task": task, "created_at": str(datetime.datetime.now())})
            save_setting("inbox_items", st.session_state.inbox_items)
            st.rerun()

# ---------------------------------------------------------
# 5. 메인 로직 (View)
# ---------------------------------------------------------
def format_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def render_daily_view():
    if any(t.get('is_running') for t in st.session_state.tasks):
        st_autorefresh(interval=1000, key="tick")

    sel_date = st.session_state.selected_date
    if st.session_state.loaded_date != sel_date:
        data = load_day_data(sel_date)
        st.session_state.tasks = data['tasks']
        st.session_state.master = data['master']
        st.session_state.loaded_date = sel_date

    today = datetime.date.today()
    future = [g for g in st.session_state.project_goals if g['date'] >= str(today)]
    suffix = ""
    if future:
        pg = min(future, key=lambda x: x['date'])
        d_obj = datetime.datetime.strptime(pg['date'], '%Y-%m-%d').date()
        delta = (d_obj - sel_date).days
        d_str = f"D-{delta}" if delta >= 0 else f"D+{-delta}"
        suffix = f"({pg['name']} {d_str})"
    
    st.title(f"📝 {sel_date.strftime('%Y-%m-%d')} {suffix}")

    c1, c2 = st.columns([1, 2], vertical_alignment="center")
    with c1:
        st.session_state.master['wakeup'] = st.checkbox("☀️ 7시 기상 성공!", value=st.session_state.master['wakeup'])
    with c2:
        # [학습 템플릿] (세트 메뉴)
        templates = get_templates()
        if templates:
            study_templates = [t for t in templates if t['카테고리'] != '업무/사업']
            t_names = sorted(list(set([t['템플릿명'] for t in study_templates])))
            
            c_sel, c_btn = st.columns([3, 1])
            sel_temp = c_sel.selectbox("📚 학습 루틴", ["선택하세요"] + t_names, label_visibility="collapsed")
            if c_btn.button("적용", use_container_width=True):
                if sel_temp != "선택하세요":
                    new_tasks = [t for t in templates if t['템플릿명'] == sel_temp]
                    for nt in new_tasks:
                        st.session_state.tasks.append({
                            "ID": str(uuid.uuid4()), "시간": nt['시간'], "카테고리": nt['카테고리'],
                            "할일_Main": nt['할일_Main'], "할일_Sub": nt.get('할일_Sub', ''),
                            "상태": "예정", "소요시간(초)": 0, "참고자료": "",
                            "accumulated": 0, "is_running": False
                        })
                    st.rerun()
        else: st.caption("👈 템플릿 관리에서 루틴 생성")
    
    st.divider()

    # [할 일 입력 + AI]
    with st.expander("➕ 할 일 추가 / ✨ AI Copilot", expanded=True):
        c_ai1, c_ai2 = st.columns([3, 1], vertical_alignment="bottom")
        
        # Form Start
        with st.form("add_tsk", clear_on_submit=False):
            c1, c2 = st.columns([1, 1])
            i_time = c1.time_input("시작", datetime.time(9,0))
            i_cat = c_cat = c2.selectbox("카테고리", PROJECT_CATEGORIES)
            i_main = st.text_input("메인 목표")
            
            # AI 버튼은 form_submit_button이어야 함
            ai_clicked = st.form_submit_button("✨ AI 제안 받기")
            
            # 세부 목표 필드
            def_sub = st.session_state.get("ai_suggestion_temp", "")
            i_sub = st.text_area("세부 목표", value=def_sub, height=100)
            i_link = st.text_input("링크")
            
            # 등록 버튼
            submitted = st.form_submit_button("등록", type="primary")
            
            if ai_clicked:
                st.session_state.ai_suggestion_temp = generate_ai_suggestion(i_cat, i_main)
                st.rerun()

            if submitted:
                st.session_state.tasks.append({
                    "ID": str(uuid.uuid4()), "시간": i_time.strftime("%H:%M"), "카테고리": i_cat,
                    "할일_Main": i_main, "할일_Sub": i_sub, "상태": "예정",
                    "소요시간(초)": 0, "참고자료": i_link, "accumulated": 0, "is_running": False
                })
                st.session_state.ai_suggestion_temp = ""
                st.rerun()

    # [통계 변수 초기화 - 에러 방지]
    total_focus_sec = 0
    cat_stats = {cat: 0 for cat in PROJECT_CATEGORIES}

    if not st.session_state.tasks:
        st.info("일정이 없습니다.")
    else:
        st.session_state.tasks.sort(key=lambda x: x['시간'])
        for i, t in enumerate(st.session_state.tasks):
            cat_color = CATEGORY_COLORS.get(t['카테고리'], "gray")
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([1, 1.2, 3.5, 1.2, 1.5], vertical_alignment="center")
                c1.text(t['시간'])
                c2.markdown(f":{cat_color}[**{t['카테고리']}**]")
                c3.markdown(f"**{t['할일_Main']}**")
                
                curr = t['accumulated']
                if t['is_running']: curr += (time.time() - t['last_start'])
                c4.markdown(f"⏱️ `{format_time(curr)}`")
                
                if sel_date == datetime.date.today():
                    if t['is_running']:
                        if c5.button("⏹️ 중지", key=f"stp_{i}", use_container_width=True):
                            t['accumulated'] += (time.time() - t['last_start'])
                            t['is_running'] = False; st.rerun()
                    else:
                        if c5.button("▶️ 시작", key=f"str_{i}", use_container_width=True, type="primary"):
                            t['is_running'] = True; t['last_start'] = time.time(); st.rerun()
                else: c5.caption("-")
                
                has_dt = bool(t['할일_Sub'] or t['참고자료'])
                exp_lbl = "🔽 세부 내용" if has_dt else "🔽 추가"
                with st.expander(exp_lbl):
                    n_sub = st.text_area("세부 목표", value=t['할일_Sub'], key=f"sb_{i}")
                    n_lnk = st.text_input("링크", value=t['참고자료'], key=f"lk_{i}")
                    if n_sub != t['할일_Sub'] or n_lnk != t['참고자료']:
                        t['할일_Sub'] = n_sub; t['참고자료'] = n_lnk
                    if st.button("🗑️ 삭제", key=f"dl_{i}"):
                        del st.session_state.tasks[i]; st.rerun()

            if t['카테고리'] not in NON_STUDY_CATEGORIES:
                total_focus_sec += curr
                cat_stats[t['카테고리']] = cat_stats.get(t['카테고리'], 0) + curr

    st.markdown("---")
    st.subheader("📊 Daily Report")
    st.session_state.master['total_time'] = total_focus_sec
    hours = total_focus_sec / 3600
    
    k1, k2 = st.columns(2)
    k1.metric("총 집중 시간", format_time(total_focus_sec))
    k2.metric("평가", "Good" if hours >= 8 else "Fighting")
    
    if total_focus_sec > 0:
        for cat, sec in cat_stats.items():
            if sec > 0:
                ratio = sec / total_focus_sec
                st.progress(ratio, text=f"{cat} ({int(ratio*100)}%)")

    st.session_state.master['reflection'] = st.text_area("✍️ 회고", value=st.session_state.master['reflection'])
    
    if st.button("💾 저장하기 (Save)", type="primary", use_container_width=True):
        if save_day_data(sel_date, st.session_state.tasks, st.session_state.master):
            st.success("✅ 저장되었습니다!")
        else: st.error("❌ 저장 실패")

# ---------------------------------------------------------
# 6. 실행부 (Router)
# ---------------------------------------------------------
with st.sidebar:
    st.title("🗂️ 메뉴")
    if st.button("📝 Daily Planner", use_container_width=True): 
        st.session_state.view_mode = "Daily View"; st.rerun()
    if st.button("📊 Dashboard", use_container_width=True): 
        st.session_state.view_mode = "Dashboard"; st.rerun()
    
    st.markdown("---")
    st.subheader("🎯 목표")
    if st.session_state.project_goals:
        today = datetime.date.today()
        for g in st.session_state.project_goals:
            delta = (datetime.datetime.strptime(g['date'], '%Y-%m-%d').date() - today).days
            d_str = f"D-{delta}" if delta >= 0 else f"D+{-delta}"
            st.caption(f"**{g['name']}** ({d_str})")
    if st.button("목표 설정"): goal_manager()
    
    st.markdown("---")
    if st.button(f"📥 Inbox ({len(st.session_state.inbox_items)})", use_container_width=True): manage_inbox_modal()
    
    if st.button("💼 업무 템플릿", use_container_width=True): manage_work_template_modal()
    if st.button("💾 템플릿 관리", use_container_width=True): manage_templates_modal()

    st.markdown("---")
    with st.expander("⚙️ 설정"):
        tel_id = st.text_input("텔레그램 ID", value=st.session_state.telegram_id)
        if st.button("ID 저장"):
            st.session_state.telegram_id = tel_id
            save_setting("telegram_id", tel_id)

# 3단 분할
main_col, chat_col = st.columns([2.2, 1])

with main_col:
    if st.session_state.view_mode == "Daily View":
        render_daily_view()
    elif st.session_state.view_mode == "Dashboard":
        st.title("📊 대시보드")
        client = get_client()
        if client:
            try:
                df = pd.DataFrame(client.open("CTA_Study_Data").worksheet("Daily_Master").get_all_records())
                if not df.empty:
                    st.subheader("📅 집중 시간 추이")
                    st.line_chart(df, x="날짜", y="총집중시간(초)")
                else: st.info("데이터 없음")
            except: st.error("데이터 로드 실패")

with chat_col:
    st.header("💬 AI Coach")
    st.caption("비즈니스 인사이트 & 건강 코칭")
    if "messages" not in st.session_state: 
        st.session_state.messages = [{"role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?"}]

    with st.container(height=600, border=True):
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "video_url" in msg: st.video(msg["video_url"])
                if "news_data" in msg:
                    for n in msg["news_data"]: st.info(f"**{n['title']}**\n{n['summary']}")

    if prompt := st.chat_input("질문 입력..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        with st.chat_message("assistant"):
            resp = ""
            media = {}
            if "스트레칭" in prompt:
                resp = "거북목 교정 스트레칭 영상입니다! 🐢"
                media["video_url"] = "https://www.youtube.com/watch?v=M5J2aaw3YBc"
            elif "뉴스" in prompt:
                resp = "오늘의 주요 뉴스입니다."
                media["news_data"] = [{"title": "금리 인하 전망", "summary": "내년 하반기 금리 인하 가능성..."}]
            else:
                resp = f"입력하신 내용: {prompt}\n(아직은 시뮬레이션입니다)"
            
            st.markdown(resp)
            if "video_url" in media: st.video(media["video_url"])
            if "news_data" in media:
                for n in media["news_data"]: st.info(f"**{n['title']}**\n{n['summary']}")
            
            ai_msg = {"role": "assistant", "content": resp}
            ai_msg.update(media)
            st.session_state.messages.append(ai_msg)
