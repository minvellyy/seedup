# routers/reports.py
#
# 증권사 리포트 RAG 검색 + ETL 초기화 엔드포인트.
# main.py 에서 include_router() 로 등록:
#
#   app.include_router(reports_router, prefix="/api/v1")
#
# 엔드포인트:
#   GET  /api/v1/reports/search?query=...   — 리포트 RAG 검색
#   POST /api/v1/reports/init               — 30일치 초기 ETL (최초 1회, 백그라운드)
#   POST /api/v1/reports/update             — 1일치 수동 업데이트 (백그라운드)
#
from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from rag_worker.tools.reports_tool import search_reports_context
from rag_worker.scheduler import run_reports_etl, run_reports_init

logger = logging.getLogger("reports_router")

router = APIRouter(prefix="/reports", tags=["Reports"])


class ReportsSearchResponse(BaseModel):
    query: str
    count: int
    results: list[dict[str, Any]]


@router.get("/search", response_model=ReportsSearchResponse, summary="증권사 리포트 RAG 검색")
def search_reports(
    query: str = Query(..., description="검색 질의 (한국어 자연어)"),
    k: int = Query(3, ge=1, le=10, description="반환 건수"),
):
    """ChromaDB 벡터 인덱스에서 관련 증권사 리포트를 검색해 반환한다."""
    try:
        raw = search_reports_context(query, k=k)
        results = [{"content": r["content"], "metadata": r["metadata"]} for r in raw]
        return {"query": query, "count": len(results), "results": results}
    except Exception as exc:
        logger.error(f"리포트 검색 오류: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/init", summary="리포트 초기 DB 구축 (30일치, 관리용)")
def init_reports(background_tasks: BackgroundTasks):
    """수동으로 30일치 리포트 크롤링·파싱·임베딩을 시작한다. (최초 1회 실행)"""
    background_tasks.add_task(run_reports_init)
    return {"message": "리포트 초기 DB 구축 시작 (30일치, 백그라운드 실행 중)"}


@router.post("/update", summary="리포트 1일치 수동 업데이트 (관리용)")
def update_reports(background_tasks: BackgroundTasks):
    """수동으로 리포트 1일치를 크롤링·파싱·임베딩한다."""
    background_tasks.add_task(run_reports_etl)
    return {"message": "리포트 수동 업데이트 시작 (1일치, 백그라운드 실행 중)"}
