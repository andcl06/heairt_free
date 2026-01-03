# modules/ai_service.py

import json
import re
import time
from typing import List, Dict, Any
import streamlit as st
import requests  # HTTP 호출을 위해 상단에 배치
from modules import database_manager
from datetime import datetime

def call_gemini_api_raw(prompt_message: str, api_key: str, response_schema=None, model: str = "gemini-1.5-flash") -> dict:
    """
    주어진 프롬프트 메시지로 Gemini API를 호출하고 원본 응답을 반환합니다.
    v1beta 대신 안정적인 v1 엔드포인트를 사용하며, 응답 파싱 시 안전 검사를 수행합니다.
    """
    if not api_key:
        return {"error": "Gemini API 키가 누락되었습니다."}

    # [수정] 모델 경로 최적화 및 v1 정식 버전 엔드포인트 사용
    # 모델명 앞에 'models/'가 붙지 않은 경우를 대비해 처리
    clean_model_name = model if model.startswith("models/") else f"models/{model}"
    gemini_api_endpoint = f"https://generativelanguage.googleapis.com/v1/{clean_model_name}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "role": "user",
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
        "Content-Type": "application/json; charset=utf-8"
    }

    try:
        # requests를 사용하여 API 호출 (timeout 설정 포함)
        response = requests.post(gemini_api_endpoint, headers=headers, json=payload, timeout=300)
        
        # 429(Too Many Requests) 또는 404 에러 상세 처리
        if response.status_code != 200:
            return {"error": f"API 오류 ({response.status_code}): {response.text}", "status_code": response.status_code}

        response_json = response.json()
        
        # [수정] 'parts' 에러 방지를 위한 단계별 데이터 존재 확인 (Safety check)
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
        
        return {"error": "유효한 AI 응답 텍스트를 찾을 수 없습니다. (Safety filter 등에 의해 차단되었을 수 있음)", "raw_response": response_json}

    except requests.exceptions.RequestException as e:
        return {"error": f"네트워크 오류 발생: {str(e)}"}
    except Exception as e:
        return {"error": f"알 수 없는 오류 발생: {str(e)}"}

def retry_ai_call(prompt: str, api_key: str, response_schema=None, max_retries: int = 2, delay_seconds: int = 15) -> dict:
    """
    API 호출 실패 시 재시도 로직을 수행합니다. 429 에러 발생 시 대기 시간을 자동으로 늘립니다.
    """
    for attempt in range(max_retries):
        # [수정] 1.5-flash 모델이 무료 쿼터가 넉넉하므로 기본값으로 설정
        response_dict = call_gemini_api_raw(prompt, api_key=api_key, response_schema=response_schema, model="gemini-1.5-flash")

        if "error" not in response_dict:
            return response_dict
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            
            # [추가] 429 Too Many Requests 에러인 경우 대기 시간을 2배로 늘림
            current_delay = delay_seconds * 2 if "429" in error_msg else delay_seconds
            
            if attempt < max_retries - 1:
                st.warning(f"🚨 AI 호출 실패 (시도 {attempt + 1}/{max_retries}): {error_msg}. {current_delay}초 후 재시도합니다.")
                time.sleep(current_delay)
            else:
                st.error(f"🚨 AI 호출 최종 실패: {error_msg}")
                return {"error": f"AI 호출 최종 실패: {error_msg}"}
    return {"error": "최종 실패"}

