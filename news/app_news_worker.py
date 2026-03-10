from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from pipeline_news_analysis_mvp import search_news_context

app = FastAPI(
    title="SeedUp News Worker API",
    description="뉴스 RAG 검색용 워커 API",
    version="0.1.0"
)


class NewsSearchResponse(BaseModel):
    query: str
    count: int
    results: List[Dict[str, Any]]


@app.get("/")
def root():
    return {
        "message": "SeedUp News Worker API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.get("/news/search", response_model=NewsSearchResponse)
def search_news(
    query: str = Query(..., description="검색할 뉴스 질의"),
    n_results: int = Query(5, ge=1, le=10, description="반환 개수")
):
    try:
        results = search_news_context(query, n_results=max(n_results * 2, 10))

        final_results = []
        for r in results:
            importance = r["meta"].get("importance_score", 0.5)

            # importance가 너무 낮은 것만 제외
            if importance < 0.4:
                continue

            final_results.append(r)

            if len(final_results) >= n_results:
                break

        return {
            "query": query,
            "count": len(final_results),
            "results": final_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"뉴스 검색 중 오류: {str(e)}")