# modules/database_manager.py

import sqlite3
from datetime import datetime
import streamlit as st # Streamlit의 st.session_state, st.success, st.error 등을 사용하기 위해 임시로 import.
                        # 실제 프로덕션에서는 이 로깅 부분을 다른 방식으로 처리하는 것이 좋습니다.

DB_FILE = 'news_data.db'

def init_db():
    """데이터베이스를 초기화하고 테이블을 생성합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            date TEXT NOT NULL,
            content TEXT,
            crawl_timestamp TEXT NOT NULL
        )
    ''')
    # 새로운 테이블 추가: 검색 프로필 저장
    c.execute('''
        CREATE TABLE IF NOT EXISTS search_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT UNIQUE NOT NULL,
            keyword TEXT NOT NULL,
            total_search_days INTEGER NOT NULL,
            recent_trend_days INTEGER NOT NULL,
            max_naver_search_pages_per_day INTEGER NOT NULL
        )
    ''')
    # 새로운 테이블 추가: 예약된 작업 저장 (schedule_day 컬럼 추가)
    c.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL,
            schedule_time TEXT NOT NULL, -- "HH:MM" 형식
            schedule_day TEXT NOT NULL, -- "매일", "월요일", "화요일" 등
            recipient_emails TEXT NOT NULL, -- 콤마로 구분된 이메일 주소
            last_run_date TEXT, -- 마지막 실행 날짜 (YYYY-MM-DD)
            FOREIGN KEY (profile_id) REFERENCES search_profiles(id) ON DELETE CASCADE
        )
    ''')
    # 새 테이블 추가: 생성된 특약 저장 (가장 최신 특약만 저장)
    c.execute('''
        CREATE TABLE IF NOT EXISTS generated_endorsements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endorsement_text TEXT NOT NULL,
            generation_timestamp TEXT NOT NULL
        )
    ''')
    # 새 테이블 추가: 문서 분석을 위해 업로드된 문서의 전체 텍스트 저장
    c.execute('''
        CREATE TABLE IF NOT EXISTS document_texts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_text TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    # 새로 추가: 중간 요약문 저장 (임시 사용)
    c.execute('''
        CREATE TABLE IF NOT EXISTS intermediate_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary_text TEXT NOT NULL,
            batch_id TEXT NOT NULL, -- 어떤 배치에서 생성된 요약인지 식별
            level INTEGER NOT NULL, -- 요약 계층 (예: 1차 요약, 2차 요약)
            timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insert_article(article: dict):
    """기사 데이터를 데이터베이스에 삽입합니다. 중복 링크는 건너뛰거나 업데이트합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # 링크가 이미 존재하면 업데이트, 없으면 삽입
        c.execute("INSERT OR REPLACE INTO articles (link, title, date, content, crawl_timestamp) VALUES (?, ?, ?, ?, ?)",
                  (article['링크'], article['제목'], article['날짜'], article['내용'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    except Exception as e:
        print(f"오류: 데이터베이스 삽입/업데이트 실패 - {e} (링크: {article['링크']})")
    finally:
        conn.close()

def get_all_articles():
    """데이터베이스의 모든 기사 데이터를 가져옵니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT title, link, date, content, crawl_timestamp FROM articles ORDER BY date DESC, crawl_timestamp DESC")
    articles = c.fetchall()
    conn.close()
    return articles

def clear_db_content():
    """데이터베이스의 모든 기사 기록을 삭제합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM articles")
        # 추가: 검색 프로필, 예약 작업, 생성된 특약, 문서 텍스트, 중간 요약도 함께 삭제
        c.execute("DELETE FROM search_profiles")
        c.execute("DELETE FROM scheduled_tasks")
        c.execute("DELETE FROM generated_endorsements")
        c.execute("DELETE FROM document_texts")
        c.execute("DELETE FROM intermediate_summaries") # 새로 추가
        conn.commit()
        st.session_state['db_status_message'] = "데이터베이스의 모든 기록이 성공적으로 삭제되었습니다."
        st.session_state['db_status_type'] = "success"
    except Exception as e:
        st.session_state['db_status_message'] = f"데이터베이스 초기화 중 오류 발생: {e}"
        st.session_state['db_status_type'] = "error"
    finally:
        conn.close()

# --- 검색 프로필 관련 함수 ---
def save_search_profile(profile_name: str, keyword: str, total_search_days: int, recent_trend_days: int, max_naver_search_pages_per_day: int):
    """검색 프로필을 저장하거나 업데이트합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO search_profiles (profile_name, keyword, total_search_days, recent_trend_days, max_naver_search_pages_per_day) VALUES (?, ?, ?, ?, ?)",
                  (profile_name, keyword, total_search_days, recent_trend_days, max_naver_search_pages_per_day))
        conn.commit()
        return True
    except Exception as e:
        print(f"오류: 검색 프로필 저장/업데이트 실패 - {e}")
        return False
    finally:
        conn.close()

def get_search_profiles() -> list[dict]:
    """저장된 모든 검색 프로필을 가져옵니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, profile_name, keyword, total_search_days, recent_trend_days, max_naver_search_pages_per_day FROM search_profiles ORDER BY profile_name")
    profiles = c.fetchall()
    conn.close()
    
    profile_list = []
    for p in profiles:
        profile_list.append({
            "id": p[0],
            "profile_name": p[1],
            "keyword": p[2],
            "total_search_days": p[3],
            "recent_trend_days": p[4],
            "max_naver_search_pages_per_day": p[5]
        })
    return profile_list

def delete_search_profile(profile_id: int):
    """지정된 ID의 검색 프로필을 삭제합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM search_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"오류: 검색 프로필 삭제 실패 - {e}")
        return False
    finally:
        conn.close()

# --- 예약 작업 관련 함수 ---
def save_scheduled_task(profile_id: int, schedule_time: str, schedule_day: str, recipient_emails: str): # schedule_day 추가
    """예약된 작업을 저장하거나 업데이트합니다. (단일 예약만 가능하도록 구현)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # 기존 예약 삭제 후 새로 삽입 (단일 예약만 허용)
        c.execute("DELETE FROM scheduled_tasks")
        c.execute("INSERT INTO scheduled_tasks (profile_id, schedule_time, schedule_day, recipient_emails, last_run_date) VALUES (?, ?, ?, ?, ?)", # schedule_day 추가
                  (profile_id, schedule_time, schedule_day, recipient_emails, None)) # 초기 last_run_date는 None
        conn.commit()
        return True
    except Exception as e:
        print(f"오류: 예약 작업 저장 실패 - {e}")
        return False
    finally:
        conn.close()

def get_scheduled_task() -> dict | None:
    """현재 예약된 작업을 가져옵니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, profile_id, schedule_time, schedule_day, recipient_emails, last_run_date FROM scheduled_tasks LIMIT 1") # schedule_day 추가
    task = c.fetchone()
    conn.close()
    
    if task:
        return {
            "id": task[0],
            "profile_id": task[1],
            "schedule_time": task[2],
            "schedule_day": task[3], # schedule_day 추가
            "recipient_emails": task[4],
            "last_run_date": task[5]
        }
    return None

def update_scheduled_task_last_run_date(task_id: int, run_date: str):
    """예약된 작업의 마지막 실행 날짜를 업데이트합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("UPDATE scheduled_tasks SET last_run_date = ? WHERE id = ?", (run_date, task_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"오류: 예약 작업 마지막 실행 날짜 업데이트 실패 - {e}")
        return False
    finally:
        conn.close()

def clear_scheduled_task():
    """예약된 작업을 삭제합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM scheduled_tasks")
        conn.commit()
        return True
    except Exception as e:
        print(f"오류: 예약 작업 삭제 실패 - {e}")
        return False
    finally:
        conn.close()

# --- 생성된 특약 관련 함수 ---
def save_generated_endorsement(endorsement_text: str):
    """
    생성된 특약 텍스트를 데이터베이스에 저장합니다.
    항상 가장 최신 특약만 유지합니다 (기존 특약 삭제 후 새로 삽입).
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # 기존 특약 삭제
        c.execute("DELETE FROM generated_endorsements")
        # 새 특약 삽입
        c.execute("INSERT INTO generated_endorsements (endorsement_text, generation_timestamp) VALUES (?, ?)",
                  (endorsement_text, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return True
    except Exception as e:
        print(f"오류: 생성된 특약 저장 실패 - {e}")
        return False
    finally:
        conn.close()

def get_latest_generated_endorsement() -> str | None:
    """
    데이터베이스에 저장된 가장 최신 특약 텍스트를 가져옵니다.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT endorsement_text FROM generated_endorsements ORDER BY generation_timestamp DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    if result:
        return result[0]
    return None

# --- 문서 텍스트 저장 및 로드 함수 (새로 추가) ---
def save_document_text(full_text: str):
    """
    업로드된 문서의 전체 텍스트를 데이터베이스에 저장합니다.
    항상 가장 최신 텍스트만 유지합니다 (기존 텍스트 삭제 후 새로 삽입).
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # 기존 문서 텍스트 삭제
        c.execute("DELETE FROM document_texts")
        # 새 문서 텍스트 삽입
        c.execute("INSERT INTO document_texts (full_text, timestamp) VALUES (?, ?)",
                  (full_text, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))\
        ;conn.commit()
        return True
    except Exception as e:
        print(f"오류: 문서 텍스트 저장 실패 - {e}")
        return False
    finally:
        conn.close()

def get_latest_document_text() -> str | None:
    """
    데이터베이스에 저장된 가장 최신 문서 텍스트를 가져옵니다.
    """
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT full_text FROM document_texts ORDER BY timestamp DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    if result:
        return result[0]
    return None

# --- 중간 요약문 저장 및 로드 함수 (새로 추가) ---
def save_intermediate_summary(summary_text: str, batch_id: str, level: int):
    """중간 요약 텍스트를 데이터베이스에 저장합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO intermediate_summaries (summary_text, batch_id, level, timestamp) VALUES (?, ?, ?, ?)",
                  (summary_text, batch_id, level, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return True
    except Exception as e:
        print(f"오류: 중간 요약 저장 실패 - {e}")
        return False
    finally:
        conn.close()

def get_intermediate_summaries(level: int, batch_id_prefix: str = "") -> list[str]:
    """특정 계층 및 배치 접두사에 해당하는 중간 요약문들을 가져옵니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if batch_id_prefix:
        c.execute("SELECT summary_text FROM intermediate_summaries WHERE level = ? AND batch_id LIKE ? ORDER BY id",
                  (level, f"{batch_id_prefix}%"))
    else:
        c.execute("SELECT summary_text FROM intermediate_summaries WHERE level = ? ORDER BY id")
    summaries = [row[0] for row in c.fetchall()]
    conn.close()
    return summaries

def clear_intermediate_summaries():
    """중간 요약 테이블의 모든 내용을 삭제합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM intermediate_summaries")
        conn.commit()
        print("중간 요약 테이블이 성공적으로 초기화되었습니다.")
        return True
    except Exception as e:
        print(f"오류: 중간 요약 테이블 초기화 실패 - {e}")
        return False
    finally:
        conn.close()
