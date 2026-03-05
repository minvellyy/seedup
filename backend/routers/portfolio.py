"""FastAPI 라우터 — 포트폴리오 구성 / 추천 엔드포인트.

main.py에서 include_router() 로 등록:

    from routers.portfolio import router as portfolio_router
    app.include_router(portfolio_router, prefix="/api/v1")
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
    PortfolioRecommendationResponse,
)
from portfolio_model import get_portfolio_recommendation  # noqa: E402

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


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
    response_model=PortfolioRecommendationResponse,
    summary="포트폴리오 구성 및 추천",
    description=(
        "user_id와 코스콤 투자성향 점수를 기반으로 DB 설문 답변을 로드하고 "
        "포트폴리오 구성, 온주 매수 계획, 성과 분석 결과를 반환합니다."
    ),
)
def recommend_portfolio(
    req: UserSurveyRequest,
    conn=Depends(_get_db_conn),
) -> PortfolioRecommendationResponse:
    try:
        return get_portfolio_recommendation(
            user_id=req.user_id,
            conn=conn,
            koscom_score=req.koscom_score,
            monthly_override=req.monthly_override,
            total_assets_override=req.total_assets_override,
            explain_detail=req.explain_detail,
            explain_lang=req.explain_lang,
            explain_style=req.explain_style,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포트폴리오 모델 오류: {e}")


@router.get(
    "/recommend/{user_id}",
    response_model=PortfolioRecommendationResponse,
    summary="포트폴리오 구성 및 추천 (GET)",
    description="user_id를 경로 매개변수로 전달하는 GET 버전입니다.",
)
def recommend_portfolio_get(
    user_id: int,
    koscom_score: int = 20,
    monthly_override: int = None,
    total_assets_override: int = None,
    conn=Depends(_get_db_conn),
) -> PortfolioRecommendationResponse:
    try:
        return get_portfolio_recommendation(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
            monthly_override=monthly_override,
            total_assets_override=total_assets_override,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포트폴리오 모델 오류: {e}")
