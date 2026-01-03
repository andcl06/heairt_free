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
    주어진 프롬프트 메시지로 Gemini API를 호출하고 원본 응답을 반환합니다.
    필드명을 Google REST API 표준 규격인 CamelCase로 최종 교정했습니다.
    """
    if not api_key:
        return {"error": "Gemini API 키가 누락되었습니다."}

    # 모델명 경로 처리
    clean_model_name = model if model.startswith("models/") else f"models/{model}"
    gemini_api_endpoint = f"https://generativelanguage.googleapis.com/v1/{clean_model_name}:generateContent?key={api_key}"
    
    # [수정] REST API 규격은 CamelCase를 사용해야 합니다.
    payload = {
        "contents": [{
            "parts": [{"text": prompt_message}]
        }],
        "generationConfig": {
            "responseMimeType": "text/plain"
        }
    }

    # JSON 스키마가 있을 경우 설정 변경
    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(gemini_api_endpoint, headers=headers, json=payload, timeout=300)
        
        if response.status_code != 200:
            return {"error": f"API 오류 ({response.status_code}): {response.text}", "status_code": response.status_code}

        response_json = response.json()
        
        if "candidates" in response_json and len(response_json["candidates"]) > 0:
            candidate = response_json["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                text_part = candidate["content"]["parts"][0].get("text")
                if text_part:
                    if response_schema:
                        try:
                            if isinstance(text_part, str):
                                parsed_content = json.loads(text_part.strip())
                                return {"text": parsed_content, "raw_response": response_json}
                            return {"text": text_part, "raw_response": response_json}
                        except json.JSONDecodeError:
                            return {"error": f"JSON 파싱 실패: {text_part}"}
                    else:
                        return {"text": text_part.strip(), "raw_response": response_json}
        
        return {"error": "응답 데이터 구조가 예상과 다릅니다.", "raw_response": response_json}

    except Exception as e:
        return {"error": f"호출 예외 발생: {str(e)}"}

def retry_ai_call(prompt: str, api_key: str, response_schema=None, max_retries: int = 2, delay_seconds: int = 15) -> dict:
    for attempt in range(max_retries):
        response_dict = call_gemini_api_raw(prompt, api_key=api_key, response_schema=response_schema)

        if "error" not in response_dict:
            return response_dict
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            current_delay = delay_seconds * 2 if "429" in error_msg else delay_seconds
            
            if attempt < max_retries - 1:
                st.warning(f"🚨 AI 호출 실패 (시도 {attempt + 1}/{max_retries}): {error_msg}. {current_delay}초 후 재시도합니다.")
                time.sleep(current_delay)
            else:
                st.error(f"🚨 AI 호출 최종 실패: {error_msg}")
                return {"error": error_msg}
    return {"error": "최종 실패"}

def get_article_summary(title: str, link: str, date_str: str, summary_snippet: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    initial_prompt = (
        f"다음 뉴스를 핵심 내용 위주로 간결하게 요약해 주세요.\n\n"
        f"제목: {title}\n날짜: {date_str}\n미리보기: {summary_snippet}"
    )
    response_dict = retry_ai_call(initial_prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_seconds)
    return response_dict.get("text", "요약 실패")

def get_relevant_keywords(trending_keywords_data: list[dict], perspective: str, api_key: str) -> list[str]:
    prompt_keywords = [{"keyword": k['keyword'], "recent_freq": k['recent_freq']} for k in trending_keywords_data]
    prompt = (
        f"다음 키워드 목록 중 '{perspective}' 관점에서 유의미한 키워드 최대 5개를 골라 JSON 배열(['k1', 'k2'])로 반환하세요.\n"
        f"목록: {json.dumps(prompt_keywords, ensure_ascii=False)}"
    )
    response_schema = {
        "type": "array",
        "items": {"type": "string"}
    }
    response_dict = retry_ai_call(prompt, api_key=api_key, response_schema=response_schema)
    return response_dict.get("text", [])

def _summarize_text_batch(texts: list[str], api_key: str, batch_size: int = 3, level: int = 1, current_batch_prefix: str = "") -> list[str]:
    if not texts: return []
    summarized_batches = []
    current_batch_texts = []

    for i, text in enumerate(texts):
        current_batch_texts.append(text)
        if len(current_batch_texts) >= batch_size or i == len(texts) - 1:
            combined = "\n\n---\n\n".join(current_batch_texts)
            prompt = f"다음 내용들을 종합 요약하세요:\n{combined}"
            res = retry_ai_call(prompt, api_key=api_key)
            summary = clean_ai_response_text(res.get("text", "요약 실패"))
            summarized_batches.append(summary)
            database_manager.save_intermediate_summary(summary, f"{current_batch_prefix}L{level}_B{len(summarized_batches)}", level)
            current_batch_texts = []
            time.sleep(12) 

    if len(summarized_batches) > 1:
        return _summarize_text_batch(summarized_batches, api_key, batch_size, level + 1, current_batch_prefix)
    return summarized_batches

def get_overall_trend_summary(summarized_articles: list[dict], api_key: str) -> str:
    if not summarized_articles: return "내용 없음"
    initials = [f"제목: {a['제목']}\n요약: {a['내용']}" for a in summarized_articles]
    database_manager.clear_intermediate_summaries()
    final = _summarize_text_batch(initials, api_key, batch_size=3, level=1, current_batch_prefix=datetime.now().strftime('%H%M%S_'))
    return final[0] if final else "요약 실패"

def get_insurance_implications_from_ai(trend_summary_text: str, api_key: str) -> str:
    prompt = f"다음 트렌드 요약문을 보고 '자동차 보험' 산업에 미칠 영향을 분석하세요:\n{trend_summary_text}"
    res = retry_ai_call(prompt, api_key=api_key)
    return res.get("text", "분석 실패")

def format_text_with_markdown(text_to_format: str, api_key: str) -> str:
    prompt = f"다음 내용을 전문적인 마크다운 보고서로 재구성하세요. 본문만 출력하세요:\n{text_to_format}"
    res = retry_ai_call(prompt, api_key=api_key)
    return str(res.get("text", "포맷팅 실패"))

def clean_ai_response_text(text: Any) -> str:
    if not isinstance(text, str): text = str(text)
    cleaned = re.sub(r'```(?:json|text)?\s*([\s\S]*?)\s*```', r'\1', text)
    cleaned = re.sub(r'[#*_\-]+', '', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()