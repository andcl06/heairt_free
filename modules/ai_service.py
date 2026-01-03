# modules/ai_service.py

import json
import re
import time
from typing import List, Dict, Any
import streamlit as st
import requests
from modules import database_manager
from datetime import datetime

def call_gemini_api_raw(prompt_message: str, api_key: str, response_schema=None, model: str = "gemini-1.5-flash") -> dict:
    """
    Gemini API를 호출합니다. 400 에러를 방지하기 위해 가장 단순하고 표준적인 
    v1beta 엔드포인트와 페이로드 구조를 사용합니다.
    """
    if not api_key:
        return {"error": "Gemini API 키가 누락되었습니다."}

    # 다시 v1beta로 복귀 (최신 기능 호환성을 위해)
    clean_model_name = model if model.startswith("models/") else f"models/{model}"
    gemini_api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/{clean_model_name}:generateContent?key={api_key}"
    
    # [수정] 가장 안전한 형태의 페이로드. response_schema를 직접 넣지 않고 텍스트로 유도합니다.
    payload = {
        "contents": [{
            "parts": [{"text": prompt_message}]
        }]
    }

    # generation_config 에러를 피하기 위해 필드를 하나씩 검증하며 추가
    generation_config = {}
    if response_schema:
        # API가 response_mime_type을 거부하는 경우가 많으므로 텍스트로 받고 파싱하는 전략 사용
        prompt_message += "\n\n반드시 다른 설명 없이 JSON 형식으로만 답변해 주세요."
        # 필요시 아래 주석을 해제하되, 현재는 400 에러 방지를 위해 최소화함
        # generation_config["response_mime_type"] = "application/json"
    
    if generation_config:
        payload["generation_config"] = generation_config
    
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(gemini_api_endpoint, headers=headers, json=payload, timeout=300)
        
        if response.status_code != 200:
            return {"error": f"API 오류 ({response.status_code}): {response.text}"}

        response_json = response.json()
        
        if "candidates" in response_json and len(response_json["candidates"]) > 0:
            candidate = response_json["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                text_part = candidate["content"]["parts"][0].get("text")
                if text_part:
                    # 응답이 JSON인 경우 처리
                    if response_schema:
                        try:
                            # 마크다운 코드 블록(```json) 제거 후 파싱
                            json_str = re.sub(r'```(?:json)?\s*([\s\S]*?)\s*```', r'\1', text_part.strip())
                            parsed_content = json.loads(json_str)
                            return {"text": parsed_content, "raw_response": response_json}
                        except:
                            return {"text": text_part, "raw_response": response_json}
                    return {"text": text_part.strip(), "raw_response": response_json}
        
        return {"error": "응답 데이터 구조 오류", "raw_response": response_json}
    except Exception as e:
        return {"error": f"호출 예외: {str(e)}"}

def retry_ai_call(prompt: str, api_key: str, response_schema=None, max_retries: int = 2, delay_seconds: int = 15) -> dict:
    for attempt in range(max_retries):
        response_dict = call_gemini_api_raw(prompt, api_key=api_key, response_schema=response_schema)
        if "error" not in response_dict:
            return response_dict
        
        error_msg = response_dict.get("error", "")
        # 429 에러(Quota) 발생 시 대기 시간을 대폭 늘림
        wait_time = delay_seconds * 3 if "429" in error_msg else delay_seconds
        
        if attempt < max_retries - 1:
            st.warning(f"🚨 AI 시도 {attempt+1}/{max_retries} 실패. {wait_time}초 후 재시도...")
            time.sleep(wait_time)
        else:
            return response_dict
    return {"error": "최종 실패"}

def get_article_summary(title: str, link: str, date_str: str, summary_snippet: str, api_key: str) -> str:
    prompt = f"뉴스 요약: 제목={title}, 날짜={date_str}, 내용={summary_snippet}. 핵심만 요약해."
    res = retry_ai_call(prompt, api_key)
    return res.get("text", "요약 실패")

def get_relevant_keywords(trending_keywords_data: list[dict], perspective: str, api_key: str) -> list[str]:
    prompt = f"다음 키워드 중 '{perspective}' 관련 핵심 5개를 JSON 배열로만 써라: {json.dumps(trending_keywords_data, ensure_ascii=False)}"
    # schema를 전달하지만 내부적으로는 텍스트 파싱을 유도함
    res = retry_ai_call(prompt, api_key, response_schema=True)
    val = res.get("text", [])
    return val if isinstance(val, list) else []

def _summarize_text_batch(texts: list[str], api_key: str, batch_size: int = 3, level: int = 1, current_batch_prefix: str = "") -> list[str]:
    if not texts: return []
    summarized = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        combined = "\n".join(batch)
        prompt = f"다음 내용들을 하나로 종합 요약해:\n{combined}"
        res = retry_ai_call(prompt, api_key)
        summary = clean_ai_response_text(res.get("text", "요약 실패"))
        summarized.append(summary)
        database_manager.save_intermediate_summary(summary, f"{current_batch_prefix}L{level}_B{i}", level)
        time.sleep(13) # 쿼터 보호를 위해 13초 대기
    
    if len(summarized) > 1:
        return _summarize_text_batch(summarized, api_key, batch_size, level + 1, current_batch_prefix)
    return summarized

def get_overall_trend_summary(summarized_articles: list[dict], api_key: str) -> str:
    if not summarized_articles: return "내용 없음"
    initials = [f"제목: {a['제목']}\n요약: {a['내용']}" for a in summarized_articles]
    database_manager.clear_intermediate_summaries()
    final = _summarize_text_batch(initials, api_key, current_batch_prefix=datetime.now().strftime('%H%M%S_'))
    return final[0] if final else "요약 실패"

def get_insurance_implications_from_ai(trend_summary_text: str, api_key: str) -> str:
    prompt = f"이 트렌드가 자동차 보험에 미칠 영향 분석:\n{trend_summary_text}"
    res = retry_ai_call(prompt, api_key)
    return res.get("text", "분석 실패")

def format_text_with_markdown(text_to_format: str, api_key: str) -> str:
    prompt = f"마크다운 보고서로 예쁘게 꾸며줘. 본문만 출력:\n{text_to_format}"
    res = retry_ai_call(prompt, api_key)
    return str(res.get("text", "실패"))

def clean_ai_response_text(text: Any) -> str:
    if not isinstance(text, str): text = str(text)
    cleaned = re.sub(r'```(?:json|text)?\s*([\s\S]*?)\s*```', r'\1', text)
    cleaned = re.sub(r'[#*_\-]+', '', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()