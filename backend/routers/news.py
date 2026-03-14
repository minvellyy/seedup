# routers/news.py
#
# 뉴스 RAG 파이프라인 엔드포인트.
# main.py 에서 include_router() 로 등록:
#
#   app.include_router(news_router, prefix="/api/v1")
#
# ── 공개 엔드포인트 ────────────────────────────────────────────────────
#   GET  /api/v1/news/search   — ChromaDB RAG 검색
#   POST /api/v1/news/update   — 수동 배치 트리거 (관리용)
#   POST /api/v1/news/init     — 90일치 초기 DB 구축 (최초 1회, 관리용)
#
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from news_model.pipeline_news_analysis_mvp import search_news_context, daily_batch
from rag_worker.scheduler import run_news_init

logger = logging.getLogger("news_router")

router = APIRouter(prefix="/news", tags=["News"])


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────

def _run_news_batch() -> None:
    """백그라운드 스레드에서 daily_batch 를 실행한다."""
    logger.info("⏰ 뉴스 배치 시작")
    try:
        daily_batch()
        logger.info("✅ 뉴스 배치 완료")
    except Exception as e:
        logger.error(f"❌ daily_batch 오류: {e}")


# ── doc 파서 ─────────────────────────────────────────────────────────

def _parse_doc(doc: str) -> dict:
    """ChromaDB에 저장된 raw doc 텍스트를 구조화된 dict로 변환합니다."""
    result = {}
    field_map = {
        "title":       "title",
        "summary":     "summary",
        "themes":      "themes",
        "events":      "events",
        "companies":   "companies",
        "organizations": "organizations",
        "industries":  "industries",
        "risk":        "risks",
        "opportunity": "opportunities",
        "sentiment":   "sentiment",
    }
    for line in doc.splitlines():
        line = line.strip()
        for key, out_key in field_map.items():
            prefix = f"{key}:"
            if line.lower().startswith(prefix):
                value = line[len(prefix):].strip()
                # 콤마 구분 리스트 필드
                if out_key in ("themes", "events", "companies", "organizations", "industries", "risks", "opportunities"):
                    result[out_key] = [v.strip() for v in value.split(",") if v.strip()]
                else:
                    result[out_key] = value
                break
    return result


# ── 스키마 ────────────────────────────────────────────────────────────

class NewsSearchResponse(BaseModel):
    query: str
    count: int
    results: List[Dict[str, Any]]


# ── 엔드포인트 ────────────────────────────────────────────────────────

@router.post("/update", summary="뉴스 수집/분석 수동 트리거 (관리용)")
def trigger_news_update():
    """수동으로 뉴스 수집·분석 배치를 즉시 실행한다."""
    t = threading.Thread(target=_run_news_batch, daemon=True)
    t.start()
    return {"message": "뉴스 업데이트 시작됨 (백그라운드 실행 중)"}


@router.post("/init", summary="뉴스 초기 DB 구축 (90일치, 관리용)")
def init_news(background_tasks: BackgroundTasks):
    """90일치 뉴스를 수집·분석하여 ChromaDB 를 초기 구축한다. (최초 1회 실행)"""
    background_tasks.add_task(run_news_init)
    return {"message": "뉴스 초기 DB 구축 시작 (90일치, 백그라운드 실행 중)"}


@router.get("/search", response_model=NewsSearchResponse, summary="뉴스 RAG 검색")
def search_news(
    query: str = Query(..., description="검색할 뉴스 질의 (한국어 자연어)"),
    n_results: int = Query(5, ge=1, le=10, description="반환할 결과 수"),
):
    """ChromaDB 벡터 인덱스에서 관련 뉴스를 검색해 반환한다."""
    try:
        candidates = search_news_context(query, n_results=max(n_results * 2, 10))

        results: List[Dict[str, Any]] = []
        for r in candidates:
            meta = r["meta"]
            if meta.get("importance_score", 0.5) < 0.4:
                continue
            parsed = _parse_doc(r["doc"])
            results.append({
                "title":         parsed.get("title", ""),
                "summary":       parsed.get("summary", ""),
                "themes":        parsed.get("themes", []),
                "events":        parsed.get("events", []),
                "companies":     parsed.get("companies", []),
                "industries":    parsed.get("industries", []),
                "risks":         parsed.get("risks", []),
                "opportunities": parsed.get("opportunities", []),
                "sentiment":     parsed.get("sentiment", meta.get("sentiment", "")),
                "published_at":  meta.get("published_at", ""),
                "importance_score": meta.get("importance_score", 0.5),
                "query_topic":   meta.get("query_topic", ""),
                "news_id":       meta.get("news_id", ""),
            })
            if len(results) >= n_results:
                break

        return {"query": query, "count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"뉴스 검색 중 오류: {e}")
