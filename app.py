import streamlit as st
import pandas as pd
import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. 앱 기본 설정 ---
st.set_page_config(page_title="CTA 합격 메이커", page_icon="📝", layout="wide")

# --- 2. 구글 시트 연결 함수 ---
def save_to_google_sheets(date, total_seconds, status, wakeup_success):
    try:
        # secrets.toml 파일이 없거나 설정이 안되어 있을 경우 예외처리
        if "gcp_service_account" not in st.secrets:
            st.error("Secrets 설정이 필요합니다. (로컬 테스트 중이라면 이 메시지는 무시하세요)")
            return False
            
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 시트 열기 (시트 이름 확인!)
        sheet = client.open("CTA_Study_Data").sheet1 
        
        # 데이터 행 추가 (날짜, 공부시간, 평가, 기상성공여부)
        row = [str(date), round(total_seconds/3600, 2), status, "성공" if wakeup_success else "실패"]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False

# --- 3. 세션 상태 초기화 ---
if 'tasks' not in st.session_state:
    st.session_state.tasks = [] 
    # tasks 구조 변경: {time: "09:00", task: "과목", accumulated: 0, last_start: None, is_running: False}
if 'target_time' not in st.session_state:
    st.session_state.target_time = 10.0
if 'wakeup_checked' not in st.session_state:
    st.session_state.wakeup_checked = False
if 'd_day_date' not in st.session_state:
    st.session_state.d_day_date = datetime.date(2026, 5, 1) # 기본값 (예시)

# --- 4. 헬퍼 함수 ---
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

# --- 5. 사이드바 (설정) ---
with st.sidebar:
    st.header("⚙️ 설정")
    st.write("시험 예정일(D-Day)을 설정하세요.")
    new_d_day = st.date_input("시험 날짜 선택", value=st.session_state.d_day_date)
    if new_d_day != st.session_state.d_day_date:
        st.session_state.d_day_date = new_d_day
        st.rerun()

# --- 6. 메인 UI 헤더 ---
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
    
    # 1. 7시 기상 인증
    st.markdown("##### ☀️ 아침 루틴")
    is_wakeup = st.checkbox("7시 기상 성공!", value=st.session_state.wakeup_checked, key="wakeup_chk")
    st.session_state.wakeup_checked = is_wakeup # 상태 업데이트
    
    st.divider()

    # 2. 할 일 추가 (타임테이블 방식)
    st.markdown("##### ➕ 타임테이블 추가")
    
    # vertical_alignment="bottom"으로 버튼과 입력창 높이 정렬
    col_input1, col_input2, col_btn = st.columns([1, 3, 1], vertical_alignment="bottom")
    
    with col_input1:
        plan_time = st.time_input("시작 시간", value=datetime.time(9, 0))
    with col_input2:
        new_task = st.text_input("학습할 과목/내용", placeholder="예: 재무회계 기출풀이")
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

    # 3. 리스트 출력 (시작시간 - 할일 - 스탑워치 - 휴지통)
    # 정렬을 위해 task 리스트를 시간순으로 정렬
    st.session_state.tasks.sort(key=lambda x: x['plan_time'])

    total_seconds = 0
    
    for idx, task in enumerate(st.session_state.tasks):
        # 레이아웃 비율: [시간] 1 : [과목] 3 : [타이머] 2 : [삭제] 0.5
        c1, c2, c3, c4 = st.columns([1, 3, 2, 0.5], vertical_alignment="middle")
        
        # Col 1: 시작 시간
        with c1:
            st.markdown(f"**⏰ {task['plan_time']}**")
        
        # Col 2: 할 일
        with c2:
            st.markdown(f"{task['task']}")

        # Col 3: 스탑워치 컨트롤
        with c3:
            # 현재 흐르는 시간 계산
            current_duration = task['accumulated']
            if task['is_running']:
                current_duration += time.time() - task['last_start']
            
            # 타이머 UI (시간 표시 + 버튼)
            t_col1, t_col2 = st.columns([2, 1])
            with t_col1:
                st.markdown(f"⏱️ `{format_time(current_duration)}`")
            with t_col2:
                if task['is_running']:
                    if st.button("⏹️", key=f"stop_{idx}", help="일시정지"):
                        task['accumulated'] += time.time() - task['last_start']
                        task['is_running'] = False
                        task['last_start'] = None
                        st.rerun()
                else:
                    if st.button("▶️", key=f"start_{idx}", help="시작"):
                        task['is_running'] = True
                        task['last_start'] = time.time()
                        st.rerun()

        # Col 4: 삭제 버튼
        with c4:
            if st.button("🗑️", key=f"del_{idx}"):
                del st.session_state.tasks[idx]
                st.rerun()
        
        # 총 시간 집계
        if task['is_running']:
            total_seconds += (task['accumulated'] + (time.time() - task['last_start']))
        else:
            total_seconds += task['accumulated']

    st.divider()

    # 4. 하루 마무리 & 저장
    st.session_state.target_time = st.number_input("오늘 목표(시간)", min_value=1.0, value=st.session_state.target_time, step=0.5)
    total_hours = total_seconds / 3600
    status = get_status_color(total_hours, st.session_state.target_time)

    m1, m2, m3 = st.columns(3)
    m1.metric("총 순공 시간", format_time(total_seconds))
    m2.metric("목표 달성률", f"{(total_hours / st.session_state.target_time)*100:.1f}%")
    m3.metric("오늘의 평가", status)

    if st.button("💾 구글 시트에 기록 저장하기", type="primary", use_container_width=True):
        if save_to_google_sheets(today, total_seconds, status, st.session_state.wakeup_checked):
            st.success("✅ 저장되었습니다! 오늘도 고생하셨습니다.")
        else:
            st.error("저장 실패. 설정(Secrets)을 확인해주세요.")

# ---------------------------------------------------------
# [모드 2] 월간 뷰
# ---------------------------------------------------------
else:
    st.subheader("🗓️ 월간 기록 대시보드")
    
    # 구글 시트 데이터 로드 시도
    try:
        if "gcp_service_account" in st.secrets:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            sheet = client.open("CTA_Study_Data").sheet1
            
            records = sheet.get_all_records()
            if records:
                df = pd.DataFrame(records)
                st.dataframe(df, use_container_width=True)
                
                # 기상 성공 횟수 통계 예시
                if '기상성공여부' in df.columns: # 컬럼이 있다면
                    success_count = len(df[df['기상성공여부'] == '성공'])
                    st.info(f"이번 달 기상 성공 횟수: {success_count}회")
            else:
                st.info("아직 저장된 기록이 없습니다.")
        else:
            st.warning("구글 시트 연동 설정(Secrets)이 필요합니다.")
            
    except Exception as e:
        st.warning("데이터를 불러오는 중 오류가 발생했습니다. (아직 데이터가 없거나 설정 문제)")
