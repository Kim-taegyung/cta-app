import streamlit as st
import pandas as pd
import datetime
import time
import gspread
import json
import uuid
import calendar
import random # AI 추천 랜덤성을 위해 추가
from oauth2client.service_account import ServiceAccountCredentials
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    def st_autorefresh(interval, key): pass

# ---------------------------------------------------------
# 1. 앱 기본 설정 & 상수
# ---------------------------------------------------------
st.set_page_config(page_title="CTA 합격 메이커 V2", page_icon="🔥", layout="wide")

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
            
        # Task Save
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

# ---------------------------------------------------------
# 3. AI 시뮬레이션 로직 (추천 알고리즘)
# ---------------------------------------------------------
def generate_ai_suggestion(category, main_input):
    """
    사용자의 카테고리와 입력된 메인 목표를 기반으로 세부 할 일을 추천합니다.
    (현재는 룰베이스 시뮬레이션 -> 추후 GPT 연동)
    """
    suggestions = []
    
    if category == "CTA 공부":
        if "세법" in main_input:
            suggestions = ["- 법인세 3강 수강", "- 익금/손금 불산입 항목 암기", "- 기출문제 10문항 풀이 (타이머 필수)"]
        elif "회계" in main_input:
            suggestions = ["- 재무회계 고급 챕터 복습", "- 연결재무제표 작성 연습", "- 오답노트 정리"]
        else:
            suggestions = ["- 오늘 진도 3강 수강하기", "- 백지 복습 20분", "- 핵심 키워드 정리"]
            
    elif category == "업무/사업":
        if "앱" in main_input or "개발" in main_input:
            suggestions = ["- 주요 기능 UI/UX 스케치", "- DB 스키마 설계 점검", "- 버그 리포트 확인 및 수정"]
        elif "미팅" in main_input:
            suggestions = ["- 회의 안건(Agenda) 정리", "- 지난 회의록 리마인드", "- 액션 아이템 도출"]
        else:
            suggestions = ["- 이메일함 정리 및 회신", "- 주간 업무 우선순위 재설정", "- 관련 시장 뉴스 스크랩"]
            
    elif category == "건강/운동":
        suggestions = ["- 스트레칭 10분 (폼롤러)", "- 유산소 30분 (심박수 130 이상)", "- 스쿼트 3세트 진행"]
        
    else:
        suggestions = ["- 책상 정리 및 환기", "- 내일 할 일 미리 계획하기", "- 명상 5분"]
        
    return "\n".join(suggestions)

# ---------------------------------------------------------
# 4. 초기화
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
    st.session_state.ai_suggestion_temp = "" # AI 추천 임시 저장소
    st.session_state.init = True

# ---------------------------------------------------------
# 5. 팝업 UI (Dialogs)
# ---------------------------------------------------------
@st.dialog("📝 템플릿(루틴) 관리", width="large")
def manage_templates_modal():
    st.caption("자주 사용하는 루틴을 세트로 만들어두세요.")
    st.write("###### ➕ 템플릿 항목 추가")
    with st.form("new_template_form", clear_on_submit=True):
        c1, c2 = st.columns([1.5, 1])
        t_name = c1.text_input("템플릿 이름 (예: 평일)", placeholder="묶음 이름")
        t_time = c2.time_input("시간", datetime.time(9,0))
        c3, c4 = st.columns([1, 2])
        t_cat = c3.selectbox("카테고리", PROJECT_CATEGORIES)
        t_main = c4.text_input("할 일 내용")
        if st.form_submit_button("추가"):
            if t_name and t_main:
                add_template_row(t_name, t_time.strftime("%H:%M"), t_cat, t_main, "")
                st.toast(f"'{t_name}'에 추가되었습니다.")
                st.rerun()
            else: st.warning("이름과 내용을 입력해주세요.")

    st.divider()
    st.write("###### 📋 저장된 템플릿 목록")
    templates = get_templates()
    if templates:
        for i, t in enumerate(templates):
            col1, col2, col3, col4 = st.columns([1.5, 3, 1, 0.5], vertical_alignment="center")
            col1.caption(f"[{t['템플릿명']}] {t['시간']}")
            col2.write(f"**{t['할일_Main']}**")
            col3.caption(t['카테고리'])
            if col4.button("x", key=f"del_temp_{i}"):
                delete_template_row(i + 2)
                st.rerun()
    else: st.info("등록된 템플릿이 없습니다.")

