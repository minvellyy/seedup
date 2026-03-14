"""
rag_worker/tools/esg_tool.py

ESG 보고서 분석 툴.
esg_model.analyzer.analyze_by_stock_code 를 CrewAI @tool 로 래핑.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# backend/ 를 sys.path 에 추가 (esg_model 이 backend/ 안에 있음)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from crewai.tools import tool
from esg_model.analyzer import analyze_by_stock_code


def analyze_esg_direct(ticker: str, force_refresh: bool = False) -> dict | None:
    """
    종목코드로 ESG 분석을 수행하고 결과 dict 를 반환한다.
    보고서가 없으면 None 을 반환한다.
    """
    return analyze_by_stock_code(str(ticker).zfill(6), force_refresh=force_refresh)


@tool("esg_analysis")
def esg_analysis(ticker: str) -> str:
    """
    특정 종목의 ESG 보고서를 분석하여 리스크 요인과 기대 요인을 반환한다.
    DB에 캐시된 결과가 있으면 즉시 반환하고, 없으면 GPT로 새로 분석한다.
    Args:
        ticker: 종목코드 (예: '005930')
    """
    result = analyze_esg_direct(ticker)
    if result is None:
        return json.dumps(
            {
                "ticker": str(ticker).zfill(6),
                "status": "NO_REPORT",
                "message": "해당 종목의 ESG 보고서가 없습니다.",
            },
            ensure_ascii=False,
        )
    return json.dumps(result, ensure_ascii=False, indent=2)
