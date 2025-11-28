# modules/document_processor.py

import tiktoken
from loguru import logger
from typing import List, Dict, Any

from langchain_community.document_loaders import (
    PyPDFLoader, Docx2txtLoader, UnstructuredPowerPointLoader, TextLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS


def tiktoken_len(text):
    """텍스트의 토큰 길이를 계산합니다."""
    tokenizer = tiktoken.get_encoding("cl100k_base")
    return len(tokenizer.encode(text))


def get_text(uploaded_files):
    """업로드된 문서에서 텍스트를 추출합니다."""
    all_docs = []
    for doc in uploaded_files:
        file_name = doc.name
        try:
            # Streamlit 환경에서는 파일을 직접 저장해야 로더가 접근 가능
            with open(file_name, "wb") as f:
                f.write(doc.getvalue())
            logger.info(f"Uploaded: {file_name}")

            if file_name.endswith('.pdf'):
                loader = PyPDFLoader(file_name)
            elif file_name.endswith('.docx'):
                loader = Docx2txtLoader(file_name)
            elif file_name.endswith('.pptx'):
                loader = UnstructuredPowerPointLoader(file_name)
            elif file_name.endswith('.txt'):
                loader = TextLoader(file_name, encoding="utf-8")
            else:
                logger.warning(f"지원하지 않는 파일 형식입니다: {file_name}. 건너뜁니다.")
                continue

            all_docs.extend(loader.load_and_split())
        except Exception as e:
            logger.error(f"문서 처리 중 오류 발생 ({file_name}): {e}", exc_info=True)
            continue # 오류 발생 시 해당 파일은 건너뛰고 다음 파일 처리
    return all_docs


def get_text_chunks(texts):
    """텍스트를 청크 단위로 분할합니다."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=100,
        length_function=tiktoken_len
    )
    return splitter.split_documents(texts)


def get_vectorstore(chunks):
    """텍스트 청크를 기반으로 벡터 데이터베이스를 생성합니다."""
    embeddings = HuggingFaceEmbeddings(
        model_name="jhgan/ko-sroberta-multitask",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
    return FAISS.from_documents(chunks, embeddings)
