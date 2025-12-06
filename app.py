# ---------------------------------------------------------
# 7. AI Chat (멀티미디어 비서 기능 탑재)
# ---------------------------------------------------------
with chat_col:
    st.header("💬 AI Coach")
    st.caption("비즈니스 인사이트 & 건강 코칭")
    
    # 채팅 기록 초기화
    if "messages" not in st.session_state: 
        st.session_state.messages = [
            {"role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?\n\n💡 **Tip:** '스트레칭', '경제 뉴스', '동기부여'라고 입력해보세요."}
        ]

    # 채팅창 UI (높이 지정으로 스크롤 가능하게)
    with st.container(height=600, border=True):
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                # [핵심] 메시지에 동영상/이미지 정보가 있으면 렌더링
                if "video_url" in msg:
                    st.video(msg["video_url"])
                if "news_data" in msg:
                    for news in msg["news_data"]:
                        st.info(f"**[{news['source']}] {news['title']}**\n\n{news['summary']}")

    # 사용자 입력 처리
    if prompt := st.chat_input("질문을 입력하세요..."):
        # 1. 사용자 메시지 표시
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): 
            st.markdown(prompt)

        # 2. AI 응답 로직 (룰베이스 시뮬레이션)
        with st.chat_message("assistant"):
            response_content = ""
            media_content = {} # 영상이나 뉴스 데이터 담을 그릇
            
            # (A) 건강/운동: 스트레칭 요청 시 유튜브 팝업
            if "스트레칭" in prompt or "운동" in prompt or "목 아파" in prompt:
                response_content = "장시간 공부하느라 목과 어깨가 뭉치셨군요. 🐢\n지금 바로 의자에서 할 수 있는 **5분 거북목 교정 스트레칭** 영상을 준비했습니다. 따라 해보세요!"
                media_content["video_url"] = "https://www.youtube.com/watch?v=M5J2aaw3YBc" # (예시: 피지컬갤러리)
            
            # (B) 비즈니스: 뉴스/시장 파악 요청
            elif "뉴스" in prompt or "시장" in prompt or "경제" in prompt:
                response_content = "📊 **오늘의 주요 핀테크 & 경제 브리핑**입니다.\n환율 변동성과 금리 이슈를 체크해보세요."
                media_content["news_data"] = [
                    {"source": "경제신문", "title": "美 연준, 금리 인하 시그널... 핀테크 시장 영향은?", "summary": "금리 인하 시 스타트업 투자 심리가 회복될 것으로 전망됩니다."},
                    {"source": "IT뉴스", "title": "토스 vs 카카오페이, 외국인 투자자 유치 경쟁", "summary": "국내 핀테크 기업들이 글로벌 시장 확장을 위해 외국인 전용 서비스를 강화하고 있습니다."}
                ]
            
            # (C) 멘탈/동기부여
            elif "하기 싫어" in prompt or "지쳐" in prompt:
                response_content = "많이 힘드시죠? 😥 합격한 선배들도 다 겪었던 과정입니다.\n잠시 머리 식히고 **동기부여 영상** 하나 보고 다시 시작해요. 할 수 있습니다!"
                media_content["video_url"] = "https://www.youtube.com/watch?v=F0IUs8q1YV0" # (예시: 동기부여 영상)

            # (D) 일반 대화
            else:
                response_content = f"입력하신 내용: '{prompt}'\n\n(아직은 시뮬레이션 단계라 '스트레칭', '뉴스' 같은 키워드에만 반응해요!)"

            # 3. 화면에 출력 및 저장
            st.markdown(response_content)
            if "video_url" in media_content:
                st.video(media_content["video_url"])
            if "news_data" in media_content:
                for news in media_content["news_data"]:
                    st.info(f"**[{news['source']}] {news['title']}**\n\n{news['summary']}")
            
            # 세션에 저장 (나중에 다시 봐도 영상이 남아있게)
            ai_msg = {"role": "assistant", "content": response_content}
            ai_msg.update(media_content) # 영상/뉴스 정보 합치기
            st.session_state.messages.append(ai_msg)
            
            # (중요) 채팅창 갱신을 위해 리런
            # st.rerun() # 채팅 입력 직후 리런하면 입력창 포커스가 풀리는 경우가 있어 여기선 생략하거나 필요시 추가
