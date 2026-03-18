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
import json as _json
import logging as _logging
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from pathlib import Path as _Path
load_dotenv(dotenv_path=_Path(__file__).parent.parent / '.env')

from schemas import (  # noqa: E402
    UserSurveyRequest,
    PortfolioRecommendationResponse,
)
from portfolio_model import get_portfolio_recommendation, get_multi_portfolio_recommendations, get_user_top3_portfolio_recommendations  # noqa: E402

# CrewAI 기반 포트폴리오 추천 (패키지 없으면 graceful fallback)
try:
    from manager_agent.crew import run_db_portfolio_recommendation as _run_db_portfolio
    _CREW_AVAILABLE = True
except Exception as _crew_err:
    _CREW_AVAILABLE = False
    _CREW_ERR = str(_crew_err)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# ─── 캐시 전략 키 (portfolio_recommendations.strategy_name) ───────────────────
_MULTI_CACHE_KEYS = ['pf_top1', 'pf_top2', 'pf_top3']
_CACHE_TTL_MINUTES = 60
_CACHE_DIR = _Path(__file__).resolve().parent.parent / "portfolio_cache"
_logger = _logging.getLogger(__name__)


def _save_portfolio_json(user_id: int, result) -> None:
    """portfolio_cache/user_{id}_portfolio.json 에 저장합니다.
    result는 PortfolioRecommendationResponse 또는 list[PortfolioRecommendationResponse]입니다.
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"user_{user_id}_portfolio.json"
        if isinstance(result, list):
            data = [r.model_dump(mode="json") for r in result]
        else:
            data = result.model_dump(mode="json")
        path.write_text(
            _json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        _logger.warning("포트폴리오 JSON 저장 실패 (user_id=%s): %s", user_id, exc)


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


def _load_multi_cache(user_id: int, conn) -> list | None:
    """DB에서 1시간 이내 캐시된 3종 포트폴리오를 읽어 반환. 없으면 None."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT strategy_name, strategy_content
        FROM portfolio_recommendations
        WHERE user_id = %s
          AND strategy_name IN ('pf_top1', 'pf_top2', 'pf_top3')
          AND created_at >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
        ORDER BY FIELD(strategy_name, 'pf_top1', 'pf_top2', 'pf_top3')
        """,
        (user_id, _CACHE_TTL_MINUTES),
    )
    rows = cur.fetchall()
    if len(rows) < 3:
        return None
    found = {r['strategy_name'] for r in rows}
    if not all(k in found for k in _MULTI_CACHE_KEYS):
        return None
    result = []
    for r in rows:
        content = r['strategy_content']
        if isinstance(content, str):
            content = _json.loads(content)
        result.append(PortfolioRecommendationResponse.model_validate(content))
    return result


def _save_multi_cache(user_id: int, conn, rec_list: list) -> None:
    """기존 캐시를 삭제하고 새 3종 포트폴리오를 DB에 저장합니다."""
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM portfolio_recommendations
        WHERE user_id = %s
          AND strategy_name IN ('pf_top1', 'pf_top2', 'pf_top3')
        """,
        (user_id,),
    )
    for key, rec in zip(_MULTI_CACHE_KEYS, rec_list):
        content_json = _json.dumps(rec.model_dump(mode='json'), ensure_ascii=False)
        cur.execute(
            """
            INSERT INTO portfolio_recommendations
                (user_id, strategy_name, strategy_content, state)
            VALUES (%s, %s, %s, 'ACTIVE')
            """,
            (user_id, key, content_json),
        )


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
        result = get_portfolio_recommendation(
            user_id=req.user_id,
            conn=conn,
            koscom_score=req.koscom_score,
            monthly_override=req.monthly_override,
            total_assets_override=req.total_assets_override,
            explain_detail=req.explain_detail,
            explain_lang=req.explain_lang,
            explain_style=req.explain_style,
        )
        _save_portfolio_json(req.user_id, result)
        return result
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
        result = get_portfolio_recommendation(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
            monthly_override=monthly_override,
            total_assets_override=total_assets_override,
        )
        _save_portfolio_json(user_id, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포트폴리오 모델 오류: {e}")


@router.get(
    "/recommend-multi/{user_id}",
    response_model=list[PortfolioRecommendationResponse],
    summary="유저 맞춤 Top-3 포트폴리오 추천 (GET)",
    description=(
        "사용자의 투자성향(risk_appetite)에서 최적 팩터 가중치를 산출하고, "
        "다양한 가중치 조합의 후보 포트폴리오 중 Fit Score 상위 3개를 1·2·3순위로 반환합니다. "
        "1시간 동안 DB에 캐싱됩니다."
    ),
)
def recommend_portfolio_multi_get(
    user_id: int,
    koscom_score: int = 20,
    total_assets_override: int = None,
    force_refresh: bool = False,
    conn=Depends(_get_db_conn),
) -> list[PortfolioRecommendationResponse]:
    # ── 1. 캐시 확인 (force_refresh=true면 건너뜀) ─────────────────────────
    if not force_refresh:
        cached = _load_multi_cache(user_id, conn)
        if cached is not None:
            return cached

    # ── 2. 캐시 없음 → CrewAI 경유 포트폴리오 추천 ───────────────────────
    result = None
    if _CREW_AVAILABLE:
        try:
            import os
            model = os.getenv("MANAGER_LLM_MODEL", "openai/gpt-4o-mini")
            from crewai import LLM
            llm = LLM(model=model)
            raw = _run_db_portfolio(llm=llm, user_id=user_id, mode="top3")
            _s = raw.strip()
            if _s.startswith("```"):
                _s = _s.split("```")[1].lstrip("json").strip()
            import json as _j
            data = _j.loads(_s)
            result = [PortfolioRecommendationResponse.model_validate(item) for item in data]
        except Exception:
            result = None  # CrewAI 실패 시 직접 모델 호출로 fallback

    if result is None:
        try:
            result = get_user_top3_portfolio_recommendations(
                user_id=user_id,
                conn=conn,
                koscom_score=koscom_score,
                total_assets_override=total_assets_override,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"포트폴리오 모델 오류: {e}")

    # ── 3. 결과를 DB에 저장 (캐시) ─────────────────────────────────────────
    try:
        _save_multi_cache(user_id, conn, result)
    except Exception as e:
        _logger.warning("포트폴리오 캐시 저장 실패: %s", e)

    # ── 4. JSON 파일 저장 ─────────────────────────────────────────────────
    _save_portfolio_json(user_id, result)

    return result
