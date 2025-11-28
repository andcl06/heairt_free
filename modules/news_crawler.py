# modules/news_crawler.py

import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime

# Streamlit의 st.error, st.warning 등을 사용하기 위해 임시로 import.
# 실제 프로덕션에서는 이 로깅 부분을 다른 방식으로 처리하는 것이 좋습니다.
import streamlit as st

def crawl_naver_news_metadata(keyword: str, current_search_date: datetime, max_naver_search_pages_per_day: int):
    """
    지정된 키워드와 날짜로 네이버 뉴스 메타데이터를 크롤링합니다.
    Args:
        keyword (str): 검색할 키워드.
        current_search_date (datetime): 검색할 날짜 (datetime 객체).
        max_naver_search_pages_per_day (int): 해당 날짜에 크롤링할 최대 페이지 수.
    Returns:
        list[dict]: 수집된 기사 메타데이터 목록.
    """
    articles_on_this_day = []
    formatted_search_date = current_search_date.strftime('%Y.%m.%d')

    for page in range(max_naver_search_pages_per_day):
        start_num = page * 10 + 1
        search_url = (
            f"https://search.naver.com/search.naver?where=news&query={keyword}"
            f"&sm=tab_opt&sort=0&photo=0&field=0&pd=3"
            f"&ds={formatted_search_date}"
            f"&de={formatted_search_date}"
            f"&start={start_num}"
        )

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'}
            response = requests.get(search_url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            title_spans = soup.find_all("span", class_="sds-comps-text-type-headline1")

            if not title_spans:
                # 해당 페이지에 기사가 없으면 다음 페이지 크롤링 중단
                break
            else:
                articles_on_this_page_count = 0
                for title_span in title_spans:
                    link_tag = title_span.find_parent('a')

                    if link_tag and 'href' in link_tag.attrs:
                        title = title_span.text.strip()
                        link = link_tag['href']

                        summary_snippet_text = ""
                        next_sibling_a_tag = link_tag.find_next_sibling('a')
                        if next_sibling_a_tag:
                            snippet_span = next_sibling_a_tag.find('span', class_='sds-comps-text-type-body1')
                            if snippet_span:
                                summary_snippet_text = snippet_span.get_text(strip=True)
                            else:
                                summary_snippet_text = next_sibling_a_tag.get_text(strip=True)

                        if not (link.startswith('javascript:') or 'ad.naver.com' in link):
                            articles_on_this_day.append({
                                "제목": title,
                                "링크": link,
                                "날짜": current_search_date, # datetime 객체 유지
                                "내용": summary_snippet_text if summary_snippet_text else "" # None 방지
                            })
                            articles_on_this_page_count += 1
                
                # 현재 페이지에 기사가 없으면 다음 페이지 크롤링 중단
                if articles_on_this_page_count == 0:
                    break

            time.sleep(0.5) # 서버 부하를 줄이기 위한 딜레이

        except requests.exceptions.RequestException as e:
            st.error(f"웹 페이지 요청 중 오류 발생 ({formatted_search_date} 날짜, 페이지 {page + 1}): {e}")
            break # 오류 발생 시 해당 날짜의 크롤링 중단
        except Exception as e:
            st.error(f"스크립트 실행 중 오류 발생 ({formatted_search_date} 날짜, 페이지 {page + 1}): {e}")
            break # 오류 발생 시 해당 날짜의 크롤링 중단
    return articles_on_this_day
