"""FastAPI 라우터 — 개별 주식 추천 엔드포인트.

main.py에서 include_router() 로 등록:

    from routers.stocks import router as stocks_router
    app.include_router(stocks_router, prefix="/api/v1")
"""
from __future__ import annotations

import sys
import os

# ── backend/ 디렉터리를 sys.path에 추가 ──────────────────────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# DB_PKG_PATH 환경변수가 있으면 추가로 경로 등록 (core 패키지 위치 지정 시 사용)
_PKG_PATH = os.environ.get("DB_PKG_PATH")
if _PKG_PATH and _PKG_PATH not in sys.path:
    sys.path.insert(0, os.path.abspath(_PKG_PATH))

import pymysql
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from pathlib import Path as _Path
load_dotenv(dotenv_path=_Path(__file__).parent.parent / '.env')

from schemas import (  # noqa: E402
    UserSurveyRequest,
    StockRecommendationResponse,
)
from stock_model import get_stock_recommendations  # noqa: E402

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _get_db_conn():
    """FastAPI Dependency: pymysql DB 연결을 생성하고 요청이 끝나면 자동으로 닫습니다."""
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


@router.post(
    "/recommend",
    response_model=StockRecommendationResponse,
    summary="개별 주식 Top5 추천",
    description=(
        "user_id와 코스콤 투자성향 점수를 기반으로 DB 설문 답변을 로드하고 "
        "개별 주식 Top5 추천 결과를 반환합니다."
    ),
)
def recommend_stocks(
    req: UserSurveyRequest,
    conn=Depends(_get_db_conn),
) -> StockRecommendationResponse:
    try:
        return get_stock_recommendations(
            user_id=req.user_id,
            conn=conn,
            koscom_score=req.koscom_score,
            monthly_override=req.monthly_override,
            explain_detail=req.explain_detail,
            explain_lang=req.explain_lang,
            explain_style=req.explain_style,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 모델 오류: {e}")


@router.get(
    "/recommend/{user_id}",
    response_model=StockRecommendationResponse,
    summary="개별 주식 Top5 추천 (GET)",
    description="user_id를 경로 매개변수로 전달하는 GET 버전입니다. koscom_score는 기본값(20)을 사용합니다.",
)
def recommend_stocks_get(
    user_id: int,
    koscom_score: int = 20,
    conn=Depends(_get_db_conn),
) -> StockRecommendationResponse:
    try:
        return get_stock_recommendations(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 모델 오류: {e}")
