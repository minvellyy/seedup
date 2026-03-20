"""
rag_worker/tools/reports_tool.py

증권사 리포트 RAG 검색 툴.
reports_chroma_db (LangChain + Chroma) 에서 관련 리포트를 검색한다.

DB 경로: 환경변수 REPORTS_CHROMA_PATH 또는 기본값 <workspace_root>/reports_chroma_db
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from crewai.tools import tool
from dotenv import load_dotenv

load_dotenv()

# reports_chroma_db 는 backend/ 안으로 이동됨
_REPORTS_DB_PATH = os.getenv("REPORTS_CHROMA_PATH", str(_BACKEND_DIR / "reports_chroma_db"))
_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
_COLLECTION = "financial_reports"

_vectorstore = None
_vectorstore_lock = threading.Lock()  # 멀티스레드 동시 접근 보호


def _get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        with _vectorstore_lock:
            if _vectorstore is None:  # double-checked locking
                from langchain_openai import OpenAIEmbeddings
                try:
                    from langchain_chroma import Chroma
                except ImportError:
                    from langchain_community.vectorstores import Chroma

                embeddings = OpenAIEmbeddings(model=_EMBED_MODEL)
                _vectorstore = Chroma(
                    persist_directory=_REPORTS_DB_PATH,
                    embedding_function=embeddings,
                    collection_name=_COLLECTION,
                )
    return _vectorstore


_search_lock = threading.Lock()  # ChromaDB SQLite 동시 읽기 경쟁 방지


def search_reports_context(query: str, k: int = 3, ticker: str | None = None) -> list[dict]:
    """
    증권사 리포트 ChromaDB 에서 관련 문서를 검색한다.
    ticker 를 전달하면 해당 종목 리포트만 필터링하고, 결과가 없으면 필터 없이 재검색.
    Returns: list of {"content": str, "metadata": dict}
    """
    db = _get_vectorstore()
    with _search_lock:
        if ticker:
            docs = db.similarity_search(query, k=k, filter={"ticker": str(ticker).zfill(6)})
            # ticker 지정 시 결과 없으면 빈 결과 반환 (다른 종목 리포트 노출 방지)
        else:
            docs = db.similarity_search(query, k=k)
    return [{"content": d.page_content, "metadata": d.metadata} for d in docs]


@tool("reports_rag_search")
def reports_rag_search(query: str) -> str:
    """
    증권사 리포트 RAG 저장소에서 관련 리포트를 검색한다.
    종목명·섹터·투자 테마를 자연어로 질의할 수 있다.
    예) '삼성전자 반도체 목표주가', 'HBM 수요 전망', '2차전지 업황 분석'
    Args:
        query: 한국어 자연어 검색 질의
    """
    if not os.path.exists(_REPORTS_DB_PATH):
        return json.dumps(
            {
                "status": "DB_NOT_FOUND",
                "message": "증권사 리포트 DB가 없습니다. POST /api/v1/reports/init 으로 ETL을 먼저 실행하세요.",
            },
            ensure_ascii=False,
        )

    try:
        results = search_reports_context(query, k=3)
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e)}, ensure_ascii=False)

    if not results:
        return "관련 리포트가 없습니다."

    lines = []
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        brokerage = meta.get("brokerage", "증권사 미상")
        title = meta.get("report_title", "제목 없음")
        date = meta.get("report_date", "날짜 미상")
        lines.append(f"[리포트 {i}] {brokerage} '{title}' ({date})")
        lines.append(r["content"])
        lines.append("-" * 60)
    return "\n".join(lines)
