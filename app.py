import streamlit as st
import pandas as pd
import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. 앱 기본 설정 ---
st.set_page_config(page_title="CTA Pass Maker", page_icon="📝", layout="wide")

# --- 2. 구글 시트 연결 함수 (비밀번호는 Streamlit Secrets에서 가져옴) ---
def save_to_google_sheets(date, total_seconds, status):
    try:
        # Streamlit Cloud의 Secrets 기능을 사용해 인증
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # st.secrets에 저장된 정보를 이용해 인증 정보 생성
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        # 시트 열기 (시트 이름이 정확해야 함!)
        sheet = client.open("CTA_Study_Data").sheet1 
        
        # 데이터 행 추가
        row = [str(date), round(total_seconds/3600, 2), status]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"저장 실패: {e}")
        return False

# 세션 상태 초기화
if 'tasks' not in st.session_state:
    st.session_state.tasks = []
if 'target_time' not in st.session_state:
    st.session_state.target_time = 10.0

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

# --- 3. UI 레이아웃 ---
st.title("📝 CTA 합격 메이커 (Web Ver.)")
mode = st.radio("모드 선택", ["Daily View (오늘의 공부)", "Monthly View (대시보드)"], horizontal=True)

if mode == "Daily View (오늘의 공부)":
    st.subheader(f"📅 {datetime.date.today()}")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        new_task = st.text_input("학습할 과목 입력")
    with col2:
        if st.button("추가", use_container_width=True):
            if new_task:
                st.session_state.tasks.append({"task": new_task, "accumulated": 0, "last_start": None, "is_running": False})
                st.rerun()

    total_seconds = 0
    for idx, task in enumerate(st.session_state.tasks):
        c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
        with c1: st.markdown(f"**{task['task']}**")
        with c2:
            current_duration = task['accumulated']
            if task['is_running']: current_duration += time.time() - task['last_start']
            st.markdown(f"⏱️ `{format_time(current_duration)}`")
        with c3:
            if task['is_running']:
                if st.button("⏹️ 중지", key=f"stop_{idx}"):
                    task['accumulated'] += time.time() - task['last_start']
                    task['is_running'] = False
                    task['last_start'] = None
                    st.rerun()
            else:
                if st.button("▶️ 시작", key=f"start_{idx}"):
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
    st.session_state.target_time = st.number_input("오늘 목표(시간)", min_value=1.0, value=10.0, step=0.5)
    total_hours = total_seconds / 3600
    status = get_status_color(total_hours, st.session_state.target_time)

    m1, m2, m3 = st.columns(3)
    m1.metric("총 순공 시간", format_time(total_seconds))
    m2.metric("목표 달성률", f"{(total_hours / st.session_state.target_time)*100:.1f}%")
    m3.metric("오늘의 평가", status)

    # 저장 버튼 (실제 구글 시트 저장)
    if st.button("💾 구글 시트에 기록 저장하기", type="primary", use_container_width=True):
        if save_to_google_sheets(datetime.date.today(), total_seconds, status):
            st.success("✅ 저장되었습니다! 월간 탭에서 확인하려면 새로고침하세요.")
        else:
            st.error("저장 실패. 설정(Secrets)을 확인해주세요.")

else: # 월간 뷰
    st.subheader("🗓️ 월간 기록 (구글 시트 연동)")
    try:
        # 데이터 불러오기
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("CTA_Study_Data").sheet1
        
        # 모든 기록 가져오기
        records = sheet.get_all_records()
        if records:
            df = pd.DataFrame(records)
            st.dataframe(df, use_container_width=True)
            
            # 간단 통계
            st.info(f"누적 데이터: {len(df)}건")
        else:
            st.info("아직 저장된 기록이 없습니다.")
            
    except Exception as e:
        st.warning("데이터를 불러오려면 먼저 Secrets 설정을 완료해야 합니다.")