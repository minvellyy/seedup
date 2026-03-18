# manager_agent/tools/portfolio_recommend_tool.py
#
# portfolio_model 의 포트폴리오 추천 함수들을 CrewAI 툴로 랩핑.
# 에이전트가 user_id만 넘기면 DB 기반 개인화 포트폴리오를 조회할 수 있습니다.
#
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from crewai.tools import tool

# backend/ 를 sys.path 에 추가
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _make_conn():
    """환경변수 기반 pymysql 연결을 생성합니다."""
    try:
        import pymysql
        from dotenv import load_dotenv
        for _env in (_BACKEND_DIR / ".env", _BACKEND_DIR.parent / ".env"):
            if _env.exists():
                load_dotenv(_env, override=False)
                break
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            db=os.getenv("DB_NAME"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    except ImportError as e:
        raise RuntimeError(f"pymysql 또는 dotenv 패키지가 없습니다: {e}")


@tool("get_db_multi_portfolio_recommendations")
def get_db_multi_portfolio_recommendations(user_id: str) -> str:
    """DB 설문 답변과 투자성향에 기반하여 3가지 스타일(균형/모멘텀/안정) 포트폴리오를 추천합니다.
    portfolio_model.get_multi_portfolio_recommendations()를 호출합니다.

    Args:
        user_id: 사용자 ID (정수형 문자열, 예: '42')

    Returns:
        PortfolioRecommendationResponse 배열 JSON 문자열 (3개 포트폴리오).
        오류 시 {"error": "..."} JSON 문자열.
    """
    try:
        from portfolio_model import get_multi_portfolio_recommendations  # noqa: E402
        uid = int(user_id)
        conn = _make_conn()
        try:
            results = get_multi_portfolio_recommendations(user_id=uid, conn=conn)
            return json.dumps(
                [r.model_dump(mode="json") for r in results],
                ensure_ascii=False,
            )
        finally:
            conn.close()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool("get_db_user_top3_portfolio")
def get_db_user_top3_portfolio(user_id: str) -> str:
    """Fit Score 기준 사용자에게 최적인 포트폴리오 Top-3를 추천합니다.
    투자성향에서 연속 보간한 팩터 가중치 조합으로 후보군을 생성하고 상위 3개를 반환합니다.
    portfolio_model.get_user_top3_portfolio_recommendations()를 호출합니다.

    Args:
        user_id: 사용자 ID (정수형 문자열, 예: '42')

    Returns:
        PortfolioRecommendationResponse 배열 JSON 문자열 (Top-3, 1·2·3순위 레이블 포함).
        오류 시 {"error": "..."} JSON 문자열.
    """
    try:
        from portfolio_model import get_user_top3_portfolio_recommendations  # noqa: E402
        uid = int(user_id)
        conn = _make_conn()
        try:
            results = get_user_top3_portfolio_recommendations(user_id=uid, conn=conn)
            return json.dumps(
                [r.model_dump(mode="json") for r in results],
                ensure_ascii=False,
            )
        finally:
            conn.close()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool("get_db_portfolio_summary")
def get_db_portfolio_summary(user_id: str) -> str:
    """사용자 포트폴리오 추천 결과의 핵심 요약(종목명·비중·레이블)만 반환합니다.
    에이전트가 포트폴리오 구성 내용을 이해하고 설명할 때 사용합니다.

    Args:
        user_id: 사용자 ID (정수형 문자열)

    Returns:
        포트폴리오별 핵심 요약 JSON 문자열.
    """
    try:
        from portfolio_model import get_multi_portfolio_recommendations  # noqa: E402
        uid = int(user_id)
        conn = _make_conn()
        try:
            results = get_multi_portfolio_recommendations(user_id=uid, conn=conn)
            summaries = []
            for pf in results:
                items_summary = [
                    {
                        "ticker": it.ticker,
                        "name": it.name,
                        "weight_pct": it.weight_pct,
                        "asset_type": it.asset_type,
                        "selection_reason": it.selection_reason,
                    }
                    for it in pf.portfolio_items
                ]
                summaries.append({
                    "portfolio_label": pf.portfolio_label,
                    "portfolio_style": pf.portfolio_style,
                    "portfolio_summary": pf.portfolio_summary,
                    "risk_tier": pf.risk_tier,
                    "items": items_summary,
                    "performance_3y": (
                        pf.performance_3y.model_dump() if pf.performance_3y else None
                    ),
                })
            return json.dumps(summaries, ensure_ascii=False)
        finally:
            conn.close()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
