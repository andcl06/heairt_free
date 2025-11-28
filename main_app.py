# main_app.py
# 이 파일은 '보험특약개발 솔루션'의 메인 애플리케이션으로,
# 랜딩 페이지, 최신 트렌드 분석, 문서 분석 기능을 통합합니다.
#
# Potens.dev API 키가 만료되어 Gemini API 키로 교체하기 위해 수정되었습니다.

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import os
from dotenv import load_dotenv
from loguru import logger # 로깅을 위해 필요

# --- 페이지 함수 임포트 (modules 디렉토리에서 직접 임포트) ---
from modules.landing_page import landing_page
from modules.trend_analysis_page import trend_analysis_page
from modules.document_analysis_page import document_analysis_page
from modules.report_automation_page import report_automation_page # 새로 추가: 보고서 자동화 페이지


# --- 환경 변수 로드 (앱 시작 시 한 번만) ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Potens API 키 대신 Gemini API 키를 로드하도록 변경


# --- 메인 애플리케이션 라우팅 ---
def main_app():
    """
    애플리케이션의 메인 진입점입니다.
    로그인 없이 바로 랜딩 페이지로 시작하며, 페이지를 라우팅합니다.
    """
    # Streamlit 페이지 설정 (전역에서 한 번만 설정)
    st.set_page_config(layout="wide", page_title="트렌드 기반 특약생성 솔루션") # 앱 이름 변경

    # 세션 상태 초기화 (앱이 처음 로드될 때만 실행)
    if "username" not in st.session_state: # 사용자 이름은 환영 메시지를 위해 유지
        st.session_state.username = "사용자" # 기본 사용자 이름 설정 (로그인 제거)
    if "page" not in st.session_state:
        st.session_state.page = "landing" # 앱 시작 시 기본 페이지를 랜딩으로 고정

    # 라우팅 로직 (로그인 검사 없이 바로 페이지 호출)
    if st.session_state.page == "landing":
        landing_page() # modules/landing_page.py의 함수 호출
    elif st.session_state.page == "trend":
        trend_analysis_page() # modules/trend_analysis_page.py의 함수 호출
    elif st.session_state.page == "document":
        document_analysis_page() # modules/document_analysis_page.py의 함수 호출
    elif st.session_state.page == "automation": # 새로 추가: 자동화 페이지 라우팅
        report_automation_page() # modules/report_automation_page.py의 함수 호출
    else:
        st.session_state.page = "landing" # 알 수 없는 페이지 상태일 경우 랜딩 페이지로 리다이렉트


if __name__ == "__main__":
    main_app()
