# modules/trend_analysis_page.py

import streamlit as st
from datetime import datetime, timedelta
import time
import re
import os
import json
import pandas as pd
from dotenv import load_dotenv
from io import BytesIO
import streamlit.components.v1 as components
import altair as alt # Altair 임포트

# --- 모듈 임포트 (경로 조정) ---
from modules import ai_service
from modules import database_manager
from modules import news_crawler
from modules import trend_analyzer
from modules import data_exporter
from modules import email_sender
# from modules import report_automation_page # 이 페이지에서는 직접 임포트하지 않습니다. main_app에서 라우팅합니다.

# --- 페이지 함수 정의 ---
def trend_analysis_page():
    """
    최신 뉴스 기반 트렌드 분석 및 보고서 생성을 수행하는 페이지입니다.
    """
    # 페이지 전체에 여백을 주기 위한 컬럼 설정
    col_left_margin, col_main_content, col_right_margin = st.columns([0.5, 9, 0.5])

    with col_main_content: # 모든 페이지 내용을 이 중앙 컬럼 안에 배치
        st.title("📰 뉴스 트렌드 분석기")
        st.markdown("원하는 키워드로 네이버 뉴스 트렌드를 감지하고, AI가 요약한 기사 내용을 확인하세요.")

        # --- 네비게이션 ---
        col_home_button, col_endorsement_button, col_trend_button = st.columns([0.2, 0.2, 0.6])
        with col_home_button:
            if st.button("🏠 메인화면"):
                st.session_state.page = "landing"
                st.rerun()
        with col_endorsement_button:
            if st.button("📄 특약생성"):
                st.session_state.page = "document"
                st.rerun()
        with col_trend_button:
            if st.button("⏰ 자동화"):
                st.session_state.page = "automation"
                st.rerun()

        st.markdown("---")

        # --- Gemini AI API 키 설정 ---
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

        if not GEMINI_API_KEY:
            st.error("🚨 오류: .env 파일에 'GEMINI_API_KEY'가 설정되지 않았습니다. Gemini AI 기능을 사용할 수 없습니다.")
            return

        # --- 이메일 설정 정보 로드 (수동 전송 기능에만 필요) ---
        SENDER_EMAIL = os.getenv("SENDER_EMAIL")
        SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
        SMTP_SERVER = os.getenv("SMTP_SERVER")
        SMTP_PORT = os.getenv("SMTP_PORT")

        email_config_ok = True
        if not all([SENDER_EMAIL, SENDER_PASSWORD, SMTP_SERVER, SMTP_PORT]):
            st.warning("⚠️ 이메일 전송 기능 활성화를 위해 .env 파일에 SENDER_EMAIL, SENDER_PASSWORD, SMTP_SERVER, SMTP_PORT를 설정해주세요.")
            email_config_ok = False
        else:
            try:
                SMTP_PORT = int(SMTP_PORT)
            except ValueError:
                st.error("🚨 오류: SMTP_PORT는 유효한 숫자여야 합니다.")
                email_config_ok = False


        # 데이터베이스 초기화
        database_manager.init_db()
        all_db_articles = database_manager.get_all_articles()


        # --- Streamlit Session State 초기화 ---
        if 'trending_keywords_data' not in st.session_state:
            st.session_state['trending_keywords_data'] = []
        if 'displayed_keywords' not in st.session_state:
            st.session_state['displayed_keywords'] = []
        if 'final_collected_articles' not in st.session_state:
            st.session_state['final_collected_articles'] = []
        if 'ai_insights_summary' not in st.session_state:
            st.session_state['ai_insights_summary'] = ""
        if 'ai_trend_summary' not in st.session_state:
            st.session_state['ai_trend_summary'] = ""
        if 'ai_insurance_info' not in st.session_state:
            st.session_state['ai_insurance_info'] = ""
        if 'db_status_message' not in st.session_state:
            st.session_state['db_status_message'] = ""
        if 'db_status_type' not in st.session_state:
            st.session_state['db_status_type'] = ""
        if 'prettified_report_for_download' not in st.session_state:
            st.session_state['prettified_report_for_download'] = ""
        if 'formatted_trend_summary' not in st.session_state:
            st.session_state['formatted_trend_summary'] = ""
        if 'formatted_insurance_info' not in st.session_state:
            st.session_state['formatted_insurance_info'] = ""
        if 'email_status_message' not in st.session_state:
            st.session_state['email_status_message'] = ""
        if 'email_status_type' not in st.session_state:
            st.session_state['email_status_type'] = ""
        # 검색 프리셋 관련 세션 상태 (프리셋으로 용어 변경)
        if 'search_presets' not in st.session_state:
            st.session_state['search_presets'] = database_manager.get_search_profiles() # DB 함수명은 유지
        if 'selected_preset_id' not in st.session_state:
            st.session_state['selected_preset_id'] = None
        if 'recipient_emails_input' not in st.session_state: # 이메일 입력 필드 상태
            st.session_state['recipient_emails_input'] = ""
        # 새로 추가: 프리셋 로드 후 자동 분석 트리거 플래그
        if 'trigger_analysis_after_preset_load' not in st.session_state:
            st.session_state['trigger_analysis_after_preset_load'] = False


        # --- UI 레이아웃: 검색 조건 (좌) & 키워드 트렌드 결과 (우) ---
        col_search_input, col_trend_results = st.columns([1, 2])

        # --- 기간 선택을 위한 매핑 딕셔너리 ---
        period_options = {
            "1주": 7, "2주": 14, "3주": 21, "4주": 28,
            "1달": 30, "2달": 60, "3달": 90
        }
        # 역방향 매핑 (저장된 일수를 드롭다운 선택지로 변환하기 위함)
        period_options_reverse = {v: k for k, v in period_options.items()}

        # --- 최근 데이터 일수 드롭다운 옵션 및 매핑 (새로 추가) ---
        recent_days_options = {
            "1일": 1, "2일": 2, "3일": 3, "4일": 4, "5일": 5, "6일": 6, "7일": 7
        }
        recent_days_options_reverse = {v: k for k, v in recent_days_options.items()}

        # --- 페이지 선택 드롭다운 옵션 및 매핑 (새로 추가) ---
        pages_options = {
            "1페이지": 1, "2페이지": 2, "3페이지": 3
        }
        pages_options_reverse = {v: k for k, v in pages_options.items()}


        with col_search_input:
            st.header("🔍 검색 조건 설정")

            # --- 검색 프리셋 관리 (프리셋으로 용어 변경) ---
            st.subheader("저장된 검색 프리셋")
            presets = st.session_state['search_presets'] # 최신 프리셋 목록 가져오기
            preset_names = ["-- 프리셋 선택 --"] + [p['profile_name'] for p in presets] # profile_name은 DB 컬럼명이라 유지
            
            # 현재 선택된 프리셋 ID가 있다면 해당 프리셋의 이름을 기본값으로 설정
            current_preset_name = "-- 프리셋 선택 --"
            if st.session_state['selected_preset_id']:
                selected_preset_obj = next((p for p in presets if p['id'] == st.session_state['selected_preset_id']), None)
                if selected_preset_obj:
                    current_preset_name = selected_preset_obj['profile_name'] # DB 컬럼명 유지

            selected_preset_name = st.selectbox(
                "불러올 프리셋을 선택하세요:", # 프리셋으로 용어 변경
                preset_names, 
                index=preset_names.index(current_preset_name) if current_preset_name in preset_names else 0,
                key="preset_selector" # 키도 프리셋으로 변경
            )
            
            # 프리셋 불러오기/삭제 버튼 (프리셋으로 용어 변경)
            col_load_preset, col_delete_preset = st.columns(2)
            with col_load_preset:
                if st.button("프리셋 불러오기", help="선택된 프리셋의 검색 조건을 적용합니다."):
                    if selected_preset_name != "-- 프리셋 선택 --":
                        selected_preset = next((p for p in presets if p['profile_name'] == selected_preset_name), None)
                        if selected_preset:
                            st.session_state['keyword_input'] = selected_preset['keyword']
                            # total_search_days는 드롭다운 값을 반영하도록 변경
                            st.session_state['total_days_input_display'] = period_options_reverse.get(selected_preset['total_search_days'], "1달") # 기본값 설정
                            # 최근 데이터 일수 드롭다운 값 반영 (수정)
                            st.session_state['recent_days_input_display'] = recent_days_options_reverse.get(selected_preset['recent_trend_days'], "2일") # 기본값 2일
                            # 페이지 선택 드롭다운 값 반영 (수정)
                            st.session_state['max_pages_input_display'] = pages_options_reverse.get(selected_preset['max_naver_search_pages_per_day'], "1페이지") # 기본값 1페이지
                            st.session_state['selected_preset_id'] = selected_preset['id'] # 선택된 프리셋 ID 저장
                            st.info(f"✅ 프리셋 '{selected_preset_name}'이(가) 불러와졌습니다.")
                            
                            # 새로 추가: 프리셋 로드 후 자동 분석 트리거 플래그 설정
                            st.session_state['trigger_analysis_after_preset_load'] = True
                            st.rerun()
                    else:
                        st.warning("불러올 프리셋을 선택해주세요.")
            with col_delete_preset:
                if st.button("프리셋 삭제", help="선택된 프리셋을 데이터베이스에서 삭제합니다."):
                    if selected_preset_name != "-- 프리셋 선택 --":
                        selected_preset = next((p for p in presets if p['profile_name'] == selected_preset_name), None)
                        if selected_preset:
                            if database_manager.delete_search_profile(selected_preset['id']): # DB 함수명은 유지
                                st.success(f"✅ 프리셋 '{selected_preset_name}'이(가) 삭제되었습니다.")
                                st.session_state['search_presets'] = database_manager.get_search_profiles() # 프리셋 목록 새로고침
                                if st.session_state['selected_preset_id'] == selected_preset['id']:
                                    st.session_state['selected_preset_id'] = None # 삭제된 프리셋이 선택되어 있었다면 초기화
                                st.rerun()
                            else:
                                st.error(f"🚨 프리셋 '{selected_preset_name}' 삭제에 실패했습니다.")
                    else:
                        st.warning("삭제할 프리셋을 선택해주세요.")

            with st.form("search_form"):
                keyword = st.text_input("검색할 뉴스 키워드 (예: '전기차')", value=st.session_state.get('keyword_input', "전기차"), key="keyword_input")
                
                # total_search_days를 드롭다운으로 변경
                selected_total_days_display = st.selectbox(
                    "총 몇 일간의 뉴스를 검색할까요?",
                    options=list(period_options.keys()),
                    index=list(period_options.keys()).index(st.session_state.get('total_days_input_display', "1달")), # 기본값 1달
                    key="total_days_input_display",
                    help="과거로부터 총 몇 일간의 뉴스 데이터를 수집할지 설정합니다. 이 기간의 모든 뉴스를 분석하여 키워드를 추출합니다."
                )
                total_search_days = period_options[selected_total_days_display] # 선택된 문자열을 일수로 변환
                
                # --- 최근 데이터 일수 드롭다운으로 변경 (수정) ---
                selected_recent_days_display = st.selectbox(
                    "최근 몇 일간의 데이터를 기준으로 트렌드를 분석할까요?",
                    options=list(recent_days_options.keys()),
                    index=list(recent_days_options.keys()).index(st.session_state.get('recent_days_input_display', "2일")), # 기본값 2일
                    key="recent_days_input_display",
                    help="총 검색 기간 중 최근 몇 일간의 데이터를 '최신 트렌드'로 간주하여, 이전 기간과 비교하여 키워드 언급량의 변화를 감지합니다. 이 값은 총 검색 기간보다 작아야 합니다."
                )
                recent_trend_days = recent_days_options[selected_recent_days_display] # 선택된 문자열을 일수로 변환

                # --- 페이지 선택 드롭다운으로 변경 (수정) ---
                selected_max_pages_display = st.selectbox(
                    "각 날짜별로 네이버 뉴스 검색 결과 몇 페이지까지 크롤링할까요? (페이지당 10개 기사)",
                    options=list(pages_options.keys()),
                    index=list(pages_options.keys()).index(st.session_state.get('max_pages_input_display', "1페이지")), # 기본값 1페이지
                    key="max_pages_input_display",
                    help="네이버 뉴스 검색 결과에서 각 날짜별로 크롤링할 최대 페이지 수를 설정합니다. (페이지당 약 10개의 기사)"
                )
                max_naver_search_pages_per_day = pages_options[selected_max_pages_display] # 선택된 문자열을 정수로 변환


                col_submit, col_save_preset = st.columns([0.7, 0.3]) # 프리셋으로 용어 변경
                with col_submit:
                    # '뉴스 트렌드 분석 시작' 버튼 클릭 또는 프리셋 로드 후 자동 트리거
                    submitted_button = st.form_submit_button("뉴스 트렌드 분석 시작")
                
                # 폼 제출 조건 변경: 버튼 클릭 또는 자동 트리거 플래그
                submitted = submitted_button or st.session_state['trigger_analysis_after_preset_load']

                with col_save_preset: # 프리셋으로 용어 변경
                    preset_name_to_save = st.text_input("프리셋 이름 (저장)", value="", help="현재 검색 설정을 저장할 이름을 입력하세요.") # 프리셋으로 용어 변경
                    if st.form_submit_button("프리셋 저장"): # 프리셋으로 용어 변경
                        if preset_name_to_save:
                            if database_manager.save_search_profile(preset_name_to_save, keyword, total_search_days, recent_trend_days, max_naver_search_pages_per_day): # DB 함수명은 유지
                                st.success(f"✅ 검색 프리셋 '{preset_name_to_save}'이(가) 성공적으로 저장되었습니다.") # 프리셋으로 용어 변경
                                st.session_state['search_presets'] = database_manager.get_search_profiles() # 프리셋 목록 새로고침
                                st.rerun()
                            else:
                                st.error(f"🚨 검색 프리셋 '{preset_name_to_save}' 저장에 실패했습니다. 이미 존재하는 이름일 수 있습니다.") # 프리셋으로 용어 변경
                        else:
                            st.warning("저장할 프리셋 이름을 입력해주세요.") # 프리셋으로 용어 변경

        with col_trend_results:
            st.header("📈 키워드 트렌드 분석 결과")
            st.markdown("다음은 최근 언급량이 급증한 트렌드 키워드입니다.")

            table_placeholder = st.empty()
            status_message_placeholder = st.empty()
            chart_placeholder = st.empty() # 막대 그래프를 위한 플레이스홀더

            # 폼 제출 조건 변경: submitted 변수 사용
            if submitted:
                # 자동 트리거 플래그 초기화 (중요! 무한 루프 방지)
                st.session_state['trigger_analysis_after_preset_load'] = False

                # 새로운 검색 요청 시 기존 상태 초기화
                st.session_state['trending_keywords_data'] = []
                st.session_state['displayed_keywords'] = []
                st.session_state['final_collected_articles'] = []
                st.session_state['ai_insights_summary'] = ""
                st.session_state['ai_trend_summary'] = ""
                st.session_state['ai_insurance_info'] = ""
                st.session_state['prettified_report_for_download'] = ""
                st.session_state['formatted_trend_summary'] = ""
                st.session_state['formatted_insurance_info'] = ""
                st.session_state['email_status_message'] = ""
                st.session_state['email_status_type'] = ""

                table_placeholder.empty()
                my_bar = status_message_placeholder.progress(0, text="데이터 수집 및 분석 진행 중...")
                status_message_placeholder.info("네이버 뉴스 메타데이터 수집 중...")

                # 유효성 검사: recent_trend_days가 total_search_days보다 작아야 함
                if recent_trend_days >= total_search_days:
                    status_message_placeholder.error("오류: 최근 트렌드 분석 기간은 총 검색 기간보다 짧아야 합니다.")
                    st.session_state['analysis_completed'] = False # 분석 실패 상태
                    st.stop() # 더 이상 진행하지 않음


                all_collected_news_metadata = []

                today_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                search_start_date = today_date - timedelta(days=total_search_days - 1)

                total_expected_articles = total_search_days * max_naver_search_pages_per_day * 10
                processed_article_count = 0


                for i in range(total_search_days):
                    current_search_date = search_start_date + timedelta(days=i)
                    formatted_search_date = current_search_date.strftime('%Y-%m-%d')

                    daily_articles = news_crawler.crawl_naver_news_metadata(
                        keyword,
                        current_search_date,
                        max_naver_search_pages_per_day
                    )

                    for article in daily_articles:
                        processed_article_count += 1
                        progress_percentage = processed_article_count / total_expected_articles
                        my_bar.progress(min(progress_percentage, 1.0), text=f"뉴스 메타데이터 수집 중... ({formatted_search_date}, {processed_article_count}개 기사 처리 완료)")


                        article_data_for_db = {
                            "제목": article["제목"],
                            "링크": article["링크"],
                            "날짜": article["날짜"].strftime('%Y-%m-%d'),
                            "내용": article["내용"]
                        }
                        database_manager.insert_article(article_data_for_db)

                        all_collected_news_metadata.append(article)

                my_bar.empty()
                status_message_placeholder.success(f"총 {len(all_collected_news_metadata)}개의 뉴스 메타데이터를 수집했습니다.")

                # --- 2. 키워드 트렌드 분석 실행 ---
                status_message_placeholder.info("키워드 트렌드 분석 중...")
                with st.spinner("키워드 트렌드 분석 중..."):
                    trending_keywords_data = trend_analyzer.analyze_keyword_trends(
                        all_collected_news_metadata,
                        recent_days_period=recent_trend_days,
                        total_days_period=total_search_days
                    )
                st.session_state['trending_keywords_data'] = trending_keywords_data

                if trending_keywords_data:
                    # --- AI가 보험 개발자 관점에서 유의미한 키워드 선별 ---
                    relevant_keywords_from_ai_raw = []
                    with st.spinner("AI가 보험 개발자 관점에서 유의미한 키워드를 선별 중..."):
                        relevant_keywords_from_ai_raw = ai_service.get_relevant_keywords(
                            trending_keywords_data,
                            "차량보험사의 보험개발자",
                            GEMINI_API_KEY
                        )

                    filtered_trending_keywords = []
                    if relevant_keywords_from_ai_raw:
                        filtered_trending_keywords = [
                            kw_data for kw_data in trending_keywords_data
                            if kw_data['keyword'] in relevant_keywords_from_ai_raw
                        ]
                        filtered_trending_keywords = sorted(filtered_trending_keywords, key=lambda x: x['recent_freq'], reverse=True)

                        status_message_placeholder.info(f"AI가 선별한 보험 개발자 관점의 유의미한 키워드 ({len(filtered_trending_keywords)}개): {[kw['keyword'] for kw in filtered_trending_keywords]}")
                    else:
                        status_message_placeholder.warning("AI가 보험 개발자 관점에서 유의미한 키워드를 선별하지 못했습니다. 모든 트렌드 키워드를 표시합니다.")
                        filtered_trending_keywords = trending_keywords_data

                    top_3_relevant_keywords = filtered_trending_keywords[:3]
                    st.session_state['displayed_keywords'] = top_3_relevant_keywords

                    if top_3_relevant_keywords:
                        pass
                    else:
                        status_message_placeholder.info("보험 개발자 관점에서 유의미한 트렌드 키워드가 식별되지 않습니다.")


                    # --- 3. 트렌드 기사 본문 요약 (Gemini AI 활용) ---
                    status_message_placeholder.info("트렌드 기사 본문 요약 중 (Gemini AI 호출)...")

                    recent_trending_articles_candidates = [
                        article for article in all_collected_news_metadata
                        if article.get("날짜") and today_date - timedelta(days=recent_trend_days) <= article["날짜"]
                    ]

                    processed_links = set()

                    articles_for_ai_summary = []
                    for article in recent_trending_articles_candidates:
                        text_for_trend_check = article["제목"] + " " + article.get("내용", "")
                        article_keywords_for_trend = trend_analyzer.extract_keywords_from_text(text_for_trend_check)

                        if any(trend_kw['keyword'] in article_keywords_for_trend for trend_kw in top_3_relevant_keywords):
                            articles_for_ai_summary.append(article)

                    total_ai_articles_to_process = len(articles_for_ai_summary)

                    if total_ai_articles_to_process == 0:
                        status_message_placeholder.info("선별된 트렌드 키워드를 포함하는 최근 기사가 없거나, AI 요약 대상 기사가 없습니다.")
                    else:
                        ai_progress_bar = st.progress(0, text=f"AI가 트렌드 기사를 요약 중... (0/{total_ai_articles_to_process} 완료)")
                        ai_processed_count = 0

                        temp_collected_articles = []
                        for article in articles_for_ai_summary:
                            if article["링크"] in processed_links:
                                continue

                            article_date_str = article["날짜"].strftime('%Y-%m-%d')

                            ai_processed_content = ai_service.get_article_summary(
                                article["제목"],
                                article["링크"],
                                article_date_str,
                                article["내용"],
                                GEMINI_API_KEY,
                                max_attempts=2
                            )

                            final_content = ""
                            if ai_processed_content.startswith("Gemini AI 호출 최종 실패") or \
                               ai_processed_content.startswith("Gemini AI 호출에서 유효한 응답을 받지 못했습니다."):
                                final_content = f"본문 요약 실패 (AI 오류): {ai_processed_content}"
                                status_message_placeholder.error(f"AI 요약 실패: {final_content}")
                            else:
                                final_content = ai_service.clean_ai_response_text(ai_processed_content)

                            temp_collected_articles.append({
                                "제목": article["제목"],
                                "링크": article["링크"],
                                "날짜": article_date_str,
                                "내용": final_content
                            })
                            processed_links.add(article["링크"])
                            ai_processed_count += 1
                            ai_progress_bar.progress(ai_processed_count / total_ai_articles_to_process, text=f"AI가 트렌드 기사를 요약 중... ({ai_processed_count}/{total_ai_articles_to_process} 완료)")
                            time.sleep(0.1)

                        ai_progress_bar.empty()
                        st.session_state['final_collected_articles'] = temp_collected_articles

                        if st.session_state['final_collected_articles']:
                            status_message_placeholder.success(
                                f"총 {len(st.session_state['final_collected_articles'])}개의 트렌드 기사 요약을 완료했습니다. "
                                "AI 트렌드 요약 및 보험 상품 개발 인사이트 보고서는 아래 '데이터 다운로드' 섹션에서 다운로드할 수 있습니다."
                            )

                            # --- 4. AI가 트렌드 요약 및 보험 상품 개발 인사이트 도출 (분리된 호출) ---
                            status_message_placeholder.info("AI가 트렌드 요약 및 보험 상품 개발 인사이트를 도출 중 (분리된 호출)...")

                            articles_for_ai_insight_generation = st.session_state['final_collected_articles']

                            with st.spinner("AI가 뉴스 트렌드를 요약 중..."):
                                trend_summary = ai_service.get_overall_trend_summary(
                                    articles_for_ai_insight_generation,
                                    GEMINI_API_KEY
                                )
                                st.session_state['ai_trend_summary'] = ai_service.clean_ai_response_text(trend_summary)
                                if st.session_state['ai_trend_summary'].startswith("요약된 기사가 없어") or \
                                   st.session_state['ai_trend_summary'].startswith("Gemini AI 호출 최종 실패") or \
                                   st.session_state['ai_trend_summary'].startswith("Gemini AI 호출에서 유효한 응답을 받지 못했습니다."):
                                    status_message_placeholder.error(f"AI 트렌드 요약 실패: {st.session_state['ai_trend_summary']}")
                                else:
                                    st.session_state['ai_trend_summary_ok'] = True # 성공 플래그
                                    status_message_placeholder.success("AI 뉴스 트렌드 요약 완료!")
                                time.sleep(1)

                            with st.spinner("AI가 자동차 보험 산업 관련 정보를 분석 중..."):
                                insurance_info = ai_service.get_insurance_implications_from_ai(
                                    st.session_state['ai_trend_summary'],
                                    GEMINI_API_KEY
                                )
                                st.session_state['ai_insurance_info'] = ai_service.clean_ai_response_text(insurance_info)
                                if st.session_state['ai_insurance_info'].startswith("요약된 기사가 없어") or \
                                   st.session_state['ai_insurance_info'].startswith("Gemini AI 호출 최종 실패") or \
                                   st.session_state['ai_insurance_info'].startswith("Gemini AI 호출에서 유효한 응답을 받지 못했습니다.") or \
                                   st.session_state['ai_insurance_info'].startswith("트렌드 요약문이 없어"):
                                    status_message_placeholder.error(f"AI 자동차 보험 산업 관련 정보 분석 실패: {st.session_state['ai_insurance_info']}")
                                else:
                                    st.session_state['ai_insurance_info_ok'] = True # 성공 플래그
                                    status_message_placeholder.success("AI 자동차 보험 산업 관련 정보 분석 완료!")
                                time.sleep(1)

                            # --- 5. AI가 각 섹션별로 포맷팅 (부하 분산) ---
                            with st.spinner("AI가 뉴스 트렌드 요약 보고서를 포맷팅 중..."):
                                formatted_trend_summary = ai_service.format_text_with_markdown(
                                    st.session_state['ai_trend_summary'],
                                    GEMINI_API_KEY
                                )
                                st.session_state['formatted_trend_summary'] = formatted_trend_summary
                                if formatted_trend_summary.startswith("AI를 통한 보고서 포맷팅 실패"):
                                    status_message_placeholder.warning("AI 뉴스 트렌드 요약 포맷팅에 실패했습니다. 원본 텍스트가 사용됩니다.")
                                    st.session_state['formatted_trend_summary'] = st.session_state['ai_trend_summary']
                                else:
                                    status_message_placeholder.success("AI 뉴스 트렌드 요약 보고서 포맷팅 완료!")
                                time.sleep(1)

                            with st.spinner("AI가 자동차 보험 산업 관련 정보 보고서를 포맷팅 중..."):
                                formatted_insurance_info = ai_service.format_text_with_markdown(
                                    st.session_state['ai_insurance_info'],
                                    GEMINI_API_KEY
                                )
                                st.session_state['formatted_insurance_info'] = formatted_insurance_info
                                if formatted_insurance_info.startswith("AI를 통한 보고서 포맷팅 실패"):
                                    status_message_placeholder.warning("AI 자동차 보험 산업 관련 정보 포맷팅에 실패했습니다. 원본 텍스트가 사용됩니다.")
                                    st.session_state['formatted_insurance_info'] = st.session_state['ai_insurance_info']
                                else:
                                    st.session_state['formatted_insurance_info_ok'] = True # 성공 플래그
                                    status_message_placeholder.success("AI 자동차 보험 산업 관련 정보 분석 완료!")
                                time.sleep(1)

                            # --- 6. 최종 보고서 결합 (AI 포맷팅 + 직접 구성 부록) ---
                            final_prettified_report = ""
                            final_prettified_report += "# 뉴스 트렌드 분석 및 보험 상품 개발 인사이트\n\n"
                            final_prettified_report += "## 개요\n\n"
                            final_prettified_report += "이 보고서는 최근 뉴스 트렌드를 분석하고, 이를 바탕으로 자동차 보험 상품 개발에 필요한 주요 인사이트를 제공합니다.\n\n"

                            if st.session_state['formatted_trend_summary']:
                                final_prettified_report += "## 뉴스 트렌드 요약\n"
                                final_prettified_report += st.session_state['formatted_trend_summary'] + "\n\n"
                            else:
                                final_prettified_report += "## 뉴스 트렌드 요약 (생성 실패)\n"
                                final_prettified_report += st.session_state['ai_trend_summary'] + "\n\n"

                            if st.session_state['formatted_insurance_info']:
                                final_prettified_report += "## 자동차 보험 산업 관련 주요 사실 및 법적 책임\n"
                                final_prettified_report += st.session_state['formatted_insurance_info'] + "\n\n"
                            else:
                                final_prettified_report += "## 자동차 보험 산업 관련 주요 사실 및 법적 책임 (생성 실패)\
                                \n"
                                final_prettified_report += st.session_state['ai_insurance_info'] + "\n\n"

                            # --- 부록 섹션 추가 (AI 포맷팅 없이 직접 구성) ---
                            final_prettified_report += "---\n\n"
                            final_prettified_report += "## 부록\n\n"

                            final_prettified_report += "### 키워드 산출 근거\n"
                            if st.session_state['displayed_keywords']:
                                for kw_data in st.session_state['displayed_keywords']:
                                    surge_ratio_display = (f'''{kw_data.get('surge_ratio'):.2f}x''' if kw_data.get('surge_ratio') != float('inf') else '새로운 트렌드')
                                    final_prettified_report += (
                                        f"- **키워드**: {kw_data['keyword']}\n"
                                        f"  - 최근 언급량: {kw_data['recent_freq']}회\n"
                                        f"  - 이전 언급량: {kw_data['past_freq']}회\n"
                                        f"  - 증가율: {surge_ratio_display}\n\n"
                                    )
                            else:
                                final_prettified_report += "키워드 산출 근거 데이터가 없습니다.\n\n"

                            final_prettified_report += "### 반영된 기사 리스트\n"
                            if temp_collected_articles:
                                for i, article in enumerate(temp_collected_articles):
                                    final_prettified_report += (
                                        f"{i+1}. **제목**: {article['제목']}\n"
                                        f"   **날짜**: {article['날짜']}\n"
                                        f"   **링크**: {article['링크']}\n"
                                        f"   **요약 내용**: {article['내용'][:150]}...\n\n"
                                    )
                            else:
                                final_prettified_report += "반영된 기사 리스트가 없습니다.\n\n"

                            st.session_state['prettified_report_for_download'] = final_prettified_report


                        else:
                            status_message_placeholder.info("선별된 트렌드 키워드를 포함하는 기사가 없거나, AI 요약에 실패했습니다.")

                else:
                    status_message_placeholder.info("선택된 기간 내에 유의미한 트렌드 키워드가 없습니다.")

                st.session_state['submitted_flag'] = False
                st.session_state['analysis_completed'] = True
                database_manager.clear_intermediate_summaries() # 중간 요약 DB 초기화
                st.rerun()

            # --- 결과가 이미 세션 상태에 있는 경우 표시 ---
            # submitted_button이 False이고, trigger_analysis_after_preset_load가 False이며, analysis_completed가 True일 때만 결과 표시
            if not submitted_button and not st.session_state.get('trigger_analysis_after_preset_load', False) and \
               st.session_state.get('analysis_completed', False):
                if st.session_state['displayed_keywords']:
                    df_top_keywords = pd.DataFrame(st.session_state['displayed_keywords'])
                    df_top_keywords['surge_ratio'] = df_top_keywords['surge_ratio'].apply(
                        lambda x: f"{x:.2f}x" if x != float('inf') else "새로운 트렌드"
                    )
                    
                    # --- 표에 색상 추가 ---
                    # 키워드별 색상 매핑 (Streamlit 기본 테마를 따르면서 다른 색상 사용)
                    keyword_colors = [
                        '#E0F7FA', # Light Cyan (밝은 청록)
                        '#EDE7F6', # Lavender (연한 보라)
                        '#FFECB3'  # Amber A100 (연한 호박색)
                    ]
                    
                    def highlight_keywords_stable(row):
                        # 상위 3개 키워드에만 색상 적용
                        if row.name < len(keyword_colors):
                            return [f'background-color: {keyword_colors[row.name]}'] * len(row)
                        return [''] * len(row)

                    def highlight_header(s):
                        # 헤더 배경색 제거 (요청에 따라)
                        return ['font-weight: bold; color: black;'] * len(s)

                    # 스타일 적용: 헤더 스타일 먼저 적용 후 키워드별 행 스타일 적용
                    styled_df = df_top_keywords.style.apply(highlight_keywords_stable, axis=1).apply(highlight_header, axis=0, subset=pd.IndexSlice[:, df_top_keywords.columns])
                    
                    table_placeholder.dataframe(styled_df, use_container_width=True)
                    
                    # 차트 데이터 준비: Altair를 위해 데이터를 'long' 형식으로 변환
                    df_chart = df_top_keywords[['keyword', 'recent_freq', 'past_freq']].copy()
                    df_chart_melted = df_chart.melt('keyword', var_name='type', value_name='count')

                    # 'type' 컬럼의 값 변경 (범례에 표시될 이름)
                    df_chart_melted['type'] = df_chart_melted['type'].replace({
                        'recent_freq': '최근 트렌드 기간 언급량',
                        'past_freq': '과거 전체 기간 언급량'
                    })

                    chart = alt.Chart(df_chart_melted).mark_bar(size=15).encode(
                        # X축: 키워드 (주요 그룹)
                        x=alt.X('keyword:N', title='키워드', axis=alt.Axis(
                            labels=True, # 레이블 표시
                            labelAngle=0, # 축 레이블 가로로
                            titleFontWeight='normal', # 축 제목 가늘게
                            labelFontWeight='normal' # 축 레이블 가늘게
                        )),
                        # Y축: 언급량 (수치)
                        y=alt.Y('count:Q', title='언급량', axis=alt.Axis(
                            titleFontWeight='normal', # 축 제목 가늘게
                            labelFontWeight='normal' # 축 레이블 가늘게
                        )),
                        # 색상: 기간 (최근/과거)에 따라 다르게 표시
                        color=alt.Color('type:N', title='기간', scale=alt.Scale(range=['#ADD8E6', '#FFB6C1']), legend=alt.Legend(title="언급량 종류", orient="bottom")),
                        # X축 오프셋: 각 키워드 내에서 기간별 막대를 나란히 배치
                        xOffset='type:N',
                        tooltip=['keyword', 'type', 'count']
                    ).properties(
                        title='키워드 언급량 비교' # 차트 제목은 유지 (요청에 따라)
                    ).interactive()

                    chart_placeholder.altair_chart(chart, use_container_width=True)
                    st.markdown("---") # 차트 아래 구분선 추가

                    if st.session_state['final_collected_articles']:
                        status_message_placeholder.success(
                            f"총 {len(st.session_state['final_collected_articles'])}개의 트렌드 기사 요약을 완료했습니다. "
                            "AI 트렌드 요약 및 보험 상품 개발 인사이트 보고서는 아래 '데이터 다운로드' 섹션에서 다운로드할 수 있습니다."
                        )
                else:
                    st.info("선택된 기간 내에 유의미한 트렌드 키워드가 식별되지 않았습니다.")
                    chart_placeholder.empty() # 데이터가 없으면 차트도 비움
            # 초기 상태 또는 분석이 완료되지 않은 상태
            elif not submitted_button and not st.session_state.get('analysis_completed', False):
                empty_df = pd.DataFrame(columns=['keyword', 'recent_freq', 'past_freq', 'surge_ratio'])
                # --- 표에 색상 추가 (초기 빈 데이터프레임에도 적용) ---
                def highlight_header(s):
                    # 헤더 배경색 제거 (요청에 따라)
                    return ['font-weight: bold; color: black;'] * len(s)
                styled_empty_df = empty_df.style.apply(highlight_header, axis=0, subset=pd.IndexSlice[:, empty_df.columns])
                table_placeholder.dataframe(styled_empty_df, use_container_width=True) # st.table 대신 st.dataframe 사용
                status_message_placeholder.info("검색 조건을 입력하고 '뉴스 트렌드 분석 시작' 버튼을 눌러주세요!")
                chart_placeholder.empty() # 초기 상태에서는 차트도 비움


        # --- 데이터 다운로드 섹션 ---
        st.header("📥 데이터 다운로드")
        
        # --- 다운로드 섹션 레이아웃 변경 ---
        col_all_news_download, col_ai_summary_download = st.columns(2)

        txt_data_all_crawled = ""
        excel_data_all_crawled = None
        txt_data_ai_summaries = ""
        excel_data_ai_summaries = None
        txt_data_ai_insights = ""
        excel_data_ai_insights = None

        # all_db_articles가 비어있을 수도 있으므로, DataFrame 생성 전에 확인
        if all_db_articles:
            df_all_articles = pd.DataFrame(all_db_articles, columns=['제목', '링크', '날짜', '내용', '수집_시간'])
            df_all_articles['내용'] = df_all_articles['내용'].fillna('')

            txt_data_all_crawled = data_exporter.export_articles_to_txt(
                [dict(zip(df_all_articles.columns, row)) for row in df_all_articles.values],
                file_prefix="all_crawled_news"
            )

            excel_data_all_crawled = data_exporter.export_articles_to_excel(df_all_articles, sheet_name='All_Crawled_News')


        df_ai_summaries = pd.DataFrame(st.session_state['final_collected_articles'],
                                       columns=['제목', '링크', '날짜', '내용'])
        df_ai_summaries['내용'] = df_ai_summaries['내용'].fillna('')

        txt_data_ai_summaries = data_exporter.export_articles_to_txt(
            [dict(zip(df_ai_summaries.columns, row)) for row in df_ai_summaries.values],
            file_prefix="ai_summaries"
        )

        if not df_ai_summaries.empty:
            excel_data_ai_summaries = data_exporter.export_articles_to_excel(df_ai_summaries, sheet_name='AI_Summaries')

        if st.session_state['prettified_report_for_download']:
            txt_data_ai_insights = st.session_state['prettified_report_for_download']
        else:
            txt_data_ai_insights = "AI 트렌드 요약 및 보험 상품 개발 인사이트가 없습니다."


        if st.session_state['prettified_report_for_download']:
            excel_data_ai_insights = data_exporter.export_ai_report_to_excel(
                st.session_state['prettified_report_for_download'],
                sheet_name='AI_Insights_Report'
            )
        else:
            excel_data_ai_insights = None


        with col_all_news_download:
            st.markdown("### 📊 수집된 전체 뉴스 데이터")
            # TXT 다운로드 버튼의 너비를 위해 컬럼 비율 조정 (0.2, 0.8)
            col_all_data_txt, col_all_data_excel = st.columns([0.2, 0.8])
            with col_all_data_txt:
                st.download_button(
                    label="📄 TXT 다운로드",
                    data=txt_data_all_crawled,
                    file_name=data_exporter.generate_filename("all_crawled_news", "txt"),
                    mime="text/plain",
                    help="데이터베이스에 저장된 모든 뉴스를 텍스트 파일로 다운로드합니다."
                )
            with col_all_data_excel:
                if excel_data_all_crawled:
                    st.download_button(
                        label="📊 엑셀 다운로드",
                        data=excel_data_all_crawled.getvalue(),
                        file_name=data_exporter.generate_filename("all_crawled_news", "xlsx"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="데이터베이스에 저장된 모든 뉴스를 엑셀 파일(.xlsx)로 다운로드합니다. (한글 깨짐 없음)"
                    )
                else:
                    st.info("엑셀 다운로드 데이터가 없습니다.")

        with col_ai_summary_download:
            if not df_ai_summaries.empty:
                st.markdown("### 📝 AI 요약 기사")
                # TXT 다운로드 버튼의 너비를 위해 컬럼 비율 조정 (0.2, 0.8)
                col_ai_txt, col_ai_excel = st.columns([0.2, 0.8])
                with col_ai_txt:
                    st.download_button(
                        label="📄 AI 요약 TXT 다운로드",
                        data=txt_data_ai_summaries,
                        file_name=data_exporter.generate_filename("ai_summaries", "txt"),
                        mime="text/plain",
                        help="AI가 요약한 트렌드 기사 내용을 텍스트 파일로 다운로드합니다."
                    )
                with col_ai_excel:
                    if excel_data_ai_summaries:
                        st.download_button(
                            label="📊 AI 요약 엑셀 다운로드",
                            data=excel_data_ai_summaries.getvalue(),
                            file_name=data_exporter.generate_filename("ai_summaries", "xlsx"),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            help="AI가 요약한 트렌드 기사 내용을 엑셀 파일(.xlsx)로 다운로드합니다."
                        )
                    else:
                        st.info("AI 요약 엑셀 다운로드 데이터가 없습니다.")
            else:
                st.markdown("### 📝 AI 요약 기사") # 제목은 항상 표시
                st.info("AI 요약된 트렌드 기사가 없습니다. 먼저 분석을 실행하여 요약된 기사를 생성하세요.")


        if st.session_state['prettified_report_for_download']:
            st.markdown("### 💡 AI 트렌드 요약 및 보험 상품 개발 인사이트")
            col_ai_insights_txt, col_ai_insights_excel, col_ai_insights_email = st.columns([0.1, 0.4, 0.5])
            with col_ai_insights_txt:
                st.download_button(
                    label="📄 TXT 다운로드",
                    data=txt_data_ai_insights,
                    file_name=data_exporter.generate_filename("ai_insights_report", "txt"),
                    mime="text/plain",
                    help="AI가 도출한 트렌드 요약 및 보험 상품 개발 인사이트 보고서를 텍스트 파일로 다운로드합니다."
                )
            with col_ai_insights_excel:
                if excel_data_ai_insights:
                    st.download_button(
                        label="📊 엑셀 다운로드",
                        data=excel_data_ai_insights.getvalue(),
                        file_name=data_exporter.generate_filename("ai_insights_report", "xlsx"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="AI가 도출한 트렌드 요약 및 보험 상품 개발 인사이트 보고서를 엑셀 파일로 다운로드합니다."
                    )
                else:
                    st.info("AI 인사이트 엑셀 다운로드 데이터가 없습니다.")
            with col_ai_insights_email:
                st.text_input(
                    "수신자 이메일 (콤마로 구분)",
                    value=st.session_state['recipient_emails_input'],
                    key="email_recipients_input",
                    help="보고서를 받을 이메일 주소를 콤마(,)로 구분하여 입력하세요."
                )
                # 이메일 전송 버튼 (보고서만) - 특약 포함 전송은 자동화 페이지에서
                if st.button("📧 보고서 이메일 전송", help="생성된 보고서를 이메일로 전송합니다."):
                    recipient_emails_str = st.session_state['email_recipients_input']
                    recipient_emails_list = [e.strip() for e in recipient_emails_str.split(',') if e.strip()]

                    if not recipient_emails_list:
                        st.session_state['email_status_message'] = "🚨 수신자 이메일 주소를 입력해주세요."
                        st.session_state['email_status_type'] = "error"
                        st.rerun()
                    elif not email_config_ok:
                        st.session_state['email_status_message'] = "🚨 이메일 설정 정보가 올바르지 않아 이메일을 전송할 수 없습니다."
                        st.session_state['email_status_type'] = "error"
                        st.rerun()
                    else:
                        with st.spinner("이메일 전송 중..."):
                            email_subject = f"뉴스 트렌드 분석 보고서 - {datetime.now().strftime('%Y%m%d')}"
                            email_body = st.session_state['prettified_report_for_download']

                            attachments = []
                            if excel_data_ai_insights:
                                attachments.append({
                                    "data": excel_data_ai_insights.getvalue(),
                                    "filename": data_exporter.generate_filename("ai_insights_report", "xlsx"),
                                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                })
                            
                            # 이 페이지에서는 특약 첨부는 하지 않습니다.
                            # 특약 첨부는 report_automation_page에서 담당합니다.

                            success = email_sender.send_email_with_multiple_attachments( # 함수명 변경
                                sender_email=SENDER_EMAIL,
                                sender_password=SENDER_PASSWORD,
                                receiver_emails=recipient_emails_list, # 리스트 형태로 전달
                                smtp_server=SMTP_SERVER,
                                smtp_port=SMTP_PORT,
                                subject=email_subject,
                                body=email_body,
                                attachments=attachments, # 여러 첨부파일 전달
                                report_format="markdown"
                            )
                            if success:
                                st.session_state['email_status_message'] = "이메일이 성공적으로 전송되었습니다!"
                                st.session_state['email_status_type'] = "success"
                            else:
                                st.session_state['email_status_message'] = "이메일 전송에 실패했습니다. 설정 및 로그를 확인해주세요."
                                st.session_state['email_status_type'] = "error"
                            st.rerun()

                # 이메일 전송 상태 메시지 표시
                if st.session_state['email_status_message']:
                    if st.session_state['email_status_type'] == "success":
                        st.success(st.session_state['email_status_message'])
                    elif st.session_state['email_status_type'] == "error":
                        st.error(st.session_state['email_status_message']) # 메시지 출력으로 변경
                    st.session_state['email_status_message'] = ""
                    st.session_state['email_status_type'] = ""


        else:
            st.info("AI 트렌드 요약 및 보험 상품 개발 인사이트가 없습니다. 분석을 실행하여 생성하세요.")

        st.markdown("---")
        col_db_info, col_db_clear = st.columns([2, 1])
        with col_db_info:
            st.info(f"현재 데이터베이스에 총 {len(all_db_articles)}개의 기사가 저장되어 있습니다.")
            if st.session_state['db_status_message']:
                if st.session_state['db_status_type'] == "success":
                    st.success(st.session_state['db_status_message'])
                elif st.session_state['db_status_type'] == "error":
                    st.error(st.session_state['db_status_message']) # 메시지 출력으로 변경
                st.session_state['db_status_message'] = ""
                st.session_state['db_status_type'] = ""
            st.markdown("💡 **CSV 파일이 엑셀에서 깨질 경우:** 엑셀에서 '데이터' 탭 -> '텍스트/CSV 가져오기'를 클릭한 후, '원본 파일' 인코딩을 'UTF-8'로 선택하여 가져오세요.")
        with col_db_clear:
            if st.button("데이터베이스 초기화", help="데이터베이스의 모든 저장된 뉴스를 삭제합니다.", type="secondary"):
                database_manager.clear_db_content()
                st.session_state['trending_keywords_data'] = []
                st.session_state['displayed_keywords'] = []
                st.session_state['final_collected_articles'] = []
                st.session_state['ai_insights_summary'] = ""
                st.session_state['ai_trend_summary'] = ""
                st.session_state['ai_insurance_info'] = ""
                st.session_state['submitted_flag'] = False
                st.session_state['analysis_completed'] = False
                st.session_state['prettified_report_for_download'] = ""
                st.session_state['formatted_trend_summary'] = ""
                st.session_state['formatted_insurance_info'] = ""
                st.session_state['email_status_message'] = ""
                st.session_state['email_status_type'] = ""
                st.session_state['search_profiles'] = database_manager.get_search_profiles() # 프로필 목록 새로고침
                st.session_state['scheduled_task'] = database_manager.get_scheduled_task() # 예약 정보 새로고침
                database_manager.save_generated_endorsement("") # 데이터베이스 특약도 초기화 (새로 추가)
                database_manager.save_document_text("") # 문서 텍스트도 초기화
                st.rerun()
