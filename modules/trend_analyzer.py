# modules/trend_analyzer.py

import re
from collections import Counter
from datetime import datetime, timedelta
import streamlit as st # Streamlit의 st.warning 등을 사용하기 위해 임시로 import.
                        # 실제 프로덕션에서는 이 로깅 부분을 다른 방식으로 처리하는 것이 좋습니다.
from konlpy.tag import Okt # konlpy의 Okt 형태소 분석기 임포트

# Okt 형태소 분석기 초기화 (한 번만 수행)
# Streamlit 환경에서는 전역 변수로 선언하거나, 함수 내에서 한 번만 초기화되도록 캐싱하는 것이 좋습니다.
# 여기서는 간단히 전역 변수로 선언하지만, 실제 앱에서는 st.cache_resource 등을 고려할 수 있습니다.
try:
    okt = Okt()
    KONLPY_AVAILABLE = True
except Exception as e:
    st.error(f"🚨 Konlpy (Okt) 초기화 실패: {e}. 한국어 형태소 분석 없이 키워드를 추출합니다.")
    st.info("💡 Konlpy를 사용하려면 Java Development Kit (JDK) 1.8 이상이 설치되어 있어야 합니다.")
    KONLPY_AVAILABLE = False
    okt = None # 초기화 실패 시 None으로 설정

def extract_keywords_from_text(text: str) -> list[str]:
    """
    텍스트에서 키워드를 추출합니다.
    konlpy Okt 형태소 분석기를 사용하여 명사를 추출하고, 불용어 제거를 수행합니다.
    """
    if not text:
        return []

    keywords = []
    if KONLPY_AVAILABLE and okt:
        try:
            # Okt를 사용하여 명사만 추출
            nouns = okt.nouns(text)
            
            # 일반적인 불용어 목록 (확장 가능)
            # 형태소 분석 후의 명사 형태를 고려하여 불용어 목록 조정
            stopwords = [
                "은", "는", "이", "가", "을", "를", "와", "과", "도", "만", "고", "에", "의", "한", "그", "저", "것", "수", "등", "및",
                "대한", "통해", "이번", "지난", "다", "있다", "없다", "한다", "된다", "밝혔다", "말했다", "했다", "위해", "으로", "에서",
                "으로", "로부터", "까지", "부터", "으로", "하여", "에게", "처럼", "만큼", "듯이", "보다", "아니라", "아니면", "그리고",
                "그러나", "하지만", "따라서", "때문에", "대해", "관련", "최근", "이날", "오전", "오후", "기자", "뉴스", "연합뉴스",
                "조선비즈", "한겨레", "ytn", "mbn", "뉴시스", "매일경제", "한국경제", # 언론사명 소문자 처리
                "년", "월", "일", "때", "곳", "점", "분", "명", "개", "위", "말", "뒤", "전", "중", "측", "내", "밖", "고", "데", "바"
            ]

            # 두 글자 이상인 명사만 포함하고 불용어 제거
            # 명사 추출 후 소문자 변환하여 불용어와 비교
            keywords = [
                word.lower() for word in nouns
                if len(word) > 1 and word.lower() not in stopwords
            ]
        except Exception as e:
            st.warning(f"⚠️ Konlpy 명사 추출 중 오류 발생: {e}. 일반 토큰화로 대체합니다.")
            # 오류 발생 시 기존의 간단한 토큰화 방식으로 대체
            text = re.sub(r'[^가-힣a-zA-Z0-9\s]', '', text)
            tokens = text.lower().split()
            stopwords = [
                "은", "는", "이", "가", "을", "를", "와", "과", "도", "만", "고", "에", "의", "한", "그", "저", "것", "수", "등", "및",
                "대한", "통해", "이번", "지난", "다", "있다", "없다", "한다", "된다", "밝혔다", "말했다", "했다", "위해", "으로", "에서",
                "으로", "로부터", "까지", "부터", "으로", "하여", "에게", "처럼", "만큼", "듯이", "보다", "아니라", "아니면", "그리고",
                "그러나", "하지만", "따라서", "때문에", "대해", "관련", "지난", "최근", "이번", "이날", "오전", "오후", "오후", "오전",
                "기자", "뉴스", "연합뉴스", "조선비즈", "한겨레", "ytn", "mbn", "뉴시스", "매일경제", "한국경제"
            ]
            keywords = [word for word in tokens if len(word) > 1 and word not in stopwords]
    else:
        # konlpy를 사용할 수 없는 경우 기존의 간단한 토큰화 방식 사용
        text = re.sub(r'[^가-힣a-zA-Z0-9\s]', '', text)
        tokens = text.lower().split()
        stopwords = [
            "은", "는", "이", "가", "을", "를", "와", "과", "도", "만", "고", "에", "의", "한", "그", "저", "것", "수", "등", "및",
            "대한", "통해", "이번", "지난", "다", "있다", "없다", "한다", "된다", "밝혔다", "말했다", "했다", "위해", "으로", "에서",
            "으로", "로부터", "까지", "부터", "으로", "하여", "에게", "처럼", "만큼", "듯이", "보다", "아니라", "아니면", "그리고",
            "그러나", "하지만", "따라서", "때문에", "대해", "관련", "지난", "최근", "이번", "이날", "오전", "오후", "오후", "오전",
            "기자", "뉴스", "연합뉴스", "조선비즈", "한겨레", "ytn", "mbn", "뉴시스", "매일경제", "한국경제"
        ]
        keywords = [word for word in tokens if len(word) > 1 and word not in stopwords]

    return keywords

