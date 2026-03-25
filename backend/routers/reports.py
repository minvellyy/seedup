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
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from rag_worker.tools.reports_tool import search_reports_context
from rag_worker.scheduler import run_reports_etl, run_reports_init

_REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

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


class ReportInsightItem(BaseModel):
    brokerage: str
    title: str
    date: str
    content: str
    pdf_url: str | None = None


class ReportInsightsResponse(BaseModel):
    ticker: str
    count: int
    items: list[ReportInsightItem]


@router.get("/insights/{ticker}", response_model=ReportInsightsResponse, summary="종목 증권사 리포트 인사이트 조회")
def get_report_insights(
    ticker: str,
    k: int = Query(3, ge=1, le=10, description="반환 건수"),
):
    """특정 종목의 증권사 리포트를 ChromaDB에서 직접 조회한다. ticker 필터를 우선 적용하고, 없으면 회사명으로 폴백한다."""
    import os
    import sys
    from pathlib import Path

    ticker = ticker.zfill(6)

    # ticker → 회사명 (MySQL 또는 parquet)
    company_name: str | None = None
    try:
        import pymysql
        from dotenv import load_dotenv
        load_dotenv()
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "192.168.101.70"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name FROM instruments WHERE stock_code=%s LIMIT 1",
                    (ticker,),
                )
                row = cur.fetchone()
        if row and row.get("name"):
            company_name = row["name"]
    except Exception:
        pass

    query = company_name or ticker

    try:
        # 청크 중복 제거를 위해 k보다 많이 가져온 후 report_title 기준으로 dedup
        raw = search_reports_context(query, k=k * 3, ticker=ticker)
        seen_titles: set[str] = set()
        items: list[ReportInsightItem] = []
        for r in raw:
            title = r["metadata"].get("report_title", "제목 없음")
            if title in seen_titles:
                continue
            seen_titles.add(title)

            # PDF URL 생성: report_type(카테고리) + source(파일명) → /api/v1/reports/pdf/{category}/{filename}
            # report_type 불일치·'None' 케이스 대비 모든 카테고리 폴더를 탐색
            pdf_url: str | None = None
            source = r["metadata"].get("source", "")
            report_type = r["metadata"].get("report_type", "")
            if source:
                pdf_filename = source.replace(".json", ".pdf")
                _CATEGORIES = ["종목분석", "산업분석", "시황정보", "투자정보"]
                # 1) 메타데이터 report_type 우선, 2) 나머지 폴더 순차 탐색
                candidate_types = ([report_type] if report_type and report_type != "None" else []) + _CATEGORIES
                for cat in candidate_types:
                    pdf_path = _REPORTS_DIR / cat / pdf_filename
                    if pdf_path.exists():
                        encoded = urllib.parse.quote(pdf_filename, safe="")
                        pdf_url = f"/api/v1/reports/pdf/{urllib.parse.quote(cat, safe='')}/{encoded}"
                        break
            # 로컬 PDF 없으면: 1) .url 사이드카 파일 직접 탐색, 2) ChromaDB 메타데이터 naver_pdf_url 순으로 폴백
            if pdf_url is None and source:
                url_filename = source.replace(".json", ".url")
                for cat in candidate_types:
                    url_path = _REPORTS_DIR / cat / url_filename
                    if url_path.exists():
                        try:
                            pdf_url = url_path.read_text(encoding="utf-8").strip()
                        except Exception:
                            pass
                        break
            if pdf_url is None:
                naver = r["metadata"].get("naver_pdf_url")
                if naver and naver != "None":
                    pdf_url = naver

            items.append(
                ReportInsightItem(
                    brokerage=r["metadata"].get("brokerage", "증권사 미상"),
                    title=title,
                    date=r["metadata"].get("report_date", "날짜 미상"),
                    content=r["content"],
                    pdf_url=pdf_url,
                )
            )
            if len(items) >= k:
                break
        return ReportInsightsResponse(ticker=ticker, count=len(items), items=items)
    except Exception as exc:
        logger.error(f"리포트 인사이트 조회 오류 (ticker={ticker}): {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/pdf/{report_type}/{filename}", summary="증권사 리포트 PDF 다운로드")
def get_report_pdf(report_type: str, filename: str):
    """로컬에 저장된 증권사 리포트 PDF 파일을 반환한다."""
    if ("/" in report_type or "\\" in report_type or
            "/" in filename or "\\" in filename or
            report_type.startswith("..") or filename.startswith("..")):
        raise HTTPException(status_code=400, detail="잘못된 경로입니다.")
    pdf_path = _REPORTS_DIR / report_type / filename
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="리포트 파일을 찾을 수 없습니다.")
    encoded_filename = urllib.parse.quote(filename)
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"},
    )


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
