"""FastAPI 라우터 — 종목·포트폴리오 추천 엔드포인트 (/api/recommendations).

더미 데이터를 제거하고 stock_model / portfolio_model 의 실제 개인화 로직을 위임 호출합니다.
"""
from __future__ import annotations

import sys
import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_PKG_PATH = os.environ.get("DB_PKG_PATH")
if _PKG_PATH and _PKG_PATH not in sys.path:
    sys.path.insert(0, os.path.abspath(_PKG_PATH))

import pymysql
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from pathlib import Path as _Path
load_dotenv(dotenv_path=_Path(__file__).parent.parent / '.env')

from schemas import StockRecommendationResponse, PortfolioRecommendationResponse  # noqa: E402
from stock_model import get_stock_recommendations  # noqa: E402
from portfolio_model import get_multi_portfolio_recommendations  # noqa: E402

# CrewAI 기반 추천 (패키지 없으면 graceful fallback)
try:
    from manager_agent.crew import run_db_stock_recommendation, run_db_portfolio_recommendation
    _CREW_AVAILABLE = True
except Exception as _crew_err:
    _CREW_AVAILABLE = False
    _CREW_ERR = str(_crew_err)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _get_db_conn():
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


@router.get(
    "/stocks/{user_id}",
    response_model=StockRecommendationResponse,
    summary="사용자 맞춤 종목 Top5 추천",
    description="user_id 기반으로 투자성향·설문 답변을 읽어 개인화된 종목 Top5를 반환합니다.",
)
def get_stock_recommendations_by_user(
    user_id: int,
    koscom_score: int = 20,
    conn=Depends(_get_db_conn),
) -> StockRecommendationResponse:
    # CrewAI 경유: run_db_stock_recommendation → get_db_stock_recommendations 툴 호출
    if _CREW_AVAILABLE:
        try:
            import os, json
            model = os.getenv("MANAGER_LLM_MODEL", "openai/gpt-4o-mini")
            from crewai import LLM
            llm = LLM(model=model)
            raw = run_db_stock_recommendation(llm=llm, user_id=user_id)
            # LLM 출력에서 JSON 추출 후 Pydantic 모델로 파싱
            _s = raw.strip()
            if _s.startswith("```"):
                _s = _s.split("```")[1].lstrip("json").strip()
            return StockRecommendationResponse.model_validate_json(_s)
        except Exception:
            pass  # CrewAI 실패 시 직접 모델 호출로 fallback
    try:
        return get_stock_recommendations(user_id=user_id, conn=conn, koscom_score=koscom_score)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"종목 추천 오류: {e}")


@router.get(
    "/portfolios/{user_id}",
    response_model=list[PortfolioRecommendationResponse],
    summary="사용자 맞춤 포트폴리오 3종 추천",
    description="user_id 기반으로 균형/모멘텀/안정 3가지 스타일 포트폴리오를 반환합니다.",
)
def get_portfolio_recommendations_by_user(
    user_id: int,
    koscom_score: int = 20,
    conn=Depends(_get_db_conn),
) -> list[PortfolioRecommendationResponse]:
    # CrewAI 경유: run_db_portfolio_recommendation → get_db_multi_portfolio_recommendations 툴 호출
    if _CREW_AVAILABLE:
        try:
            import os, json
            model = os.getenv("MANAGER_LLM_MODEL", "openai/gpt-4o-mini")
            from crewai import LLM
            llm = LLM(model=model)
            raw = run_db_portfolio_recommendation(llm=llm, user_id=user_id, mode="multi")
            _s = raw.strip()
            if _s.startswith("```"):
                _s = _s.split("```")[1].lstrip("json").strip()
            data = json.loads(_s)
            return [PortfolioRecommendationResponse.model_validate(item) for item in data]
        except Exception:
            pass  # CrewAI 실패 시 직접 모델 호출로 fallback
    try:
        return get_multi_portfolio_recommendations(
            user_id=user_id, conn=conn, koscom_score=koscom_score
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포트폴리오 추천 오류: {e}")