def analyze_keyword_trends(articles_metadata: list[dict], recent_days_period: int = 2, total_days_period: int = 15, min_surge_ratio: float = 1.5, min_recent_freq: int = 3) -> list[dict]:
    """
    기사 메타데이터를 기반으로 키워드 트렌드를 분석합니다.
    recent_days_period: 트렌드를 감지할 최근 기간 (예: 2일)
    total_days_period: 비교할 전체 기간 (예: 15일)
    min_surge_ratio: 최근 기간 빈도 / 과거 기간 빈도 비율이 이 값 이상일 때 트렌드로 간주
    min_recent_freq: 최근 기간에 최소한 이 횟수 이상 언급되어야 트렌드로 간주
    반환 값: [{keyword: str, recent_freq: int, past_freq: int, surge_ratio: float}]
    """
    if not articles_metadata:
        return []

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    recent_articles = []
    past_articles = []

    for article in articles_metadata:
        article_date = article.get("날짜")
        if not isinstance(article_date, datetime):
            # 날짜 파싱 실패한 경우, 오늘 날짜로 간주하여 처리 (정확도 낮음)
            st.warning(f"경고: '{article['제목']}' 기사의 날짜 파싱 실패. 오늘 날짜로 간주하여 분석에 포함합니다.")
            article_date = today

        if today - timedelta(days=recent_days_period) <= article_date:
            recent_articles.append(article)
        elif today - timedelta(days=total_days_period) <= article_date < today - timedelta(days=recent_days_period):
            past_articles.append(article)

    # 각 기간의 키워드 빈도 계산
    recent_keywords = Counter()
    for article in recent_articles:
        # 트렌드 분석 시 제목과 미리보기 스니펫 모두 활용
        text_for_keywords = article["제목"] + " " + article.get("내용", "") # '내용'이 이제 미리보기 스니펫
        recent_keywords.update(extract_keywords_from_text(text_for_keywords)) # 함수명 변경 적용

    past_keywords = Counter()
    for article in past_articles:
        # 트렌드 분석 시 제목과 미리보기 스니펫 모두 활용
        text_for_keywords = article["제목"] + " " + article.get("내용", "") # '내용'이 이제 미리보기 스니펫
        past_keywords.update(extract_keywords_from_text(text_for_keywords)) # 함수명 변경 적용

    trending_keywords_list = [] # 리스트 형태로 변경
    for keyword, recent_freq in recent_keywords.items():
        past_freq = past_keywords.get(keyword, 0) # 과거 기간에 없으면 0

        # 최근 기간에 최소 빈도 이상이어야 함
        if recent_freq < min_recent_freq:
            continue

        surge_ratio = None
        if past_freq == 0:
            # 과거에 없었는데 최근에 나타난 키워드는 트렌드로 간주
            if recent_freq >= min_recent_freq:
                surge_ratio = float('inf') # 무한대로 표현
        else:
            surge_ratio = recent_freq / past_freq
            if surge_ratio < min_surge_ratio: # 최소 증가율 미달 시 트렌드 아님
                continue

        trending_keywords_list.append({
            "keyword": keyword,
            "recent_freq": recent_freq,
            "past_freq": past_freq,
            "surge_ratio": surge_ratio
        })

    # 빈도 높은 순으로 정렬
    trending_keywords_list = sorted(trending_keywords_list, key=lambda x: x['recent_freq'], reverse=True)

    return trending_keywords_list
