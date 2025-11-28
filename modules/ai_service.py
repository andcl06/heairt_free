# modules/ai_service.py

import json
import re
import time
from typing import List, Dict, Any
import streamlit as st # Streamlit의 st.error, st.warning 등을 사용하기 위해 임시로 import.
                        # 실제 프로덕션에서는 이 로깅 부분을 다른 방식으로 처리하는 것이 좋습니다.
from modules import database_manager # database_manager 모듈 임포트
from datetime import datetime # datetime 모듈 임포트 (중간 요약 배치 ID 생성에 사용)

def call_gemini_api_raw(prompt_message: str, api_key: str, response_schema=None, model: str = "gemini-2.5-flash-preview-05-20") -> dict:
    """
    주어진 프롬프트 메시지로 Gemini API를 호출하고 원본 응답을 반환합니다.
    response_schema: JSON 응답을 위한 스키마 (선택 사항)
    """
    # 환경 변수로 API 키를 제공하는 것이 더 안전한 방법입니다.
    if not api_key:
        return {"error": "Gemini API 키가 누락되었습니다."}

    gemini_api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    chat_history = []
    chat_history.append({ "role": "user", "parts": [{ "text": prompt_message }] })

    payload = {
        "contents": chat_history,
        "generationConfig": {
            "responseMimeType": "text/plain",
        }
    }

    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema
    
    # Python 딕셔너리를 JSON 문자열로 변환하고, non-ASCII 문자를 이스케이프하지 않도록 설정
    json_payload_str = json.dumps(payload, ensure_ascii=False)
    # JSON 문자열을 UTF-8 바이트로 인코딩
    encoded_payload = json_payload_str.encode('utf-8')

    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }

    try:
        # requests 라이브러리 대신 fetch API를 사용하도록 변경
        # Canvas 환경에서 제공하는 fetch API를 사용하므로 requests를 import 할 필요가 없습니다.
        # 실제 Streamlit 환경에서는 requests.post를 사용해야 합니다.
        import requests
        response = requests.post(gemini_api_endpoint, headers=headers, data=encoded_payload, timeout=300)
        response.raise_for_status()
        response_json = response.json()
        
        if response_json.get("candidates") and response_json["candidates"][0].get("content"):
            text_part = response_json["candidates"][0]["content"]["parts"][0].get("text")
            if text_part:
                if response_schema:
                    try:
                        parsed_content = json.loads(text_part.strip())
                        return {"text": parsed_content, "raw_response": response_json}
                    except json.JSONDecodeError:
                        return {"error": f"Gemini API 응답 JSON 디코딩 오류: {text_part}"}
                else:
                    return {"text": text_part.strip(), "raw_response": response_json}
        
        # 유효한 응답이 없는 경우
        return {"error": "Gemini API 응답 형식이 올바라지 않거나 내용이 없습니다.", "raw_response": response_json}

    except requests.exceptions.RequestException as e:
        error_message = f"Gemini API 호출 오류 발생 (network/timeout/HTTP): {e}"
        if e.response is not None:
            error_message += f" Response content: {e.response.text}"
        return {"error": error_message}
    except Exception as e:
        return {"error": f"알 수 없는 오류 발생: {e}"}

def retry_ai_call(prompt: str, api_key: str, response_schema=None, max_retries: int = 2, delay_seconds: int = 15) -> dict:
    """
    Gemini API 호출에 대한 재시도 로직을 포함한 래퍼 함수.
    call_gemini_api_raw를 호출하고 실패 시 재시도합니다.
    """
    for attempt in range(max_retries):
        response_dict = call_gemini_api_raw(prompt, api_key=api_key, response_schema=response_schema)

        if "error" not in response_dict:
            return response_dict
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            if attempt < max_retries - 1:
                st.warning(f"🚨 AI 호출 실패 (시도 {attempt + 1}/{max_retries}): {error_msg}. {delay_seconds}초 후 재시도합니다.")
                time.sleep(delay_seconds)
            else:
                st.error(f"🚨 AI 호출 최종 실패: {error_msg}. 더 이상 재시도하지 않습니다.")
                return {"error": f"AI 호출 최종 실패: {error_msg}"}
    return {"error": "AI 응답을 가져오는 데 최종 실패했습니다. 나중에 다시 시도해주세요."}


