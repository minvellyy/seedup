# manager_agent/tools/stock_recommend_tool.py
#
# stock_model.get_stock_recommendations() 를 CrewAI 툴로 랩핑.
# 에이전트가 user_id만 넘기면 DB 기반 개인화 종목 Top5를 조회할 수 있습니다.
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


@tool("get_db_stock_recommendations")
def get_db_stock_recommendations(user_id: str) -> str:
    """DB 설문 답변과 투자성향에 기반하여 사용자 맞춤 종목 Top5를 추천합니다.
    stock_model.get_stock_recommendations()를 호출하여 개인화된 종목 추천 결과를 반환합니다.

    Args:
        user_id: 사용자 ID (정수형 문자열, 예: '42')

    Returns:
        StockRecommendationResponse JSON 문자열.
        오류 시 {"error": "..."} JSON 문자열.
    """
    try:
        from stock_model import get_stock_recommendations  # noqa: E402
        uid = int(user_id)
        conn = _make_conn()
        try:
            result = get_stock_recommendations(user_id=uid, conn=conn)
            return result.model_dump_json()
        finally:
            conn.close()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool("get_db_stock_recommendations_top3_reasons")
def get_db_stock_recommendations_top3_reasons(user_id: str) -> str:
    """DB 기반 종목 Top5 추천 결과에서 각 종목의 핵심 선정 이유와 주요 지표를 요약합니다.
    에이전트가 추천 근거를 설명할 때 사용.

    Args:
        user_id: 사용자 ID (정수형 문자열)

    Returns:
        종목별 핵심 요약 JSON 문자열 (ticker, name, reasons, features).
    """
    try:
        from stock_model import get_stock_recommendations  # noqa: E402
        uid = int(user_id)
        conn = _make_conn()
        try:
            result = get_stock_recommendations(user_id=uid, conn=conn)
            summary = {
                "risk_tier": result.risk_tier,
                "risk_grade": result.risk_grade,
                "items": [
                    {
                        "rank": item.rank,
                        "ticker": item.ticker,
                        "name": item.name,
                        "market": item.market,
                        "total_score": item.total_score,
                        "reasons": item.reasons,
                        "features": item.features.model_dump() if item.features else None,
                        "explanation": item.explanation,
                    }
                    for item in result.items
                ],
            }
            return json.dumps(summary, ensure_ascii=False)
        finally:
            conn.close()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
