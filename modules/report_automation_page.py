# modules/report_automation_page.py

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

# --- 모듈 임포트 (경로 조정) ---
from modules import ai_service
from modules import database_manager
from modules import news_crawler
from modules import trend_analyzer
from modules import data_exporter
from modules import email_sender

# KST와 UTC의 시차 (한국은 UTC+9)
KST_OFFSET_HOURS = 9

def report_automation_page():
    """
    보고서 자동 전송 및 예약 기능을 제공하는 페이지입니다.
    """
    # --- 환경 변수 로드 및 이메일 설정 정보 로드를 함수 시작점으로 이동 ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Potens 대신 Gemini API 키를 로드

    if not GEMINI_API_KEY:
        st.error("🚨 오류: .env 파일에 'GEMINI_API_KEY'가 설정되지 않았습니다. Gemini AI 기능을 사용할 수 없습니다.")
        return # API 키 없으면 페이지 기능 비활성화

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

    # 데이터베이스 초기화 (필요시) 및 기사 로드도 함수 시작점으로 이동
    database_manager.init_db()
    all_db_articles = database_manager.get_all_articles()


    # --- Streamlit Session State 초기화 (이 페이지에서 필요한 상태) ---
    # search_profiles는 항상 최신 상태로 DB에서 가져오도록 변경
    st.session_state['search_profiles'] = database_manager.get_search_profiles()
    
    if 'scheduled_task' not in st.session_state:
        st.session_state['scheduled_task'] = database_manager.get_scheduled_task()
    if 'auto_refresh_on' not in st.session_state:
        st.session_state['auto_refresh_on'] = False
    if 'scheduled_task_running' not in st.session_state:
        st.session_state['scheduled_task_running'] = False
    if 'automation_email_status_message' not in st.session_state: # 자동 전송 결과 메시지
        st.session_state['automation_email_status_message'] = ""
    if 'automation_email_status_type' not in st.session_state:
        st.session_state['automation_email_status_type'] = ""
    
    if 'manual_email_recipient_input' not in st.session_state:
        st.session_state['manual_email_recipient_input'] = ""
    if 'manual_email_status_message' not in st.session_state:
        st.session_state['manual_email_status_message'] = ""
    if 'manual_email_status_type' not in st.session_state:
        st.session_state['manual_email_status_type'] = ""
    if 'db_status_message' not in st.session_state:
        st.session_state['db_status_message'] = ""
    if 'db_status_type' not in st.session_state:
        st.session_state['db_status_type'] = ""
    if 'auto_refresh_counter' not in st.session_state:
        st.session_state['auto_refresh_counter'] = 0


    # --- 자동 보고서 전송 스케줄러 (앱이 켜져 있을 때만 작동) ---
    current_dt_utc = datetime.now() # 서버 시간은 UTC
    current_time_str_utc = current_dt_utc.strftime("%H:%M") # HH:MM (UTC)
    current_date_str = current_dt_utc.strftime("%Y-%m-%d") #YYYY-MM-DD
    current_weekday_korean = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"][current_dt_utc.weekday()] # 현재 요일 (0=월, 6=일)

    scheduled_task = st.session_state.get('scheduled_task', None) # None으로 초기화될 수 있도록 변경
    
    # 예약된 작업이 실행 중이지 않을 때만 스케줄러를 체크
    if not st.session_state['scheduled_task_running'] and scheduled_task:
        # DB에 저장된 시간은 UTC 기준
        task_time_str_utc = scheduled_task['schedule_time'] # "HH:MM" (UTC)
        task_day = scheduled_task['schedule_day'] # "매일", "월요일" 등
        last_run_date = scheduled_task['last_run_date']
        
        # 디버깅을 위한 출력 (사이드바에 표시 및 콘솔 출력)
        print(f"DEBUG: Scheduler check - Current time (UTC)={current_time_str_utc}, Task time (UTC)={task_time_str_utc}, Task day={task_day}, Current day={current_weekday_korean}, Last run={last_run_date}, Current date={current_date_str}")
        
        # --- 디버그 로그 추가 시작 ---
        st.sidebar.write(f"DEBUG: 현재 시간 (UTC): {current_dt_utc.strftime('%H:%M:%S')}")
        st.sidebar.write(f"DEBUG: 예약 시간 (UTC): {task_time_str_utc}")
        st.sidebar.write(f"DEBUG: 예약 요일: {task_day}, 현재 요일: {current_weekday_korean}")
        st.sidebar.write(f"DEBUG: 마지막 실행일: {last_run_date}, 오늘 날짜: {current_date_str}")
        st.sidebar.write(f"DEBUG: scheduled_task_running: {st.session_state['scheduled_task_running']}")
        # --- 디버그 로그 추가 끝 ---

        # 예약 시간 5분 전부터 예약 시간 1분 후까지의 범위에 현재 시간이 포함되는지 확인 (모두 UTC 기준)
        try:
            task_hour_utc, task_minute_utc = map(int, task_time_str_utc.split(':'))
            
            scheduled_dt_today_utc = current_dt_utc.replace(hour=task_hour_utc, minute=task_minute_utc, second=0, microsecond=0)
            trigger_start_dt_utc = scheduled_dt_today_utc - timedelta(minutes=5)
            trigger_end_dt_utc = scheduled_dt_today_utc + timedelta(minutes=1) # 예약 시간 1분 후까지 여유를 둠

            # 요일 조건 확인
            day_condition_met = False
            if task_day == "매일":
                day_condition_met = True
            elif task_day == current_weekday_korean:
                day_condition_met = True
            
            # --- 디버그 로그 추가 시작 ---
            st.sidebar.write(f"DEBUG: 트리거 시작 (UTC): {trigger_start_dt_utc.strftime('%H:%M:%S')}")
            st.sidebar.write(f"DEBUG: 트리거 종료 (UTC): {trigger_end_dt_utc.strftime('%H:%M:%S')}")
            st.sidebar.write(f"DEBUG: 시간 조건 (현재 UTC >= 시작 UTC): {current_dt_utc >= trigger_start_dt_utc}")
            st.sidebar.write(f"DEBUG: 시간 조건 (현재 UTC < 종료 UTC): {current_dt_utc < trigger_end_dt_utc}")
            st.sidebar.write(f"DEBUG: 날짜 조건 (마지막 실행일 != 오늘): {last_run_date != current_date_str}")
            st.sidebar.write(f"DEBUG: 요일 조건 충족: {day_condition_met}")
            # --- 디버그 로그 추가 끝 ---

            if current_dt_utc >= trigger_start_dt_utc and \
               current_dt_utc < trigger_end_dt_utc and \
               last_run_date != current_date_str and \
               day_condition_met:
                st.info(f"⏰ 예약된 보고서 전송 시간입니다! (설정 시간: {task_time_str_utc} UTC, {task_day})") # UTC 시간 명시
                print(f"DEBUG: Triggering scheduled task for {task_time_str_utc} UTC on {current_date_str} ({task_day})")
                
                # 예약 작업 시작 플래그 설정
                st.session_state['scheduled_task_running'] = True
                st.rerun() # 플래그 업데이트 후 즉시 새로고침하여 UI에 반영하고, 스케줄러 재진입 방지

        except Exception as e:
            st.error(f"🚨 예약된 작업 시간 파싱 중 오류 발생: {e}")
            print(f"ERROR: Scheduled task time parsing failed: {e}")
    elif st.session_state['scheduled_task_running']:
        st.warning("⚠️ 예약된 보고서 전송 작업이 현재 실행 중입니다. 잠시 기다려주세요...")
        print("DEBUG: Scheduled task is already running. Skipping scheduler check.")
        # 작업이 실행 중일 때는 스케줄러 체크를 건너뛰고, 아래에서 실제 작업을 수행합니다.

    # --- 예약된 작업 실제 실행 로직 (플래그가 True일 때만 실행) ---
    if st.session_state['scheduled_task_running']:
        scheduled_task = st.session_state['scheduled_task'] # 최신 예약 정보 다시 로드
        if scheduled_task:
            profile_id_to_run = scheduled_task['profile_id']
            # search_profiles를 항상 최신 DB 정보로 사용
            profiles_dict = {p['id']: p for p in database_manager.get_search_profiles()}
            profile_to_run = profiles_dict.get(profile_id_to_run)

            if profile_to_run:
                try:
                    with st.spinner(f"예약된 작업 실행 중: '{profile_to_run['profile_name']}' 보고서 생성 및 전송..."):
                        # 1. 뉴스 메타데이터 수집
                        all_collected_news_metadata = []
                        today_date_for_crawl = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                        search_start_date = today_date_for_crawl - timedelta(days=profile_to_run['total_search_days'] - 1)

                        for i in range(profile_to_run['total_search_days']):
                            current_search_date = search_start_date + timedelta(days=i)
                            daily_articles = news_crawler.crawl_naver_news_metadata(
                                profile_to_run['keyword'],
                                current_search_date,
                                profile_to_run['max_naver_search_pages_per_day']
                            )
                            for article in daily_articles:
                                article_data_for_db = {
                                    "제목": article["제목"],
                                    "링크": article["링크"],
                                    "날짜": article["날짜"].strftime('%Y-%m-%d'),
                                    "내용": article["내용"] # 오타 수정: '내andung' -> '내용'
                                }
                                database_manager.insert_article(article_data_for_db)
                                all_collected_news_metadata.append(article)
                        
                        # 2. 키워드 트렌드 분석
                        trending_keywords_data = trend_analyzer.analyze_keyword_trends(
                            all_collected_news_metadata,
                            recent_days_period=profile_to_run['recent_trend_days'],
                            total_days_period=profile_to_run['total_search_days']
                        )

                        relevant_keywords_from_ai_raw = ai_service.get_relevant_keywords(
                            trending_keywords_data, "차량보험사의 보험개발자", GEMINI_API_KEY
                        )
                        filtered_trending_keywords = [
                            kw_data for kw_data in trending_keywords_data
                            if kw_data['keyword'] in relevant_keywords_from_ai_raw
                        ]
                        filtered_trending_keywords = sorted(filtered_trending_keywords, key=lambda x: x['recent_freq'], reverse=True)
                        top_3_relevant_keywords = filtered_trending_keywords[:3]

                        # 3. 트렌드 기사 본문 요약
                        recent_trending_articles_candidates = [
                            article for article in all_collected_news_metadata
                            if article.get("날짜") and today_date_for_crawl - timedelta(days=profile_to_run['recent_trend_days']) <= article["날짜"]
                        ]

                        # 오타 수정: '내andung' -> '내용'
                        articles_for_ai_summary = []
                        processed_links = set()
                        for article in recent_trending_articles_candidates:
                            text_for_trend_check = article["제목"] + " " + article.get("내용", "")
                            article_keywords_for_trend = trend_analyzer.extract_keywords_from_text(text_for_trend_check)
                            if any(trend_kw['keyword'] in article_keywords_for_trend for trend_kw in top_3_relevant_keywords):
                                articles_for_ai_summary.append(article)

                        temp_collected_articles = []
                        for article in articles_for_ai_summary:
                            if article["링크"] in processed_links:
                                continue
                            article_date_str = article["날짜"].strftime('%Y-%m-%d')
                            ai_processed_content = ai_service.get_article_summary(
                                article["제목"], article["링크"], article_date_str, article["내용"], GEMINI_API_KEY
                            )
                            final_content = ai_service.clean_ai_response_text(ai_processed_content)
                            temp_collected_articles.append({
                                "제목": article["제목"], "링크": article["링크"], "날짜": article_date_str, "내용": final_content
                            })
                            processed_links.add(article["링크"])

                        # 4. AI가 트렌드 요약 및 보험 상품 개발 인사이트 도출
                        articles_for_ai_insight_generation = temp_collected_articles
                        trend_summary = ai_service.get_overall_trend_summary(articles_for_ai_insight_generation, GEMINI_API_KEY)
                        insurance_info = ai_service.get_insurance_implications_from_ai(trend_summary, GEMINI_API_KEY)

                        # 5. AI가 각 섹션별로 포맷팅
                        formatted_trend_summary = ai_service.format_text_with_markdown(trend_summary, GEMINI_API_KEY)
                        formatted_insurance_info = ai_service.format_text_with_markdown(insurance_info, GEMINI_API_KEY)

                        # 6. 최종 보고서 결합
                        final_prettified_report = ""
                        final_prettified_report += "# 뉴스 트렌드 분석 및 보험 상품 개발 인사이트\n\n"
                        final_prettified_report += "## 개요\n\n"
                        final_prettified_report += "이 보고서는 최근 뉴스 트렌드를 분석하고, 이를 바탕으로 자동차 보험 상품 개발에 필요한 주요 인사이트를 제공합니다.\n\n"
                        final_prettified_report += "## 뉴스 트렌드 요약\n" + (formatted_trend_summary if formatted_trend_summary else trend_summary) + "\n\n"
                        final_prettified_report += "## 자동차 보험 산업 관련 주요 사실 및 법적 책임\n" + (formatted_insurance_info if formatted_insurance_info else insurance_info) + "\n\n"
                        final_prettified_report += "---\n\n## 부록\n\n### 키워드 산출 근거\n"
                        if top_3_relevant_keywords:
                            for kw_data in top_3_relevant_keywords:
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
                                    f"   **날짜**: {article['날짜']}\n" # '날' 대신 '날짜' 사용
                                    f"   **링크**: {article['링크']}\n"
                                    f"   **요약 내용**: {article['내용'][:150]}...\n\n"
                                )
                        else:
                            final_prettified_report += "반영된 기사 리스트가 없습니다.\n\n"

                        # 7. 엑셀 보고서 생성 (첨부파일용)
                        excel_data_for_attachment = None
                        if final_prettified_report:
                            excel_data_for_attachment = data_exporter.export_ai_report_to_excel(
                                final_prettified_report, sheet_name='AI_Insights_Report'
                            )

                        # --- 8. 특약 동적 생성 로직 (수정된 부분: 보고서 내용을 기반으로 생성) ---
                        endorsement_text_for_attachment = None
                        endorsement_filename = None
                        
                        # 새로 생성된 보고서 내용을 특약 생성의 기반으로 사용
                        # all_text_from_db = database_manager.get_latest_document_text() # 이 부분은 이제 사용하지 않음
                        
                        if final_prettified_report: # 새로 생성된 보고서 내용이 있을 경우에만 특약 생성 시도
                            st.info("⏳ 새로 생성된 보고서 내용을 기반으로 특약을 동적으로 생성 중...")
                            # 특약 구성 항목 정의 (document_analysis_page.py에서 가져옴)
                            sections_for_endorsement = {
                                "1. 특약의 명칭": "자동차 보험 표준약관을 참고하여 특약의 **명칭**을 작성해줘.",
                                "2. 특약의 목적": "이 특약의 **목적**을 설명해줘.",
                                "3. 보장 범위": "**보장 범위**에 대해 상세히 작성해줘.",
                                "4. 보험금 지급 조건": "**보험금 지급 조건**을 구체적으로 작성해줘.",
                                "5. 보험료 산정 방식": "**보험료 산정 방식**을 설명해줘.",
                                "6. 면책 사항": "**면책 사항**에 해당하는 내용을 작성해줘.",
                                "7. 특약의 적용 기간": "**적용 기간**을 명시해줘.",
                                "8. 기타 특별 조건": "**기타 특별 조건**이 있다면 제안해줘.",
                                "9. 운전가능자 제한": "**운전자 연령과 범위**에 따른 특별 약관을 제안해줘.",
                                "10. 보험료 할인": "**보험료 할인**에 해당하는 특별 약관을 작성해줘.",
                                "11. 보장 확대": "**법률비용 및 다른 자동차 운전**에 해당하는 특별 약관을 작성해줘"
                            }
                            
                            generated_endorsement_sections = {}
                            full_endorsement_text = ""

                            for title, question in sections_for_endorsement.items():
                                prompt_endorsement = f"""
너는 자동차 보험을 설계하고 있는 보험사 직원이야.
다음 조건에 따라 자동차 보험 특약의 '{title}'을 3~5줄 정도로 작성해줘.

[기획 목적]
- 이 특약은 보험 상품 기획 초기 단계에서 트렌드 조사 및 방향성 도출에 도움 되는 목적으로 작성돼야 해.
- 새로운 기술(예: 블랙박스, 자율주행 등)이나 최근 사회적 이슈(예: 고령 운전자 증가 등)를 반영해도 좋아.
- 표준약관 표현 방식을 따라줘.

[표준약관 내용]
{final_prettified_report} # 새로 생성된 보고서 내용을 특약 생성의 기반으로 사용

[질문]
{question}

[답변]
"""
                                response_dict_endorsement = ai_service.retry_ai_call(prompt_endorsement, GEMINI_API_KEY)
                                answer_endorsement = ai_service.clean_ai_response_text(response_dict_endorsement.get("text", response_dict_endorsement.get("error", "AI 응답 실패.")))
                                generated_endorsement_sections[title] = answer_endorsement
                                full_endorsement_text += f"#### {title}\n{answer_endorsement.strip()}\n\n"
                            
                            endorsement_text_for_attachment = full_endorsement_text
                            database_manager.save_generated_endorsement(endorsement_text_for_attachment) # 동적 생성 후 DB에 저장
                            endorsement_filename = data_exporter.generate_filename("생성된_보험_특약", "txt")
                            st.success("✅ 예약된 특약 동적 생성 완료!")
                        else:
                            st.warning("⚠️ 새로 생성된 보고서 내용이 없어 특약 생성을 건너뜁니다. 보고서 생성에 문제가 없는지 확인해주세요.")
                            # 보고서가 생성되지 않았다면 특약도 생성할 수 없으므로, 기존 특약 사용 로직은 제거
                            endorsement_text_for_attachment = None # 특약 내용 없음을 명확히
                            endorsement_filename = None

                        # --- 9. 이메일 전송 ---
                        recipient_emails_list = [e.strip() for e in scheduled_task['recipient_emails'].split(',') if e.strip()]
                        
                        report_send_success = False
                        endorsement_send_success = False

                        # 9-1. 보고서 이메일 전송
                        if recipient_emails_list:
                            email_subject_report = f"예약된 뉴스 트렌드 분석 보고서 - {datetime.now().strftime('%Y%m%d')}"
                            report_body_for_email = final_prettified_report # 본문은 보고서 내용으로 유지

                            report_attachments = []
                            if excel_data_for_attachment:
                                report_attachments.append({
                                    "data": excel_data_for_attachment.getvalue(),
                                    "filename": data_exporter.generate_filename("ai_insights_report", "xlsx"),
                                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                })
                            
                            if report_attachments: # 첨부할 보고서 내용이 있을 경우에만 전송 시도
                                report_send_success = email_sender.send_email_with_multiple_attachments(
                                    sender_email=SENDER_EMAIL,
                                    sender_password=SENDER_PASSWORD,
                                    receiver_emails=recipient_emails_list,
                                    smtp_server=SMTP_SERVER,
                                    smtp_port=SMTP_PORT,
                                    subject=email_subject_report,
                                    body=report_body_for_email,
                                    attachments=report_attachments,
                                    report_format="markdown"
                                )
                                if report_send_success:
                                    st.toast("✅ 예약된 보고서 이메일 전송 성공!", icon="📧")
                                    print("DEBUG: Scheduled report email sent successfully.")
                                else:
                                    st.error("🚨 예약된 보고서 이메일 전송 실패. 로그를 확인해주세요.")
                                    print("ERROR: Scheduled report email failed.")
                            else:
                                st.warning("⚠️ 예약된 보고서 내용이 없어 보고서 이메일 전송을 건너뜁니다.")
                                print("WARNING: No report content to send for scheduled task.")
                        else:
                            st.warning("⚠️ 예약된 작업에 유효한 수신자 이메일이 없어 보고서 이메일 전송을 건너뜁니다.")
                            print("WARNING: No valid recipients for scheduled report email.")

                        # 9-2. 특약 이메일 전송
                        if recipient_emails_list:
                            email_subject_endorsement = f"예약된 보험 특약 - {datetime.now().strftime('%Y%m%d')}"
                            
                            endorsement_attachments = []
                            if endorsement_text_for_attachment: # 특약 내용이 있을 경우에만 첨부
                                endorsement_attachments.append({
                                    "data": endorsement_text_for_attachment.encode('utf-8'),
                                    "filename": endorsement_filename,
                                    "mime_type": "text/plain"
                                })

                            if endorsement_attachments: # 첨부할 특약 내용이 있을 경우에만 전송 시도
                                endorsement_send_success = email_sender.send_email_with_multiple_attachments(
                                    sender_email=SENDER_EMAIL,
                                    sender_password=SENDER_PASSWORD,
                                    receiver_emails=recipient_emails_list,
                                    smtp_server=SMTP_SERVER,
                                    smtp_port=SMTP_PORT,
                                    subject=email_subject_endorsement,
                                    body="요청하신 보험 특약 내용입니다. 첨부 파일을 확인해주세요.",
                                    attachments=endorsement_attachments,
                                    report_format="plain"
                                )
                                if endorsement_send_success:
                                    st.toast("✅ 예약된 특약 이메일 전송 성공!", icon="📧")
                                    print("DEBUG: Scheduled endorsement email sent successfully.")
                                else:
                                    st.error("🚨 예약된 특약 이메일 전송 실패. 로그를 확인해주세요.")
                                    print("ERROR: Scheduled endorsement email failed.")
                            else:
                                st.warning("⚠️ 예약된 특약 내용이 없어 특약 이메일 전송을 건너뜁니다.")
                                print("WARNING: No endorsement content to send for scheduled task.")
                        else:
                            st.warning("⚠️ 예약된 작업에 유효한 수신자 이메일이 없어 특약 이메일 전송을 건너뜁니다.")
                            print("WARNING: No valid recipients for scheduled endorsement email.")

                        # 최종 결과 메시지 및 last_run_date 업데이트
                        if report_send_success and endorsement_send_success:
                            st.session_state['automation_email_status_message'] = "예약된 보고서와 특약이 모두 성공적으로 전송되었습니다!"
                            st.session_state['automation_email_status_type'] = "success"
                        elif report_send_success:
                            st.session_state['automation_email_status_message'] = "예약된 보고서는 전송되었으나, 특약 전송에 문제가 있었습니다."
                            st.session_state['automation_email_status_type'] = "warning"
                        elif endorsement_send_success:
                            st.session_state['automation_email_status_message'] = "예약된 특약은 전송되었으나, 보고서 전송에 문제가 있었습니다."
                            st.session_state['automation_email_status_type'] = "warning"
                        else:
                            st.session_state['automation_email_status_message'] = "예약된 보고서와 특약 전송이 모두 실패했습니다."
                            st.session_state['automation_email_status_type'] = "error"
                        
                        # 어떤 이메일이라도 전송 시도가 있었다면 last_run_date 업데이트
                        if report_send_success or endorsement_send_success:
                             database_manager.update_scheduled_task_last_run_date(scheduled_task['id'], current_date_str)
                             st.session_state['scheduled_task']['last_run_date'] = current_date_str # 세션 상태도 업데이트

                except Exception as e:
                    st.error(f"🚨 예약된 작업 실행 중 오류 발생: {e}")
                    print(f"ERROR: Scheduled task execution failed: {e}")
                    st.session_state['automation_email_status_message'] = f"예약된 작업 실행 중 오류 발생: {e}"
                    st.session_state['automation_email_status_type'] = "error"
                finally:
                    # 작업 완료 후 플래그 초기화 (성공/실패 여부와 관계없이)
                    st.session_state['scheduled_task_running'] = False
                    st.rerun() # 플래그 초기화 후 UI 업데이트를 위해 새로고침
            else:
                st.error("🚨 예약된 작업에 해당하는 검색 프리셋을 찾을 수 없습니다. 예약을 다시 설정해주세요.")
                st.session_state['scheduled_task_running'] = False # 프로필 없으면 작업 종료
                st.session_state['automation_email_status_message'] = "예약된 프리셋을 찾을 수 없습니다."
                st.session_state['automation_email_status_type'] = "error"
                st.rerun()
        else: # scheduled_task가 None이거나 더 이상 유효하지 않을 경우
            st.session_state['scheduled_task_running'] = False # 작업 중 아님으로 설정
    else:
        # 예약된 작업이 없거나, 예약 시간이 아니거나, 이미 오늘 실행되었을 때의 디버깅 메시지
        task_time_str_utc = scheduled_task['schedule_time'] if scheduled_task else 'N/A'
        last_run_date = scheduled_task['last_run_date'] if scheduled_task else 'N/A'
        print(f"DEBUG: Scheduler: Not time yet or no task scheduled or already run today. Current time: {current_time_str_utc}, Task time={task_time_str_utc}, Last run date={last_run_date}, Current date={current_date_str}")

    # --- 페이지 UI 시작 ---
    # 페이지 전체를 중앙에 배치하기 위한 최상위 컬럼
    col_page_left_spacer, col_page_main_content, col_page_right_spacer = st.columns([0.1, 0.8, 0.1])

    with col_page_main_content:
        st.title("⏰ 보고서 자동 전송 및 예약")
        st.markdown("원하는 검색 설정에 따라 뉴스 트렌드 보고서를 자동으로 생성하고 지정된 이메일로 전송합니다.")

        # --- 메인으로 돌아가기 버튼, 특약 생성 버튼, 뉴스 트렌드 분석기 버튼을 나란히 배치 ---
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
            if st.button("📈 뉴스 트렌드 분석기"):
                st.session_state.page = "trend"
                st.rerun()

        st.markdown("---")

        # --- 섹션 2 & 3: 예약 설정과 수동 전송을 나란히 배치 ---
        col_schedule_input_main, col_manual_send_main = st.columns(2)

        with col_schedule_input_main:
            st.subheader("⏰ 보고서 자동 전송 예약")
            st.markdown("원하는 검색 프리셋과 시간을 설정하여 보고서를 매일 자동으로 수신자에게 전송합니다. (앱이 켜져 있을 때만 작동)")

            st.markdown("#### 예약 설정")
            # search_profiles를 항상 최신 DB 정보로 가져오도록 변경
            available_profiles = database_manager.get_search_profiles()
            profile_options = {p['profile_name']: p['id'] for p in available_profiles}
            profile_names_for_schedule = ["-- 프리셋 선택 --"] + list(profile_options.keys())

            current_scheduled_profile_name = "-- 프리셋 선택 --"
            displayed_schedule_time_kst = "09:00" # 기본값
            # 예약된 작업이 있고, 해당 profile_id가 현재 available_profiles에 있다면 이름 설정
            if st.session_state['scheduled_task'] and available_profiles:
                task = st.session_state['scheduled_task']
                task_profile_id = task['profile_id']
                for p in available_profiles: # available_profiles를 기준으로 찾음
                    if p['id'] == task_profile_id:
                        current_scheduled_profile_name = p['profile_name']
                        break
                
                # DB에 저장된 UTC 시간을 KST로 변환하여 표시
                try:
                    task_hour_utc, task_minute_utc = map(int, task['schedule_time'].split(':'))
                    dummy_dt_utc = datetime(2000, 1, 1, task_hour_utc, task_minute_utc) # 더미 날짜 사용
                    displayed_dt_kst = dummy_dt_utc + timedelta(hours=KST_OFFSET_HOURS)
                    displayed_schedule_time_kst = displayed_dt_kst.strftime('%H:%M')
                except ValueError:
                    st.warning("⚠️ 저장된 예약 시간 형식이 올바르지 않습니다. 기본값으로 표시됩니다.")
                    displayed_schedule_time_kst = "09:00" # 파싱 오류 시 기본값

            selected_schedule_profile_name = st.selectbox(
                "예약할 검색 프리셋 선택:",
                profile_names_for_schedule,
                index=profile_names_for_schedule.index(current_scheduled_profile_name) if current_scheduled_profile_name in profile_names_for_schedule else 0,
                key="schedule_profile_selector"
            )
            
            schedule_days_options = ["매일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
            default_schedule_day = st.session_state['scheduled_task']['schedule_day'] if st.session_state['scheduled_task'] else "매일"
            selected_schedule_day = st.selectbox(
                "반복 요일 설정:",
                schedule_days_options,
                index=schedule_days_options.index(default_schedule_day) if default_schedule_day in schedule_days_options else 0,
                key="schedule_day_selector"
            )

            # 사용자 입력은 KST 기준
            schedule_time_input_kst = st.text_input(
                "자동 전송 시간 (HH:MM) (한국 시간 기준):",
                value=displayed_schedule_time_kst, # KST로 변환된 시간 표시
                max_chars=5,
                help="예: 09:00 (오전 9시), 14:30 (오후 2시 30분). 한국 시간 기준입니다."
            )

            default_schedule_emails = st.session_state['scheduled_task']['recipient_emails'] if st.session_state['scheduled_task'] else ""
            schedule_recipient_emails_input = st.text_area(
                "예약 보고서 수신자 이메일 (콤마로 구분):",
                value=default_schedule_emails,
                height=70,
                help="예약된 보고서를 받을 이메일 주소를 콤마(,)로 구분하여 입력하세요."
            )

            col_set_schedule, col_clear_schedule = st.columns(2)
            with col_set_schedule:
                if st.button("예약 설정/업데이트", help="선택된 프리셋과 시간으로 보고서 자동 전송을 예약합니다."):
                    if selected_schedule_profile_name == "-- 프리셋 선택 --":
                        st.warning("예약할 검색 프리셋을 선택해주세요.")
                    elif not re.match(r"^(?:2[0-3]|[01]?[0-9]):(?:[0-5]?[0-9])$", schedule_time_input_kst):
                        st.warning("유효한 시간 형식(HH:MM)을 입력해주세요.")
                    elif not schedule_recipient_emails_input.strip():
                        st.warning("예약 보고서를 받을 수신자 이메일 주소를 입력해주세요.")
                    else:
                        # KST 입력 시간을 UTC 시간으로 변환하여 저장
                        try:
                            input_hour_kst, input_minute_kst = map(int, schedule_time_input_kst.split(':'))
                            dummy_dt_kst = datetime(2000, 1, 1, input_hour_kst, input_minute_kst)
                            scheduled_time_utc = dummy_dt_kst - timedelta(hours=KST_OFFSET_HOURS)
                            scheduled_time_str_utc = scheduled_time_utc.strftime('%H:%M')
                        except ValueError:
                            st.error("🚨 입력된 시간 형식이 올바르지 않습니다. 다시 확인해주세요.")
                            st.stop()

                        selected_profile_id_for_schedule = profile_options.get(selected_schedule_profile_name)
                        if selected_profile_id_for_schedule:
                            if database_manager.save_scheduled_task(selected_profile_id_for_schedule, scheduled_time_str_utc, selected_schedule_day, schedule_recipient_emails_input):
                                st.success(f"✅ 보고서 자동 전송이 '{selected_schedule_day}' '{schedule_time_input_kst}' (한국 시간)으로 예약되었습니다. 프리셋: '{selected_schedule_profile_name}'")
                                st.session_state['scheduled_task'] = database_manager.get_scheduled_task() # 예약 정보 새로고침
                                st.rerun()
                            else:
                                st.error("🚨 보고서 예약 설정에 실패했습니다.")
                        else:
                            st.error("🚨 선택된 프리셋을 찾을 수 없습니다. 다시 시도해주세요.")
            
            with col_clear_schedule:
                if st.button("예약 취소", help="현재 설정된 보고서 자동 전송 예약을 취소합니다."):
                    if database_manager.clear_scheduled_task():
                        st.success("✅ 보고서 자동 전송 예약이 취소되었습니다.")
                        st.session_state['scheduled_task'] = None # 세션 상태 초기화
                        st.rerun()
                    else:
                        st.error("🚨 보고서 예약 취소에 실패했습니다.")

        with col_manual_send_main: # 수동 전송 섹션을 오른쪽 컬럼으로 이동
            st.subheader("현재 예약된 작업")
            # 자동 전송 모드 버튼과 상태 메시지
            col_auto_toggle_btn, col_auto_toggle_status = st.columns([0.4, 0.6])
            with col_auto_toggle_btn:
                if st.session_state['auto_refresh_on']:
                    if st.button("🔄 자동 전송 모드 OFF", help="앱의 자동 새로고침을 끄고 예약된 보고서 전송을 중지합니다."):
                        st.session_state['auto_refresh_on'] = False
                        st.rerun()
                else:
                    if st.button("▶️ 자동 전송 모드 ON", help="앱이 주기적으로 새로고침되어 예약된 보고서를 자동으로 전송합니다."):
                        st.session_state['auto_refresh_on'] = True
                        st.session_state['auto_refresh_counter'] = 0
                        st.rerun()
            with col_auto_toggle_status:
                if st.session_state['auto_refresh_on']:
                    st.success("자동 전송 모드가 활성화되었습니다. 앱이 켜져 있는 동안 예약된 시간에 보고서가 전송됩니다.")
                else:
                    st.warning("예약 전송을 위해 자동 모드를 켜주세요.")
            
            # 자동 새로고침 JavaScript 삽입
            js_code = f"""
            <script>
                let intervalId;
                const startRefresh = () => {{
                    if (!intervalId) {{
                        intervalId = setInterval(() => {{
                            const isTaskRunning = {json.dumps(st.session_state.get('scheduled_task_running', False))}; // 오류 방지
                            if (!isTaskRunning) {{
                                window.location.reload();
                            }} else {{
                                console.log("Scheduled task is running, auto-refresh paused.");
                            }}
                        }}, 1000); // 1초마다 새로고침 시도
                    }}
                }};
                const stopRefresh = () => {{
                    if (intervalId) {{
                        clearInterval(intervalId);
                        intervalId = null;
                    }}
                }};

                // 페이지 로드 시 새로고침 시작
                if ({json.dumps(st.session_state.get('auto_refresh_on', False), ensure_ascii=False)}) {{ // 오류 방지
                    startRefresh();
                }} else {{
                    stopRefresh();
                }}
            </script>
            """
            components.html(js_code, height=0, width=0, scrolling=False)
            
            if st.session_state['auto_refresh_on']:
                if st.session_state['auto_refresh_counter'] % 60 == 0:
                    print(f"앱 구동 중... ({st.session_state['auto_refresh_counter']}초 경과)")
                time.sleep(1)
                st.session_state['auto_refresh_counter'] += 1
                st.rerun()


            if st.session_state['scheduled_task']:
                task = st.session_state['scheduled_task']
                # search_profiles를 항상 최신 DB 정보로 가져와서 사용
                profiles_dict_for_display = {p['id']: p['profile_name'] for p in database_manager.get_search_profiles()}
                profile_name = profiles_dict_for_display.get(task['profile_id'], "알 수 없는 프리셋") # 여기서 '알 수 없는 프리셋'이 뜨는 원인
                
                # DB에 저장된 UTC 시간을 KST로 변환하여 표시
                displayed_task_time_kst = "N/A"
                try:
                    task_hour_utc, task_minute_utc = map(int, task['schedule_time'].split(':'))
                    dummy_dt_utc = datetime(2000, 1, 1, task_hour_utc, task_minute_utc)
                    displayed_dt_kst = dummy_dt_utc + timedelta(hours=KST_OFFSET_HOURS)
                    displayed_task_time_kst = displayed_dt_kst.strftime('%H:%M')
                except ValueError:
                    st.warning("⚠️ 저장된 예약 시간 형식이 올바르지 않습니다. 확인이 필요합니다.")
                
                st.info(f"**프리셋**: {profile_name}\n"
                        f"**전송 시간**: {displayed_task_time_kst} (한국 시간)\n" # 한국 시간으로 표시
                        f"**반복 요일**: {task['schedule_day']}\n"
                        f"**수신자**: {task['recipient_emails']}\n"
                        f"**마지막 실행일**: {task['last_run_date'] if task['last_run_date'] else '없음'}")
                
            else:
                st.info("현재 예약된 보고서 자동 전송 작업이 없습니다.")

            st.markdown("---")

            st.subheader("📧 보고서 및 특약 수동 전송")
            st.markdown("생성된 뉴스 트렌드 보고서와 문서 분석 페이지에서 생성된 특약을 이메일로 즉시 전송합니다.")

            manual_recipient_emails_str = st.text_input(
                "수동 전송 수신자 이메일 (콤마로 구분)",
                value=st.session_state['manual_email_recipient_input'],
                key="manual_email_recipients_input",
                help="보고서와 특약을 받을 이메일 주소를 콤마(,)로 구분하여 입력하세요."
            )

            col_send_all, col_send_report, col_send_endorsement = st.columns([0.4, 0.3, 0.3])

            with col_send_all:
                if st.button("⚡ 보고서 & 특약 모두 전송", help="생성된 보고서와 특약을 연속으로 이메일 전송합니다."):
                    manual_recipient_emails_list = [e.strip() for e in manual_recipient_emails_str.split(',') if e.strip()]

                    if not manual_recipient_emails_list:
                        st.session_state['manual_email_status_message'] = "🚨 수신자 이메일 주소를 입력해주세요."
                        st.session_state['manual_email_status_type'] = "error"
                        st.rerun()
                    elif not email_config_ok:
                        st.session_state['manual_email_status_message'] = "🚨 이메일 설정 정보가 올바르지 않아 이메일을 전송할 수 없습니다."
                        st.session_state['manual_email_status_type'] = "error"
                        st.rerun()
                    else:
                        with st.spinner("보고서 이메일 전송 중..."):
                            report_send_success = False
                            email_subject_report = f"뉴스 트렌드 분석 보고서 - {datetime.now().strftime('%Y%m%d')}"
                            report_body = st.session_state.get('prettified_report_for_download', "생성된 뉴스 트렌드 보고서가 없습니다.")
                            
                            excel_data_for_attachment = None
                            if st.session_state.get('prettified_report_for_download'):
                                excel_data_for_attachment = data_exporter.export_ai_report_to_excel(
                                    st.session_state['prettified_report_for_download'], sheet_name='AI_Insights_Report'
                                )

                            report_attachments = []
                            if excel_data_for_attachment:
                                report_attachments.append({
                                    "data": excel_data_for_attachment.getvalue(),
                                    "filename": data_exporter.generate_filename("ai_insights_report", "xlsx"),
                                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                })
                            
                            if not report_attachments:
                                st.session_state['manual_email_status_message'] = "🚨 첨부할 보고서 내용이 없어 보고서 전송을 건너뜁니다."
                                st.session_state['manual_email_status_type'] = "error"
                            else:
                                report_send_success = email_sender.send_email_with_multiple_attachments(
                                    sender_email=SENDER_EMAIL,
                                    sender_password=SENDER_PASSWORD,
                                    receiver_emails=manual_recipient_emails_list,
                                    smtp_server=SMTP_SERVER,
                                    smtp_port=SMTP_PORT,
                                    subject=email_subject_report,
                                    body=report_body,
                                    attachments=report_attachments,
                                    report_format="markdown"
                                )
                                if report_send_success:
                                    st.session_state['manual_email_status_message'] = "보고서 이메일이 성공적으로 전송되었습니다!"
                                    st.session_state['manual_email_status_type'] = "success"
                                else:
                                    st.session_state['manual_email_status_message'] = "보고서 이메일 전송에 실패했습니다. 설정 및 로그를 확인해주세요."
                                    st.session_state['manual_email_status_type'] = "error"
                            st.rerun()

                        # 특약 전송 로직
                        with st.spinner("특약 이메일 전송 중..."):
                            endorsement_send_success = False
                            email_subject_endorsement = f"생성된 보험 특약 - {datetime.now().strftime('%Y%m%d')}"
                            endorsement_text_for_attachment = database_manager.get_latest_generated_endorsement()
                            
                            endorsement_attachments = []
                            if endorsement_text_for_attachment:
                                endorsement_attachments.append({
                                    "data": endorsement_text_for_attachment.encode('utf-8'),
                                    "filename": data_exporter.generate_filename("생성된_보험_특약", "txt"),
                                    "mime_type": "text/plain"
                                })
                            
                            if not endorsement_attachments:
                                st.session_state['manual_email_status_message'] = "🚨 첨부할 특약 내용이 없어 특약 전송을 건너뜁니다."
                                st.session_state['manual_email_status_type'] = "error"
                            else:
                                success = email_sender.send_email_with_multiple_attachments(
                                    sender_email=SENDER_EMAIL,
                                    sender_password=SENDER_PASSWORD,
                                    receiver_emails=manual_recipient_emails_list,
                                    smtp_server=SMTP_SERVER,
                                    smtp_port=SMTP_PORT,
                                    subject=email_subject_endorsement,
                                    body="요청하신 보험 특약 내용입니다. 첨부 파일을 확인해주세요.",
                                    attachments=endorsement_attachments,
                                    report_format="plain"
                                )
                                if success:
                                    st.session_state['manual_email_status_message'] = "특약 이메일이 성공적으로 전송되었습니다!"
                                    st.session_state['manual_email_status_type'] = "success"
                                else:
                                    st.session_state['manual_email_status_message'] = "특약 이메일 전송에 실패했습니다. 설정 및 로그를 확인해주세요."
                                    st.session_state['manual_email_status_type'] = "error"
                            st.rerun()

                        # 최종 결과 메시지
                        if report_send_success and endorsement_send_success:
                            st.success("✅ 보고서와 특약 이메일이 모두 성공적으로 전송되었습니다!")
                        elif report_send_success:
                            st.warning("⚠️ 보고서 이메일은 전송되었으나, 특약 전송에 문제가 있었습니다.")
                        elif endorsement_send_success:
                            st.warning("⚠️ 특약 이메일은 전송되었으나, 보고서 전송에 문제가 있었습니다.")
                        else:
                            st.error("🚨 보고서와 특약 이메일 전송이 모두 실패했습니다. 설정을 확인해주세요.")
                        st.session_state['manual_email_status_message'] = ""
                        st.session_state['manual_email_status_type'] = ""
                        st.rerun()


            col_send_report, col_send_endorsement = st.columns(2)

            with col_send_report:
                if st.button("🚀 보고서만 이메일 전송", help="현재 생성된 보고서만 이메일로 전송합니다."):
                    manual_recipient_emails_list = [e.strip() for e in manual_recipient_emails_str.split(',') if e.strip()]

                    if not manual_recipient_emails_list:
                        st.session_state['manual_email_status_message'] = "🚨 수신자 이메일 주소를 입력해주세요."
                        st.session_state['manual_email_status_type'] = "error"
                        st.rerun()
                    elif not email_config_ok:
                        st.session_state['manual_email_status_message'] = "🚨 이메일 설정 정보가 올바르지 않아 이메일을 전송할 수 없습니다."
                        st.session_state['manual_email_status_type'] = "error"
                        st.rerun()
                    else:
                        with st.spinner("보고서 이메일 전송 중..."):
                            email_subject = f"뉴스 트렌드 분석 보고서 - {datetime.now().strftime('%Y%m%d')}"
                            report_body = st.session_state.get('prettified_report_for_download', "생성된 뉴스 트렌드 보고서가 없습니다.")
                            
                            excel_data_for_attachment = None
                            if st.session_state.get('prettified_report_for_download'):
                                excel_data_for_attachment = data_exporter.export_ai_report_to_excel(
                                    st.session_state['prettified_report_for_download'], sheet_name='AI_Insights_Report'
                                )

                            attachments = []
                            if excel_data_for_attachment:
                                attachments.append({
                                    "data": excel_data_for_attachment.getvalue(),
                                    "filename": data_exporter.generate_filename("ai_insights_report", "xlsx"),
                                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                })
                            
                            # 이 페이지에서는 특약 첨부는 하지 않습니다.
                            # 특약 첨부는 report_automation_page에서 담당합니다.

                            success = email_sender.send_email_with_multiple_attachments( # 함수명 변경
                                sender_email=SENDER_EMAIL,
                                sender_password=SENDER_PASSWORD,
                                receiver_emails=manual_recipient_emails_list, # 리스트 형태로 전달
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

            with col_send_endorsement:
                if st.button("📝 특약만 이메일 전송", help="현재 생성된 특약만 이메일로 전송합니다."):
                    manual_recipient_emails_list = [e.strip() for e in manual_recipient_emails_str.split(',') if e.strip()]

                    if not manual_recipient_emails_list:
                        st.session_state['manual_email_status_message'] = "🚨 수신자 이메일 주소를 입력해주세요."
                        st.session_state['manual_email_status_type'] = "error"
                        st.rerun()
                    elif not email_config_ok:
                        st.session_state['manual_email_status_message'] = "🚨 이메일 설정 정보가 올바르지 않아 이메일을 전송할 수 없습니다."
                        st.session_state['email_status_type'] = "error"
                        st.rerun()
                    else:
                        with st.spinner("특약 이메일 전송 중..."):
                            email_subject = f"생성된 보험 특약 - {datetime.now().strftime('%Y%m%d')}"
                            endorsement_text_for_attachment = database_manager.get_latest_generated_endorsement()
                            
                            attachments = []
                            if endorsement_text_for_attachment:
                                attachments.append({
                                    "data": endorsement_text_for_attachment.encode('utf-8'),
                                    "filename": data_exporter.generate_filename("생성된_보험_특약", "txt"),
                                    "mime_type": "text/plain"
                                })
                            
                            if not attachments:
                                st.session_state['manual_email_status_message'] = "🚨 첨부할 특약 내용이 없습니다. 먼저 생성해주세요."
                                st.session_state['manual_email_status_type'] = "error"
                                st.rerun()
                            else:
                                success = email_sender.send_email_with_multiple_attachments(
                                    sender_email=SENDER_EMAIL,
                                    sender_password=SENDER_PASSWORD,
                                    receiver_emails=manual_recipient_emails_list,
                                    smtp_server=SMTP_SERVER,
                                    smtp_port=SMTP_PORT,
                                    subject=email_subject,
                                    body="요청하신 보험 특약 내용입니다. 첨부 파일을 확인해주세요.",
                                    attachments=attachments,
                                    report_format="plain"
                                )
                                if success:
                                    st.session_state['manual_email_status_message'] = "특약 이메일이 성공적으로 전송되었습니다!"
                                    st.session_state['manual_email_status_type'] = "success"
                                else:
                                    st.session_state['manual_email_status_message'] = "특약 이메일 전송에 실패했습니다. 설정 및 로그를 확인해주세요."
                                    st.session_state['manual_email_status_type'] = "error"
                            st.rerun()

    # 수동 이메일 전송 상태 메시지 표시
    if st.session_state['manual_email_status_message']:
        if st.session_state['manual_email_status_type'] == "success":
            st.success(st.session_state['manual_email_status_message'])
        elif st.session_state['manual_email_status_type'] == "error":
            st.error(st.session_state['manual_email_status_message'])
        st.session_state['manual_email_status_message'] = ""
        st.session_state['manual_email_status_type'] = ""

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