def get_article_summary(title: str, link: str, date_str: str, summary_snippet: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    initial_prompt = (
        f"다음은 뉴스 기사에 대한 정보입니다. 이 정보를 바탕으로 뉴스 기사 내용을 요약해 주세요.\n"
        f"**제공된 링크에 접근할 수 없거나 기사를 찾을 수 없는 경우, 아래 제공된 제목, 날짜, 미리보기 요약만을 사용하여 기사 내용을 파악하고 요약해 주세요.**\n"
        f"광고나 불필요한 정보 없이 핵심 내용만 간결하게 제공해 주세요.\n\n"
        f"제목: {title}\n"
        f"링크: {link}\n"
        f"날짜: {date_str}\n"
        f"미리보기 요약: {summary_snippet}"
    )
    response_dict = retry_ai_call(initial_prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_seconds)
    return response_dict.get("text", response_dict.get("error", "요약 실패"))

def get_relevant_keywords(trending_keywords_data: list[dict], perspective: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> list[str]:
    prompt_keywords = [{"keyword": k['keyword'], "recent_freq": k['recent_freq']} for k in trending_keywords_data]
    prompt = (
        f"다음은 뉴스 기사에서 식별된 트렌드 키워드 목록입니다. 이 키워드들을 '{perspective}'의 관점에서 "
        f"가장 유의미하다고 판단되는 순서대로 최대 5개까지 골라 JSON 배열 형태로 반환해 주세요.\n\n"
        f"키워드 목록: {json.dumps(prompt_keywords, ensure_ascii=False)}"
    )
    response_schema = {"type": "ARRAY", "items": {"type": "STRING"}}
    response_dict = retry_ai_call(prompt, api_key=api_key, response_schema=response_schema, max_retries=max_attempts, delay_seconds=delay_seconds)
    return response_dict["text"] if "text" in response_dict and isinstance(response_dict["text"], list) else []

def _summarize_text_batch(texts: list[str], api_key: str, batch_size: int = 3, level: int = 1, current_batch_prefix: str = "") -> list[str]:
    if not texts: return []
    MAX_INPUT_LENGTH = 10000 
    summarized_batches = []
    current_batch_texts, current_batch_length = [], 0

    for i, text in enumerate(texts):
        if current_batch_length + len(text) > MAX_INPUT_LENGTH or len(current_batch_texts) >= batch_size:
            if current_batch_texts:
                combined_text = "\n\n---\n\n".join(current_batch_texts)
                prompt = f"다음 텍스트들을 종합하여 간결하게 요약해 주세요. 주요 내용만 포함해 주세요.\n\n텍스트:\n{combined_text}"
                response_dict = retry_ai_call(prompt, api_key=api_key)
                summary = clean_ai_response_text(response_dict.get("text", "배치 요약 실패"))
                summarized_batches.append(summary)
                database_manager.save_intermediate_summary(summary, f"{current_batch_prefix}L{level}_B{len(summarized_batches)}", level)
                current_batch_texts, current_batch_length = [], 0
                time.sleep(5) # [추가] 쿼터 보호를 위한 딜레이 추가
        current_batch_texts.append(text)
        current_batch_length += len(text)

    if current_batch_texts:
        combined_text = "\n\n---\n\n".join(current_batch_texts)
        prompt = f"다음 텍스트들을 종합하여 간결하게 요약해 주세요.\n\n텍스트:\n{combined_text}"
        response_dict = retry_ai_call(prompt, api_key=api_key)
        summary = clean_ai_response_text(response_dict.get("text", "배치 요약 실패"))
        summarized_batches.append(summary)
        database_manager.save_intermediate_summary(summary, f"{current_batch_prefix}L{level}_B{len(summarized_batches)}", level)

    if len(summarized_batches) > 1:
        st.info(f"⏳ {level}차 요약 완료. 다음 계층 요약 시작...")
        return _summarize_text_batch(summarized_batches, api_key, batch_size, level + 1, current_batch_prefix)
    return summarized_batches

def get_overall_trend_summary(summarized_articles: list[dict], api_key: str) -> str:
    if not summarized_articles: return "요약할 기사가 없습니다."
    initial_summaries = [f"제목: {art['제목']}\n요약: {art['내용']}" for art in summarized_articles]
    database_manager.clear_intermediate_summaries()
    final_list = _summarize_text_batch(initial_summaries, api_key, batch_size=3, level=1, current_batch_prefix=datetime.now().strftime('%H%M%S_'))
    return final_list[0] if final_list else "요약 실패"

def get_insurance_implications_from_ai(trend_summary_text: str, api_key: str) -> str:
    prompt = f"다음 뉴스 트렌드 요약문을 바탕으로 '자동차 보험 산업'에 미칠 영향을 간결하게 분석해 주세요.\n\n내용:\n{trend_summary_text}"
    response_dict = retry_ai_call(prompt, api_key=api_key)
    return response_dict.get("text", "분석 실패")

def format_text_with_markdown(text_to_format: str, api_key: str) -> str:
    prompt = f"다음 내용을 전문적인 마크다운 형식의 보고서로 재구성해 주세요. 서두 문구 없이 본문만 출력하세요.\n\n[내용]\n{text_to_format}"
    response_dict = retry_ai_call(prompt, api_key=api_key)
    return clean_prettified_report_text(response_dict.get("text", "포맷팅 실패"))

def clean_prettified_report_text(text: str) -> str:
    cleaned = re.sub(r'^(다음은|요청하신|보고서).*?\n', '', text, flags=re.IGNORECASE)
    return cleaned.strip()

def clean_ai_response_text(text: str) -> str:
    cleaned = re.sub(r'```(?:json|text)?\s*([\s\S]*?)\s*```', r'\1', text)
    cleaned = re.sub(r'[#*_\-]+', '', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()