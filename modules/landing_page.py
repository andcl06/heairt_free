# modules/landing_page.py

import streamlit as st

def landing_page():
    """로그인 후 사용자가 기능을 선택하는 랜딩 페이지를 렌더링합니다."""

    # 페이지 전체에 적용될 CSS 스타일 (안정성을 위해 최소한의 스타일만 유지)
    st.markdown("""
        <style>
        /* 페이지 배경색 설정 */
        body {
            background-color: #f0f2f6;
        }
        /* 앱 타이틀 및 서브헤더 중앙 정렬 */
        h1, h2, h3, p {
            text-align: center;
        }
        /* 기능 블록 컨테이너 스타일 */
        .feature-block {
            border: 1px solid #ddd;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 20px;
            min-height: 350px; /* 높이 조절 */
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 2px 2px 8px rgba(0,0,0,0.1); /* 그림자 효과 */
            background-color: white; /* 배경색 추가 */
        }
        .feature-block ul {
            list-style-type: none;
            padding-left: 0;
            line-height: 1.8;
            text-align: left; /* 목록 텍스트 왼쪽 정렬 */
            color: #333;
        }
        .feature-block h3 {
            text-align: left; /* 블록 제목 왼쪽 정렬 */
            margin-top: 0;
            font-size: 1.5em;
        }
        /* 앱 초기화 버튼 중앙 정렬 */
        div.stButton > button[data-testid="stButton-reset_app"] {
            display: block;
            margin-left: auto;
            margin-right: auto;
            width: auto; /* 내용에 맞춰 너비 조절 */
        }
        /* 모든 페이지 이동 버튼의 공통 스타일 (Streamlit의 primary 테마 색상을 따름) */
        div.stButton > button[data-testid*="start_"] { /* 'start_'로 시작하는 data-testid를 가진 버튼 */
            color: white; /* 텍스트 색상 흰색 */
            width: 100%; /* 너비 꽉 채우기 */
            margin-top: 20px; /* 위에 여백 추가 */
        }
        </style>
    """, unsafe_allow_html=True)


    # 상단 로고 및 앱 이름
    st.markdown("<h1 style='color: #FF4B4B;'>HEAIRT 트렌드 인사이트 자동화</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: grey; margin-top: -10px;'>Trend Insight Automator</p>", unsafe_allow_html=True)

    st.markdown("---")

    # AI 기반 보험 특약 개발 솔루션 섹션
    st.markdown("<h2 style='font-size: 2.5em;'>AI 기반 보험 특약 개발 솔루션</h2>", unsafe_allow_html=True)
    st.markdown(
        "<p style='font-size: 1.1em; color: #555;'>"
        "최신 뉴스 트렌드를 분석하고 이를 바탕으로 보험 특약 개발을 위한 심도적인 인사이트를 제공하는 전문 솔루션입니다."
        "</p>",
        unsafe_allow_html=True
    )
    # '보험 업계의 혁신을 선도합니다' 버튼 제거
    # st.button("보험 업계의 혁신을 선도합니다", help="이 버튼은 시각적 요소이며 기능은 없습니다.", key="vision_button", type="primary")

    st.markdown("<br><br>", unsafe_allow_html=True) # 제거된 버튼으로 인한 공간 확보는 유지

    # 핵심 기능 섹션
    st.markdown("<h2 style='font-size: 2em;'>핵심 기능</h2>", unsafe_allow_html=True)
    st.markdown("---")

    # 3개의 컬럼을 사용하여 기능 블록 배치
    col1, col2, col3 = st.columns(3)

    # 뉴스 트렌드 분석기 블록
    with col1:
        st.markdown("""
            <div class="feature-block">
                <h3>📰 뉴스 트렌드 분석기</h3>
                <ul>
                    <li>✔️ 실시간 뉴스데이터 수집 및 AI 기반 트렌드 분석</li>
                    <li>✔️ 키워드 트렌드 분석</li>
                    <li>✔️ AI 기반 보험 방향성 분석</li>
                    <li>✔️ 전문 보고서 자동 생성</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        # 실제 버튼 로직은 HTML 마크업 외부에서 처리 (Streamlit 기본 primary 색상 사용)
        if st.button("트렌드 분석 시작", key="start_trend", use_container_width=True, type="primary"):
            st.session_state.page = "trend"
            st.rerun()


    # 문서 기반 특약 생성 블록
    with col2:
        st.markdown("""
            <div class="feature-block">
                <h3>📄 문서 기반 특약 생성</h3>
                <ul>
                    <li>✔️ 문서 내용을 통한 맞춤형 보험 특약 생성</li>
                    <li>✔️ QA 기능</li>
                    <li>✔️ 11가지 항목별 특약 생성</li>
                    <li>✔️ 다양한 문서 형식 지원</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        if st.button("문서 분석 시작", key="start_document", use_container_width=True, type="primary"):
            st.session_state.page = "document"
            st.rerun()

    # 보고서 자동화 블록
    with col3:
        st.markdown("""
            <div class="feature-block">
                <h3>⏰ 보고서 자동화</h3>
                <ul>
                    <li>✔️ 예약 기반 보고서 생성 및 이메일 전송</li>
                    <li>✔️ 스케줄 기반 자동 실행</li>
                    <li>✔️ 이메일 전송 지원</li>
                    <li>✔️ Excel/TXT 형식 지원</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        if st.button("자동화 설정", key="start_automation", use_container_width=True, type="primary"):
            st.session_state.page = "automation"
            st.rerun()

    st.markdown("---")

    # 앱 초기화 버튼
    # Streamlit 기본 버튼 스타일을 따르며 중앙 정렬만 CSS로 처리
    if st.button("🔄 앱 초기화 (다시 시작)", use_container_width=False, key="reset_app"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

    # 저작권 정보
    st.markdown("<p style='font-size: 12px; color: grey; margin-top: 30px;'>&copy; 2025. 트렌드 기반 특약생성 솔루션. By 메이커스랩 1기 3팀</p>", unsafe_allow_html=True)