@st.dialog("🎯 목표(D-Day) 관리")
def goal_manager():
    st.caption("가장 급한 목표가 메인 화면에 표시됩니다.")
    if st.session_state.project_goals:
        for i, g in enumerate(st.session_state.project_goals):
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.markdown(f"**[{g['category']}]**")
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

@st.dialog("📥 Inbox 관리", width="large")
def manage_inbox_modal():
    if st.session_state.inbox_items:
        st.write("###### 📋 보관된 항목")
        for i, item in enumerate(st.session_state.inbox_items):
            c1, c2, c3 = st.columns([1, 4, 1], vertical_alignment="center")
            c1.caption(f"[{item['category']}]")
            c2.write(f"**{item['task']}**")
            if item.get('memo'): c2.caption(f"└ {item['memo']}")
            if c3.button("삭제", key=f"rm_inb_{i}"):
                 del st.session_state.inbox_items[i]
                 save_setting("inbox_items", st.session_state.inbox_items)
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
            save_setting("inbox_items", st.session_state.inbox_items)
            st.rerun()

# ---------------------------------------------------------
# 6. 메인 로직 (Daily View)
# ---------------------------------------------------------
def render_daily_view():
    if any(t.get('is_running') for t in st.session_state.tasks):
        st_autorefresh(interval=1000, key="timer_tick")

    sel_date = st.session_state.selected_date
    if st.session_state.loaded_date != sel_date:
        data = load_day_data(sel_date)
        st.session_state.tasks = data['tasks']
        st.session_state.master = data['master']
        st.session_state.loaded_date = sel_date

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

    c1, c2 = st.columns([1, 2], vertical_alignment="center")
    with c1:
        st.session_state.master['wakeup'] = st.checkbox("☀️ 7시 기상 성공!", value=st.session_state.master['wakeup'])
    with c2:
        templates = get_templates()
        if templates:
            t_names = sorted(list(set([t['템플릿명'] for t in templates])))
            c_sel, c_btn = st.columns([3, 1])
            sel_temp = c_sel.selectbox("루틴 불러오기", ["선택하세요"] + t_names, label_visibility="collapsed")
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
        else: st.caption("👈 사이드바에서 템플릿을 만들어보세요.")
    
    st.divider()

    # [할 일 입력 + AI Copilot]
    with st.expander("➕ 새로운 할 일 추가 / ✨ AI Copilot", expanded=True):
        # AI 제안 버튼 (Form 밖에 배치하여 즉시 반응)
        c_ai1, c_ai2 = st.columns([3, 1], vertical_alignment="bottom")
        
        with st.form("add_task_form", clear_on_submit=False):
            c_time, c_cat = st.columns([1, 1])
            i_time = c_time.time_input("시작 시간", datetime.time(9,0))
            i_cat = c_cat.selectbox("카테고리", PROJECT_CATEGORIES, key="input_cat")
            
            i_main = st.text_input("메인 목표 (예: 오전 학습 세션)", key="input_main")
            
            # AI 버튼 클릭 시 텍스트 채우기 로직
            if st.form_submit_button("✨ AI 제안 받기 (클릭)"):
                suggestion = generate_ai_suggestion(i_cat, i_main)
                st.session_state.ai_suggestion_temp = suggestion
                st.rerun()

            # 세부 목표 (AI 제안이 있으면 그걸 기본값으로)
            default_sub = st.session_state.get("ai_suggestion_temp", "")
            i_sub = st.text_area("세부 목표 (줄바꿈으로 구분)", value=default_sub, height=100, placeholder="- 강의 3강 수강\n- 기출문제 10개 풀기")
            i_link = st.text_input("참고 링크/자료")
            
            if st.form_submit_button("등록 (Save Task)", type="primary"):
                st.session_state.tasks.append({
                    "ID": str(uuid.uuid4()), "시간": i_time.strftime("%H:%M"), "카테고리": i_cat,
                    "할일_Main": i_main, "할일_Sub": i_sub, "상태": "예정",
                    "소요시간(초)": 0, "참고자료": i_link, "accumulated": 0, "is_running": False
                })
                st.session_state.ai_suggestion_temp = "" # 등록 후 초기화
                st.rerun()

    if not st.session_state.tasks:
        st.info("등록된 일정이 없습니다.")
    else:
        st.session_state.tasks.sort(key=lambda x: x['시간'])
        total_focus_sec = 0
        
        for i, t in enumerate(st.session_state.tasks):
            cat_color = CATEGORY_COLORS.get(t['카테고리'], "gray")
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([1, 1.2, 3.5, 1.2, 1.5], vertical_alignment="center")
                c1.text(t['시간'])
                c2.markdown(f":{cat_color}[**{t['카테고리']}**]")
                c3.markdown(f"**{t['할일_Main']}**")
                
                curr_dur = t['accumulated']
                if t['is_running']: curr_dur += (time.time() - t['last_start'])
                c4.markdown(f"⏱️ `{format_time(curr_dur)}`")
                
                if sel_date == datetime.date.today():
                    if t['is_running']:
                        if c5.button("⏹️ 중지", key=f"stop_{i}", use_container_width=True):
                            t['accumulated'] += (time.time() - t['last_start'])
                            t['is_running'] = False; st.rerun()
                    else:
                        if c5.button("▶️ 시작", key=f"start_{i}", use_container_width=True, type="primary"):
                            t['is_running'] = True; t['last_start'] = time.time(); st.rerun()
                else: c5.caption("-")
                
                has_detail = bool(t['할일_Sub'] or t['참고자료'])
                exp_label = "🔽 세부 내용" if has_detail else "🔽 추가"
                with st.expander(exp_label):
                    new_sub = st.text_area("세부 목표", value=t['할일_Sub'], key=f"sub_{i}")
                    new_link = st.text_input("자료 링크", value=t['참고자료'], key=f"link_{i}")
                    if new_sub != t['할일_Sub'] or new_link != t['참고자료']:
                        t['할일_Sub'] = new_sub; t['참고자료'] = new_link
                    
                    if st.button("🗑️ 삭제", key=f"del_{i}"):
                        del st.session_state.tasks[i]; st.rerun()

            if t['카테고리'] not in NON_STUDY_CATEGORIES: total_focus_sec += curr_dur

    st.markdown("---")
    st.subheader("📊 Daily Report")
    st.session_state.master['total_time'] = total_focus_sec
    hours = total_focus_sec / 3600
    
    k1, k2 = st.columns(2)
    k1.metric("총 집중 시간", format_time(total_focus_sec))
    k2.metric("평가", "Good" if hours >= 8 else "Fighting")
    
    st.session_state.master['reflection'] = st.text_area("✍️ 오늘의 회고", value=st.session_state.master['reflection'])
    
    if st.button("💾 모든 기록 저장하기", type="primary", use_container_width=True):
        if save_day_data(sel_date, st.session_state.tasks, st.session_state.master):
            st.success("✅ 저장되었습니다!")
        else: st.error("❌ 저장 실패")

# ---------------------------------------------------------
# 7. 실행부 (Router)
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
    
    if st.button("💾 템플릿 관리", use_container_width=True): manage_templates_modal()

    st.markdown("---")
    with st.expander("⚙️ 고급 설정"):
        tel_id = st.text_input("텔레그램 ID", value=st.session_state.telegram_id)
        if st.button("ID 저장"):
            st.session_state.telegram_id = tel_id
            save_setting("telegram_id", tel_id)

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