def get_article_summary(title: str, link: str, date_str: str, summary_snippet: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    Gemini AI를 호출하여 제공된 제목, 링크, 날짜, 미리보기 요약을 바탕으로
    뉴스 기사 내용을 요약합니다. (단일 호출)
    링크 접근이 불가능할 경우에도 제공된 정보만으로 요약을 시도합니다.
    """
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
    if "text" in response_dict:
        return response_dict["text"]
    else:
        return response_dict.get("error", "알 수 없는 오류")


def get_relevant_keywords(trending_keywords_data: list[dict], perspective: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> list[str]:
    """
    Gemini AI를 호출하여 트렌드 키워드 중 특정 관점에서 유의미한 키워드를 선별합니다.
    반환 값: ['keyword1', 'keyword2', ...]
    """
    prompt_keywords = [{"keyword": k['keyword'], "recent_freq": k['recent_freq']} for k in trending_keywords_data]

    prompt = (
        f"다음은 뉴스 기사에서 식별된 트렌드 키워드 목록입니다. 이 키워드들을 '{perspective}'의 관점에서 "
        f"가장 유의미하다고 판단되는 순서대로 최대 5개까지 골라 JSON 배열 형태로 반환해 주세요. "
        f"다른 설명 없이 JSON 배열만 반환해야 합니다. 각 키워드는 문자열이어야 합니다.\n\n"
        f"키워드 목록: {json.dumps(prompt_keywords, ensure_ascii=False)}"
    )

    response_schema = {
        "type": "ARRAY",
        "items": {"type": "STRING"}
    }

    response_dict = retry_ai_call(prompt, api_key=api_key, response_schema=response_schema, max_retries=max_attempts, delay_seconds=delay_seconds)
    if "text" in response_dict and isinstance(response_dict["text"], list):
        return response_dict["text"]
    else:
        return [] # 오류 발생 시 빈 리스트 반환

def _summarize_text_batch(texts: list[str], api_key: str, batch_size: int = 3, level: int = 1, current_batch_prefix: str = "") -> list[str]:
    """
    텍스트 리스트를 배치 단위로 나누어 요약하고, 그 요약문들을 반환합니다.
    필요시 재귀적으로 요약을 수행하여 최종적으로 하나의 요약문 리스트를 만듭니다.
    """
    if not texts:
        return []

    # 텍스트를 합쳐서 AI에 전달할 최대 길이 (이 함수 내에서만 적용되는 임시 제약)
    # 너무 길면 AI가 처리하지 못하므로 적절히 조절
    MAX_INPUT_LENGTH_FOR_BATCH_SUMMARIZATION = 10000 # 한 번의 AI 호출에 들어갈 텍스트의 최대 길이

    summarized_batches = []
    batch_counter = 0

    # 텍스트를 배치 크기 또는 최대 입력 길이에 맞춰 그룹화
    current_batch_texts = []
    current_batch_length = 0

    for i, text in enumerate(texts):
        # 현재 텍스트를 추가했을 때 배치 길이가 너무 길어지면 새 배치 시작
        if current_batch_length + len(text) > MAX_INPUT_LENGTH_FOR_BATCH_SUMMARIZATION or len(current_batch_texts) >= batch_size:
            if current_batch_texts:
                batch_counter += 1
                batch_id = f"{current_batch_prefix}level{level}_batch{batch_counter}"
                combined_batch_text = "\n\n---\n\n".join(current_batch_texts)

                prompt = f"다음 텍스트들을 종합하여 간결하게 요약해 주세요. 주요 내용만 포함해 주세요.\n\n텍스트:\n{combined_batch_text}"
                response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=2, delay_seconds=10)
                batch_summary = clean_ai_response_text(response_dict.get("text", f"배치 요약 실패 (레벨 {level}, 배치 {batch_counter})"))
                summarized_batches.append(batch_summary)
                database_manager.save_intermediate_summary(batch_summary, batch_id, level) # 중간 요약 저장

                current_batch_texts = []
                current_batch_length = 0
                time.sleep(1) # AI 호출 간 딜레이

        current_batch_texts.append(text)
        current_batch_length += len(text)

    # 마지막 남은 배치 처리
    if current_batch_texts:
        batch_counter += 1
        batch_id = f"{current_batch_prefix}level{level}_batch{batch_counter}"
        combined_batch_text = "\n\n---\n\n".join(current_batch_texts)
        prompt = f"다음 텍스트들을 종합하여 간결하게 요약해 주세요. 주요 내용만 포함해 주세요.\n\n텍스트:\n{combined_batch_text}"
        response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=2, delay_seconds=10)
        batch_summary = clean_ai_response_text(response_dict.get("text", f"배치 요약 실패 (레벨 {level}, 배치 {batch_counter})"))
        summarized_batches.append(batch_summary)
        database_manager.save_intermediate_summary(batch_summary, batch_id, level) # 중간 요약 저장

    # 요약된 배치가 여전히 많으면 다음 계층으로 재귀 호출
    # 최종 요약은 하나의 텍스트로 나와야 하므로, 1개 초과 시 재귀
    if len(summarized_batches) > 1:
        st.info(f"⏳ {level}차 요약 완료. {len(summarized_batches)}개의 요약문이 생성되었습니다. 다음 계층 요약 시작...")
        return _summarize_text_batch(summarized_batches, api_key, batch_size, level + 1, current_batch_prefix)
    else:
        return summarized_batches # 최종 요약문 리스트 (1개)

def get_overall_trend_summary(summarized_articles: list[dict], api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    AI가 요약된 기사들을 바탕으로 전반적인 뉴스 트렌드를 요약합니다.
    계층적 요약 방식을 사용합니다.
    """
    if not summarized_articles:
        return "요약된 기사가 없어 뉴스 트렌드를 요약할 수 없습니다."

    # 모든 개별 요약문 텍스트만 추출
    initial_summaries = [
        f"제목: {art['제목']}\n날짜: {art['날짜']}\n요약: {art['내용']}"
        for art in summarized_articles
    ]

    # 임시 DB 테이블 초기화 (새로운 전체 요약 시작 시)
    database_manager.clear_intermediate_summaries()

    st.info("⏳ 뉴스 트렌드 계층적 요약 시작...")
    # 계층적 요약 실행 (배치 크기 3개로 시작)
    final_summaries_list = _summarize_text_batch(initial_summaries, api_key, batch_size=3, level=1, current_batch_prefix=datetime.now().strftime('%Y%m%d%H%M%S_'))

    # 최종 요약문이 하나로 나와야 함
    if final_summaries_list and len(final_summaries_list) == 1:
        final_trend_summary = final_summaries_list[0]
        st.success("✅ 뉴스 트렌드 계층적 요약 완료!")
        return final_trend_summary
    else:
        return "뉴스 트렌드 요약에 실패했습니다. 최종 요약문이 생성되지 않았습니다."


def get_insurance_implications_from_ai(trend_summary_text: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    AI가 요약된 트렌드 요약문을 바탕으로 자동차 보험 산업에 미칠 영향을 요약합니다.
    """
    if not trend_summary_text:
        return "트렌드 요약문이 없어 자동차 보험 산업 관련 정보를 도출할 수 없습니다."

    # 프롬프트 변경: 트렌드 요약문을 바탕으로 자동차 보험 산업에 미칠 영향 추론
    prompt = (
        f"다음은 최근 뉴스 트렌드를 요약한 내용입니다.\n"
        f"이 트렌드 요약문을 바탕으로 '자동차 보험 산업'에 미칠 수 있는 영향에 대해 간결하게 요약해 주세요.\n" # <-- 추론 요청
        f"한국어로 요약 내용을 제공해 주세요.\n\n"
        f"뉴스 트렌드 요약문:\n{trend_summary_text}"
    )

    response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_seconds)
    if "text" in response_dict:
        return response_dict["text"]
    else:
        return response_dict.get("error", "알 수 없는 오류")

def clean_prettified_report_text(text: str) -> str:
    """
    AI가 포맷한 보고서 텍스트에서 불필요한 AI 서두/맺음말 문구만 제거하고,
    마크다운 포맷팅(헤더, 목록, 줄바꿈)은 최대한 유지합니다.
    """
    cleaned_text = text

    # AI가 자주 사용하는 서두/맺음말 문구 제거 (정규표현식으로 유연하게 매칭)
    patterns_to_remove = [
        r'다음은 뉴스 트렌드 분석 및 보험 상품 개발 인사이트에 대한 보고서 초안을 바탕으로 재구성된 전문적인 보고서입니다[.:\s]*',
        r'다음은 요청하신 지침에 따라 재구성된 보고서입니다[.:\s]*',
        r'다음은 재구성된 보고서입니다[.:\s]*',
        r'보고서:\s*',
        r'보고서 내용:\s*',
        r'\[보고서\]:\s*',
        r'\[결과\]:\s*',
        r'이상입니다[.:\s]*',
        r'위 보고서는 제공된 정보를 바탕으로 재구성되었습니다[.:\s]*',
        r'이 보고서가 트렌드 분석 및 보험 상품 개발에 도움이 되기를 바랍니다[.:\s]*',
        r'이 보고서가 귀사의 비즈니스에 도움이 되기를 바랍니다[.:\s]*',
        r'이 보고서는 제공된 초안을 바탕으로 작성되었습니다[.:\s]*',
        r'다음은 제공된 텍스트를 바탕으로 재구성된 뉴스 트렌드 요약입니다[.:\s]*', # 추가된 패턴
        r'다음은 제공된 텍스트를 바탕으로 재구성된 자동차 보험 산업 관련 정보입니다[.:\s]*', # 추가된 패턴
        r'뉴스 트렌드 요약:\s*', # 추가된 패턴
        r'자동차 보험 산업 관련 주요 사실 및 법적 책임:\s*' # 추가된 패턴
    ]
    for pattern in patterns_to_remove:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)

    # 여러 개의 공백을 하나로 대체 (줄바꿈은 유지)
    cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)
    
    # 문단 시작 부분의 불필요한 공백 제거 (줄바꿈은 유지)
    cleaned_text = re.sub(r'^\s+', '', cleaned_text, flags=re.MULTILINE)

    return cleaned_text.strip()


def format_text_with_markdown(text_to_format: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    Gemini AI를 호출하여 주어진 텍스트를 전문적이고 가독성 높은 마크다운 형식으로 포맷팅합니다.
    """
    if not text_to_format:
        return "포맷팅할 내용이 없습니다."

    prompt = (
        f"다음 텍스트를 전문적이고 가독성 높은 마크다운 형식으로 재구성해 주세요.\n"
        f"텍스트 파일로 저장했을 때 줄바꿈과 들여쓰기가 명확하게 보이도록 마크다운 문법을 활용하여 구조화해 주세요.\n"
        f"핵심 내용은 강조(예: 볼드체)하거나 목록 형태로 정리하여 시각적으로 돋보이게 해주세요.\n"
        f"문단 간의 간격을 적절히 조절하여 가독성을 높여 주세요. 각 문단은 최소 한 줄 이상 비워주세요.\n"
        f"불필요한 반복이나 비문은 수정하고, 전문적인 보고서 톤앤매너를 유지해 주세요.\n"
        f"모든 내용은 한국어로 작성해 주세요.\n"
        f"**중요: 응답은 오직 재구성된 내용만 포함해야 합니다. 다른 설명이나 서두 문구는 절대 포함하지 마세요.**\n\n"
        f"[원본 텍스트]\n"
        f"{text_to_format}"
    )

    response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_seconds)
    if "text" in response_dict:
        # 새로운 클리닝 함수를 사용하여 AI가 포맷한 보고서 텍스트를 정리
        return clean_prettified_report_text(response_dict["text"])
    else:
        return response_dict.get("error", "AI를 통한 보고서 포맷팅 실패.")

def clean_ai_response_text(text: str) -> str:
    """
    AI 응답 텍스트에서 불필요한 마크다운 기호, 여러 줄바꿈,
    그리고 AI가 자주 사용하는 서두 문구들을 제거하여 평탄화합니다.
    이 함수는 주로 요약이나 QA 답변 등 일반 텍스트 출력을 위해 사용됩니다.
    """
    # 1. 마크다운 코드 블록 제거 (예: ```json ... ```)
    cleaned_text = re.sub(r'```(?:json|text)?\s*([\s\S]*?)\s*```', r'\1', text, flags=re.IGNORECASE)

    # 2. 마크다운 헤더 기호 제거 (예: #, ##, ### 등) - 줄 시작에 관계없이 모든 # 제거
    #    이전 버전에서 #+ 였으나, 이제는 #만 제거하고 +는 리스트 기호로 따로 처리
    cleaned_text = re.sub(r'#+', '', cleaned_text)

    # 3. 마크다운 볼드체/이탤릭체 기호 제거 (예: **, __, *, _) - 텍스트는 남기고 기호만 제거
    cleaned_text = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned_text) # **text** -> text
    cleaned_text = re.sub(r'__(.*?)__', r'\1', cleaned_text) # __text__ -> text
    cleaned_text = re.sub(r'\*(.*?)\*', r'\1', cleaned_text) # *text* -> text
    cleaned_text = re.sub(r'_(.*?)_', r'\1', cleaned_text) # _text_ -> text

    # 4. 마크다운 리스트 기호 제거 (예: -, +) - 줄 시작에 관계없이 제거
    #    \s*는 공백을 의미하며, 리스트 기호 뒤에 공백이 있을 수 있으므로 포함
    cleaned_text = re.sub(r'^\s*[-+]\s*', '', cleaned_text, flags=re.MULTILINE)

    # 5. 번호가 매겨진 목록 마커 제거 (예: "1.", "2.", "3.") - 줄 시작에 관계없이 제거
    cleaned_text = re.sub(r'^\s*\d+\.\s*', '', cleaned_text, flags=re.MULTILINE)

    # 6. AI가 자주 사용하는 서두 문구 제거 (정규표현식으로 유연하게 매칭)
    patterns_to_remove = [
        r'제공해주신\s*URL의\s*뉴스\s*기사\s*내용을\s*요약해드리겠습니다[.:\s]*',
        r'주요\s*내용[.:\s]*',
        r'제공해주신\s*텍스트를\s*요약\s*하겠\s*습니다[.:\s]*\s*요약[.:\s]*',
        r'요약해\s*드리겠습니다[.:\s]*\s*주요\s*내용\s*요약[.:\s]*',
        r'다음\s*텍스트의\s*요약입니다[.:\s]*',
        r'주요\s*내용을\s*요약\s*하면\s*다음과\s*같습니다[.:\s]*',
        r'핵심\s*내용은\s*다음과\s*같습니다[.:\s]*',
        r'요약하자면[.:\s]*',
        r'주요\s*요약[.:\s]*',
        r'텍스트를\s*요약하면\s*다음과\s*같습니다[.:\s]*',
        r'제공된\s*텍스트에\s*대한\s*요약입니다[.:\s]*',
        r'다음은\s*ai가\s*내용을\s*요약한\s*것입니다[.:\s]*',
        r'먼저\s*최신\s*정보가\s*필요합니다[.:\s]*\s*현재\s*자율주행차\s*기술과\s*관련된\s*최신\s*트렌드를\s*확인해보겠습니다[.:\s]*',
        r'ai\s*답변[.:\s]*',
        r'ai\s*분석[.:\s]*',
        r'다음은\s*요청하신\s*링크의\s*본문\s*내용입니다[.:\s]*',
        r'다음은\s*제공된\s*뉴스\s*기사의\s*핵심\s*내용입니다[.:\s]*',
        r'뉴스\s*기사\s*주요\s*내용\s*요약[.:\s]*',
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*제공해주신\s*URL에서\s*뉴스\s*기사의\s*주요\s*내용을\s*추출하겠습니다[.:\s]*',
        r'검색을\s*진행할\s*URL을\s*찾았습니다[.:\s]*\s*\(1/3\)\s*해당\s*링크에서\s*뉴스\s*기사의\s*핵심\s*내용을\s*추출하겠습니다[.:\s]*',
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*제공해주신\s*링크에서\s*기사\s*내용을\s*추출하겠습니다[.:\s]*',
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*해당\s*URL에서\s*뉴스\s*기사의\s*주요\s*내용을\s*추출하겠습니다[.:\s]*',
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*URL을\s*검색하여\s*기사\s*내용을\s*확인하겠습니다[.:\s]*\s*검색\s*결과를\s*바탕으로\s*다음과\s*같이\s*기사의\s*핵심\s*내용만\s*추출했습니다[.:\s]*',
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*해당\s*URL에서\s*기사\s*내용을\s*확인하겠습니다[.:\s]*\s*기사의\s*주요\s*내용을\s*추출했습니다[.:\s]*',
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*웹사이트의\s*내용을\s*확인하겠습니다[.:\s]*\s*기사의\s*주요\s*내용을\s*광고나\s*불필요한\s*정보\s*없이\s*추출해\s*드리겠습니다[.:\s]*',
        r'이상입니다[.:\s]*',
        r'이상입니다[.:\s]*\s*광고나\s*불필요한\s*정보는\s*제외하고\s*주요\s*내용만\s*추출했습니다[.:\s]*',
        r'이것이\s*제공해주신\s*YTN\s*뉴스\s*링크에서\s*추출한\s*핵심\s*기사\s*내용입니다[.:\s]*\s*광고나\s*불필요한\s*정보는\s*제외하고\s*기사의\s*주요\s*내용만\s*추출했습니다[.:\s]*',
        r'위\s*내용은\s*제공해주신\s*URL에서\s*추출한\s*기사의\s*핵심\s*내용입니다[.:\s]*\s*광고나\s*불필요한\s*정보를\s*제거하고\s*주요\s*내용만\s*정리했습니다[.:\s]*',
        r'AI\s*모델은\s*다음과\s*같이\s*뉴스\s*트렌드를\s*요약합니다[.:\s]*', # Gemini 관련 추가
        r'뉴스\s*트렌드\s*요약:\s*', # Gemini 관련 추가
        r'AI\s*모델은\s*다음과\s*같이\s*자동차\s*보험\s*산업\s*관련\s*주요\s*사실\s*및\s*법적\s*책임을\s*분석합니다[.:\s]*', # Gemini 관련 추가
        r'자동차\s*보험\s*산업\s*관련\s*주요\s*사실\s*및\s*법적\s*책임:\s*', # Gemini 관련 추가
    ]
    for pattern in patterns_to_remove:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)

    # 7. 줄바꿈 및 공백 정규화
    cleaned_text = re.sub(r'\n{2,}', '\n\n', cleaned_text)
    cleaned_text = re.sub(r'\n', ' ', cleaned_text)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

    return cleaned_text
