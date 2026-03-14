# manager_agent/tools/unstructured_tool.py
#
# 비정형 데이터 분석 모델 연동 툴.
# backend/rag_worker 패키지(ESG · 뉴스 · 증권사 리포트 통합 RAG 워커)를 사용한다.
#
from __future__ import annotations

import json
import sys
from pathlib import Path

from crewai.tools import tool

# backend/ 를 sys.path 에 추가 → rag_worker, esg_model 등 임포트 가능
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent   # backend/
_WORKSPACE = _BACKEND_DIR.parent                               # workspace root
for _p in (str(_BACKEND_DIR), str(_WORKSPACE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from rag_worker.tools.esg_tool import analyze_esg_direct
from rag_worker.tools.news_tool import search_news_direct
from rag_worker.tools.reports_tool import search_reports_context


@tool("read_unstructured_analysis")
def read_unstructured_analysis(ticker: str) -> str:
    """비정형 데이터 분석 결과를 조회합니다.
    ESG 보고서 리스크·기대요인, 관련 최신 뉴스, 증권사 리포트 인사이트를 통합 반환합니다.
    Args:
        ticker: 종목코드 (예: '005930')
    """
    t = str(ticker).zfill(6)
    output: dict = {"ticker": t, "status": "OK"}

    # 1. ESG 분석
    try:
        esg = analyze_esg_direct(t)
        output["esg"] = esg if esg is not None else {"status": "NO_REPORT"}
    except Exception as exc:
        output["esg"] = {"status": "ERROR", "message": str(exc)}

    # 2. 뉴스 검색
    try:
        news_results = search_news_direct(t, n_results=5)
        output["news"] = [{"doc": r["doc"], "meta": r["meta"]} for r in news_results]
    except Exception as exc:
        output["news"] = {"status": "ERROR", "message": str(exc)}

    # 3. 증권사 리포트 검색
    try:
        report_results = search_reports_context(t, k=3)
        output["reports"] = [
            {"content": r["content"], "metadata": r["metadata"]}
            for r in report_results
        ]
    except Exception as exc:
        output["reports"] = {"status": "ERROR", "message": str(exc)}

    return json.dumps(output, ensure_ascii=False, indent=2)
