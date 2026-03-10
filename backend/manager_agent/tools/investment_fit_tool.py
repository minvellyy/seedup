# manager_agent/tools/investment_fit_tool.py
#
# 투자원칙 적합도 분석 툴.
# FastAPI 레이어에서 이미 조회한 사용자 프로파일 + 종목 추천 결과를
# JSON 문자열로 받아서 에이전트가 분석할 수 있도록 포맷해 반환합니다.
#
# 호출 흐름 (FastAPI 기준):
#   1. api_models.stock_model.get_stock_recommendations(user_id, conn) 호출
#   2. 결과에서 해당 ticker의 StockItem을 추출
#   3. user_profile_json, stock_item_json 을 이 툴에 넘김
#
from __future__ import annotations

import json
from crewai.tools import tool


@tool("read_investment_fit_data")
def read_investment_fit_data(user_profile_json: str, stock_item_json: str) -> str:
    """사용자 투자 프로파일과 종목 추천 결과를 받아
    '이 종목이 이 사용자에게 왜 맞는지(또는 맞지 않는지)' 분석에 필요한
    모든 맥락 정보를 구조화해 반환합니다.

    Args:
        user_profile_json: UserProfileSummary JSON 문자열
                           필드: risk_tier, grade, horizon_years, goal,
                                 deployment, monthly_contribution_krw,
                                 total_assets_krw, dividend_pref_1to5, account_type
        stock_item_json:   StockItem JSON 문자열 (없으면 빈 JSON '{}' 전달)
                           필드: rank, ticker, name, market, total_score,
                                 reasons, features(ret_3m/vol_ann/beta/mdd)
    """
    try:
        profile = json.loads(user_profile_json) if user_profile_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "user_profile_json 파싱 실패"}, ensure_ascii=False)

    try:
        stock = json.loads(stock_item_json) if stock_item_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "stock_item_json 파싱 실패"}, ensure_ascii=False)

    # ── 투자원칙 적합도 판단 기준 도출 ─────────────────────────────────────────
    risk_tier   = profile.get("risk_tier", "")
    horizon     = profile.get("horizon_years", 0)
    goal        = profile.get("goal", "")
    deployment  = profile.get("deployment", "")
    dividend_pref = profile.get("dividend_pref_1to5", 3)
    account_type  = profile.get("account_type", "")
    monthly_krw   = profile.get("monthly_contribution_krw", 0)
    total_krw     = profile.get("total_assets_krw")

    # 종목 특성
    ticker      = stock.get("ticker", "")
    name        = stock.get("name", "")
    total_score = stock.get("total_score")
    reasons     = stock.get("reasons", [])
    features    = stock.get("features", {})
    in_top5     = total_score is not None   # 추천 결과에 포함되었는지 여부

    # 리스크 성향 → 기대 변동성 허용 범위 매핑
    _risk_vol_map = {
        "공격투자형":  "높은 변동성(연간 30% 이상) 감수 가능",
        "적극투자형":  "중간-높은 변동성(연간 20~30%) 감수 가능",
        "위험중립형":  "중간 변동성(연간 15~20%) 감수 가능",
        "안정추구형":  "낮은 변동성(연간 10~15% 이내) 선호",
        "안전추구형":  "매우 낮은 변동성(연간 10% 이내) 필요",
    }
    vol_tolerance = _risk_vol_map.get(risk_tier, "정보 없음")

    # 실제 종목 변동성과 비교
    vol_ann = features.get("vol_ann")
    vol_match = None
    if vol_ann is not None:
        vol_pct = round(vol_ann * 100, 1)
        if risk_tier in ("공격투자형", "적극투자형"):
            vol_match = "적합" if vol_pct >= 15 else "낮은 편 (더 공격적 선택 가능)"
        elif risk_tier in ("위험중립형",):
            vol_match = "적합" if 10 <= vol_pct <= 30 else ("높은 편" if vol_pct > 30 else "낮은 편")
        else:
            vol_match = "적합" if vol_pct <= 20 else "변동성 주의 필요"
    else:
        vol_pct = None
        vol_match = "데이터 없음"

    # 투자 기간 대 수익률 매칭
    ret_key = "ret_1y" if horizon >= 1 else "ret_3m"
    horizon_ret = features.get(ret_key)

    result = {
        "ticker": ticker,
        "name": name,
        "in_top5_recommendation": in_top5,
        "total_score": total_score,
        "recommendation_reasons": reasons,
        "user_profile": {
            "risk_tier": risk_tier,
            "grade": profile.get("grade", ""),
            "vol_tolerance": vol_tolerance,
            "horizon_years": horizon,
            "goal": goal,
            "deployment": deployment,
            "dividend_pref_1to5": dividend_pref,
            "account_type": account_type,
            "monthly_contribution_krw": monthly_krw,
            "total_assets_krw": total_krw,
        },
        "fit_signals": {
            "vol_ann_pct": vol_pct,
            "vol_match": vol_match,
            "horizon_return_pct": round(horizon_ret * 100, 2) if horizon_ret else None,
            "horizon_return_period": ret_key.replace("ret_", ""),
            "beta": features.get("beta"),
            "mdd_pct": round(features.get("mdd", 0) * 100, 2) if features.get("mdd") else None,
        },
        "analysis_instructions": (
            "위 데이터를 바탕으로 다음을 설명하라:\n"
            "1) 이 종목이 사용자의 투자 성향(risk_tier)과 얼마나 맞는지\n"
            "2) recommendation_reasons의 각 이유가 사용자 상황에 어떻게 연결되는지\n"
            "3) 투자 기간(horizon_years) 및 목표(goal)와의 적합성\n"
            "4) 주의할 점이 있다면 1가지만, 부담 없이 쉬운 말로\n"
            "→ 모든 설명은 전문용어 없이 쉽게, 사용자 개인에게 직접 말하는 톤으로 작성"
        ),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
