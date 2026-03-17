"""
rag_worker/tools/news_tool.py

뉴스 RAG 검색 툴.
news_model.pipeline_news_analysis_mvp.search_news_context 를 CrewAI @tool 로 래핑.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from crewai.tools import tool
from news_model.pipeline_news_analysis_mvp import search_news_context


def search_news_direct(query: str, n_results: int = 5, company_name: str | None = None) -> list[dict]:
    """뉴스 RAG ChromaDB 에서 관련 기사를 검색한다. list of {"doc": str, "meta": dict}

    company_name 을 전달하면 해당 기업 관련 뉴스를 우선 필터링한다.
    """
    return search_news_context(query, n_results=n_results, company_name=company_name)


@tool("news_rag_search")
def news_rag_search(query: str) -> str:
    """
    뉴스 RAG 저장소에서 관련 최신 뉴스를 검색한다.
    테마·종목·시장 이슈에 대한 한국어 자연어 질의로 검색한다.
    예) '삼성전자 HBM 수요', '반도체 업황', '원달러 환율 상승'
    Args:
        query: 한국어 자연어 검색 질의
    """
    results = search_news_direct(query, n_results=5)
    if not results:
        return "관련 뉴스가 없습니다. 뉴스 DB가 초기화되지 않았을 수 있습니다."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[뉴스 {i}]")
        lines.append(r["doc"])
        lines.append(f"메타: {json.dumps(r['meta'], ensure_ascii=False)}")
        lines.append("-" * 60)
    return "\n".join(lines)
