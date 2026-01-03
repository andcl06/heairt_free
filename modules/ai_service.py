# modules/ai_service.py 수정본

import json
import re
import time
from typing import List, Dict, Any
import streamlit as st
import requests  # 맨 위로 이동
from modules import database_manager
from datetime import datetime

def call_gemini_api_raw(prompt_message: str, api_key: str, response_schema=None, model: str = "gemini-1.5-flash") -> dict:
    """
    주어진 프롬프트 메시지로 Gemini API를 호출하고 원본 응답을 반환합니다.
    """
    if not api_key:
        return {"error": "Gemini API 키가 누락되었습니다."}

    # [수정] URL 구조 변경: v1beta 대신 v1 사용 및 경로 최적화
    gemini_api_endpoint = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt_message}]
        }],
        "generationConfig": {
            "responseMimeType": "text/plain",
        }
    }

    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        # 인코딩 문제 방지를 위해 json 파라미터 직접 사용
        response = requests.post(gemini_api_endpoint, headers=headers, json=payload, timeout=300)
        
        # 429(Quota) 에러 등에 대한 상세 메시지 처리를 위해 raise_for_status 전 체크
        if response.status_code != 200:
            return {"error": f"API 오류 ({response.status_code}): {response.text}"}

        response_json = response.json()
        
        # [수정] 'parts' 에러 방지를 위한 안전한 추출 로직
        if "candidates" in response_json and len(response_json["candidates"]) > 0:
            candidate = response_json["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                text_part = candidate["content"]["parts"][0].get("text")
                if text_part:
                    if response_schema:
                        try:
                            parsed_content = json.loads(text_part.strip())
                            return {"text": parsed_content, "raw_response": response_json}
                        except json.JSONDecodeError:
                            return {"error": f"JSON 디코딩 오류: {text_part}"}
                    else:
                        return {"text": text_part.strip(), "raw_response": response_json}
        
        return {"error": "유효한 응답 파트를 찾을 수 없습니다.", "raw_response": response_json}

    except Exception as e:
        return {"error": f"호출 중 예외 발생: {str(e)}"}

# --- 이하 함수들은 기존과 동일 (생략 가능하나 전체 구조 유지를 위해 유지) ---
def retry_ai_call(prompt: str, api_key: str, response_schema=None, max_retries: int = 2, delay_seconds: int = 15) -> dict:
    for attempt in range(max_retries):
        response_dict = call_gemini_api_raw(prompt, api_key=api_key, response_schema=response_schema)
        if "error" not in response_dict:
            return response_dict
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            if "429" in error_msg: # 쿼터 초과 시 더 오래 대기
                actual_delay = delay_seconds * 2
            else:
                actual_delay = delay_seconds
                
            if attempt < max_retries - 1:
                st.warning(f"🚨 AI 호출 실패 (시도 {attempt + 1}/{max_retries}): {error_msg}. {actual_delay}초 후 재시도합니다.")
                time.sleep(actual_delay)
            else:
                st.error(f"🚨 AI 호출 최종 실패: {error_msg}")
                return {"error": error_msg}
    return {"error": "최종 실패"}

# ... (나머지 get_article_summary, _summarize_text_batch 등 기존 코드 유지)