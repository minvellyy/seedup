# routers/esg.py
#
# ESG 보고서 분석 엔드포인트.
# main.py 에서 include_router() 로 등록:
#
#   app.include_router(esg_router, prefix="/api/v1")
#
# 엔드포인트:
#   GET  /api/v1/esg/{ticker}         — ESG 리스크·기대요인 분석 (캐시 우선)
#   GET  /api/v1/esg/{ticker}?force=1 — 캐시 무시 재분석
#
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from rag_worker.tools.esg_tool import analyze_esg_direct

logger = logging.getLogger("esg_router")

router = APIRouter(prefix="/esg", tags=["ESG"])


class EsgResponse(BaseModel):
    ticker: str
    status: str
    result: dict[str, Any] | None


@router.get("/{ticker}", response_model=EsgResponse, summary="ESG 보고서 분석")
def get_esg(
    ticker: str,
    force: bool = Query(False, description="True 면 캐시 무시 후 재분석"),
):
    """
    종목코드로 ESG 리스크·기대요인을 분석한다.
    MySQL esg_reports 테이블에서 최신 보고서를 로드하고
    GPT-4o-mini + SBERT RAG 로 분석한 결과를 반환한다.
    캐시(analyzed_at)가 있으면 즉시 반환한다.
    """
    try:
        result = analyze_esg_direct(ticker, force_refresh=force)
        status = "NO_REPORT" if result is None else "OK"
        return {"ticker": ticker, "status": status, "result": result}
    except Exception as exc:
        logger.error(f"ESG 분석 오류 ({ticker}): {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
