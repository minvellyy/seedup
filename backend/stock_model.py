"""개별 주식 추천 모델 — FastAPI 라우터에서 직접 호출 가능한 인터페이스."""
from __future__ import annotations

import sys
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# ── sys.path 설정 ─────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))          # backend/
_PKG_ROOT = os.path.dirname(_HERE)                          # backend의 상위 (core 패키지 위치)
_WORKSPACE_ROOT = os.path.dirname(_PKG_ROOT)

# DB_PKG_PATH 환경변수로 core 패키지가 있는 경로를 지정할 수 있습니다.
_env_pkg_path = os.environ.get("DB_PKG_PATH")
_search_paths = [p for p in [_env_pkg_path, _HERE, _PKG_ROOT, _WORKSPACE_ROOT] if p]
for _p in _search_paths:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── 내부 패키지 import (core가 없으면 함수 호출 시 명확한 오류 반환) ─────────────
try:
    from core.profile import build_user_profile, risk_tier_to_grade      # noqa: E402
    from core.universe import get_universe, UniverseConfig                 # noqa: E402
    from core.survey_loader import load_survey_answers                     # noqa: E402
    from core.stock_recommender import recommend_top5_stocks               # noqa: E402
    from core.explain import explain_stock_beginner                        # noqa: E402
    _CORE_AVAILABLE = True
except ImportError as _core_err:
    _CORE_AVAILABLE = False
    _CORE_IMPORT_ERR = str(_core_err)

from schemas import (                                                    # noqa: E402
    StockItem,
    StockFeatures,
    StockRecommendationResponse,
)


import math as _math
from collections import defaultdict as _defaultdict
from datetime import date as _date, timedelta as _timedelta

# ── 투자성향 매핑 ─────────────────────────────────────────────────────────────
_RISK_MAP = {
    "공격투자형":  ("공격투자형",  "1등급"),
    "적극투자형":  ("적극투자형",  "2등급"),
    "위험중립형":  ("위험중립형",  "3등급"),
    "안전추구형":  ("안전추구형",  "4등급"),
    "안정형":      ("안정형",      "5등급"),
}

_KOSCOM_SCORE_MAP = [
    (30, "공격투자형"),
    (25, "적극투자형"),
    (20, "위험중립형"),
    (15, "안전추구형"),
    ( 0, "안정형"),
]


def _koscom_to_type(score: int) -> str:
    for threshold, t in _KOSCOM_SCORE_MAP:
        if score >= threshold:
            return t
    return "안정형"


def _recommend_db(user_id: int, conn, koscom_score: int = 20) -> "StockRecommendationResponse":
    """core 패키지 없이 DB 데이터만으로 종목 Top5를 추천합니다."""
    cur = conn.cursor()

    # 1. 사용자 투자성향
    cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"user_id={user_id} 를 찾을 수 없습니다.")
    inv_type = row.get("investment_type") or _koscom_to_type(koscom_score)
    risk_tier, risk_grade = _RISK_MAP.get(inv_type, ("위험중립형", "3등급"))

    # 2. 유니버스 종목 (active, STOCK)
    cur.execute("""
        SELECT u.instrument_id, i.stock_code, i.name, u.market
        FROM universe_items u
        JOIN instruments i ON u.instrument_id = i.instrument_id
        WHERE u.active = 1
          AND u.asset_type = 'STOCK'
          AND i.last_price IS NOT NULL AND i.last_price > 0
        ORDER BY u.market, u.instrument_id
        LIMIT 400
    """)
    stocks = cur.fetchall()
    if not stocks:
        raise ValueError("추천 가능한 종목이 없습니다.")

    iids = [s["instrument_id"] for s in stocks]
    placeholders = ",".join(["%s"] * len(iids))

    # 3. 최근 2년치 가격 데이터 일괄 조회
    cutoff = (_date.today() - _timedelta(days=730)).isoformat()
    cur.execute(
        f"""
        SELECT instrument_id, price_date, close
        FROM market_prices
        WHERE instrument_id IN ({placeholders})
          AND price_date >= %s
          AND close > 0
        ORDER BY instrument_id, price_date
        """,
        iids + [cutoff],
    )
    price_hist: dict = _defaultdict(list)
    for r in cur.fetchall():
        price_hist[r["instrument_id"]].append((r["price_date"], float(r["close"])))

    # 4. 지표 계산
    ref_date = _date.today()

    def _closest_after(hist, target):
        """target 날짜 이후 첫 번째 종가를 반환(없으면 None)."""
        for d, p in hist:
            if d >= target:
                return p
        return None

    scored: List[dict] = []
    for s in stocks:
        hist = price_hist.get(s["instrument_id"], [])
        if len(hist) < 30:
            continue
        prices = [p for _, p in hist]
        cur_price = prices[-1]

        # 수익률
        p3m = _closest_after(hist, ref_date - _timedelta(days=91))
        p6m = _closest_after(hist, ref_date - _timedelta(days=182))
        p1y = _closest_after(hist, ref_date - _timedelta(days=365))
        ret_3m = (cur_price / p3m - 1) if p3m else None
        ret_6m = (cur_price / p6m - 1) if p6m else None
        ret_1y = (cur_price / p1y - 1) if p1y else None

        # 변동성 & MDD (최근 252 거래일)
        p252 = prices[-252:]
        vol_ann, mdd = None, None
        if len(p252) >= 20:
            daily_r = [p252[i] / p252[i - 1] - 1 for i in range(1, len(p252))]
            n = len(daily_r)
            mean_r = sum(daily_r) / n
            var_r = sum((r - mean_r) ** 2 for r in daily_r) / max(n - 1, 1)
            vol_ann = _math.sqrt(var_r) * _math.sqrt(252)
            peak = p252[0]
            min_dd = 0.0
            for p in p252:
                peak = max(peak, p)
                min_dd = min(min_dd, (p - peak) / peak)
            mdd = min_dd

        scored.append({
            **s,
            "ret_3m": ret_3m, "ret_6m": ret_6m, "ret_1y": ret_1y,
            "vol_ann": vol_ann, "mdd": mdd, "beta": None,
        })

    if not scored:
        raise ValueError("지표를 계산할 수 있는 종목이 없습니다.")

    # 5. 분위 정규화 후 종합 점수
    def _rank_norm(vals: list) -> list:
        """None 처리 포함한 순위 정규화 (0~1)."""
        idxd = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(idxd) < 2:
            return [0.5] * len(vals)
        srt = sorted(idxd, key=lambda x: x[1])
        rank_map = {i: r / (len(srt) - 1) for r, (i, _) in enumerate(srt)}
        return [rank_map.get(i, 0.5) for i in range(len(vals))]

    r3m_n = _rank_norm([s["ret_3m"] for s in scored])
    r1y_n = _rank_norm([s["ret_1y"] for s in scored])
    vol_n = _rank_norm([s["vol_ann"] for s in scored])  # 낮을수록 좋음 → 1-norm

    # 투자성향별 가중치: (w_3m모멘텀, w_1y모멘텀, w_안정성)
    _SCORING_WEIGHTS = {
        "공격투자형": (0.50, 0.40, 0.10),
        "적극투자형": (0.45, 0.40, 0.15),
        "위험중립형": (0.35, 0.40, 0.25),
        "안전추구형": (0.20, 0.30, 0.50),
        "안정형":     (0.15, 0.25, 0.60),
    }
    w3m, w1y, wstab = _SCORING_WEIGHTS.get(risk_tier, (0.35, 0.40, 0.25))

    for i, s in enumerate(scored):
        s["total_score"] = w3m * r3m_n[i] + w1y * r1y_n[i] + wstab * (1.0 - vol_n[i])

    scored.sort(key=lambda x: x["total_score"], reverse=True)
    top5 = scored[:5]

    # 6. 응답 생성
    items: List[StockItem] = []
    for rank, s in enumerate(top5, 1):
        reasons: List[str] = []
        if s["ret_3m"] is not None:
            reasons.append(f"최근 3개월 수익률 {s['ret_3m']*100:+.1f}%")
        if s["ret_1y"] is not None:
            reasons.append(f"1년 수익률 {s['ret_1y']*100:+.1f}%로 강한 모멘텀")
        if s["vol_ann"] is not None:
            v = s["vol_ann"] * 100
            reasons.append(f"연 변동성 {v:.1f}%" + (" (비교적 안정)" if v < 25 else ""))
        if not reasons:
            reasons = ["모멘텀 기반 상위 종목"]

        items.append(StockItem(
            rank=rank,
            ticker=s["stock_code"],
            name=s["name"],
            market=s["market"],
            total_score=round(s["total_score"], 4),
            reasons=reasons,
            features=StockFeatures(
                ret_3m=round(s["ret_3m"], 4)  if s["ret_3m"]  is not None else None,
                ret_6m=round(s["ret_6m"], 4)  if s["ret_6m"]  is not None else None,
                ret_1y=round(s["ret_1y"], 4)  if s["ret_1y"]  is not None else None,
                vol_ann=round(s["vol_ann"], 4) if s["vol_ann"] is not None else None,
                beta=None,
                mdd=round(s["mdd"], 4)         if s["mdd"]     is not None else None,
            ),
            explanation=(
                f"{s['name']}은 최근 {risk_tier} 투자자에게 적합한 모멘텀 상위 종목입니다. "
                f"최근 1년 수익률 기준 상위권에 위치하며 변동성 대비 성과가 우수합니다."
            ),
        ))

    return StockRecommendationResponse(
        user_id=user_id,
        risk_tier=risk_tier,
        risk_grade=risk_grade,
        generated_at=datetime.now().isoformat()[:19],
        items=items,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_stock_recommendations(
    user_id: int,
    conn,
    *,
    koscom_score: int = 20,
    monthly_override: Optional[int] = None,
    top_kospi: int = 150,
    top_kosdaq: int = 150,
    lookback_years: int = 2,
    explain_detail: str = "detailed",
    explain_lang: str = "ko",
    explain_style: str = "formal",
) -> StockRecommendationResponse:
    """DB 설문 → 사용자 프로파일 → 개별주 Top5 추천 결과를 반환합니다."""
    if not _CORE_AVAILABLE:
        return _recommend_db(user_id=user_id, conn=conn, koscom_score=koscom_score)

    # 1) 설문 로드
    koscom_total_score, horizon_years, answers = load_survey_answers(
        user_id=user_id,
        conn=conn,
        monthly_override=monthly_override,
        koscom_score=koscom_score,
    )

    # 2) 유니버스 준비 (주식만)
    get_universe(UniverseConfig(
        top_kospi=top_kospi,
        top_kosdaq=top_kosdaq,
        top_etf=0,
    ))

    # 3) 사용자 프로파일 생성
    profile = build_user_profile(
        koscom_total_score=koscom_total_score,
        horizon_years=horizon_years,
        answers=answers,
    )

    # 4) Top5 추천
    scored_stocks = recommend_top5_stocks(
        profile,
        top_kospi=top_kospi,
        top_kosdaq=top_kosdaq,
        lookback_years=lookback_years,
    )

    # 5) 응답 조립
    items: List[StockItem] = []
    for rank, s in enumerate(scored_stocks, 1):
        f = s.features

        # 설명문 생성 (실패해도 None으로 graceful fallback)
        explanation: Optional[str] = None
        try:
            scores_dict = dict(getattr(s, "scores", {}))
            features_dict = {
                "ret_3m":  getattr(f, "ret_3m", None),
                "ret_6m":  getattr(f, "ret_6m", None),
                "vol_ann": getattr(f, "vol_ann", None),
                "beta":    getattr(f, "beta", None),
                "mdd":     getattr(f, "mdd", None),
            }
            explanation = explain_stock_beginner(
                s.ticker, s.name, features_dict, scores_dict,
                s.total_score, profile.risk_tier,
                detail=explain_detail, lang=explain_lang, style=explain_style,
            )
        except Exception:
            pass

        items.append(StockItem(
            rank=rank,
            ticker=s.ticker,
            name=s.name,
            market=s.market,
            total_score=round(s.total_score, 2),
            reasons=list(s.reasons),
            features=StockFeatures(
                ret_3m=getattr(f, "ret_3m", None),
                ret_6m=getattr(f, "ret_6m", None),
                ret_1y=getattr(f, "ret_1y", None),
                vol_ann=getattr(f, "vol_ann", None),
                beta=getattr(f, "beta", None),
                mdd=getattr(f, "mdd", None),
            ),
            explanation=explanation,
        ))

    return StockRecommendationResponse(
        user_id=user_id,
        risk_tier=profile.risk_tier,
        risk_grade=risk_tier_to_grade(profile.risk_tier),
        generated_at=datetime.now().isoformat(),
        items=items,
    )


def get_stock_recommendations_from_profile(
    profile,
    *,
    top_kospi: int = 150,
    top_kosdaq: int = 150,
    lookback_years: int = 2,
    explain_detail: str = "detailed",
    explain_lang: str = "ko",
    explain_style: str = "formal",
    user_id: int = 0,
) -> StockRecommendationResponse:
    """이미 생성된 UserProfile 객체로 바로 추천을 실행합니다.

    DB 없이 프로파일을 직접 만들어 호출할 때 사용하세요.
    """
    if not _CORE_AVAILABLE:
        raise ImportError(
            f"core 패키지를 찾을 수 없습니다: {_CORE_IMPORT_ERR}. "
            "환경변수 DB_PKG_PATH에 portfolio_stock_recommendation 패키지 경로를 설정하세요."
        )
    get_universe(UniverseConfig(top_kospi=top_kospi, top_kosdaq=top_kosdaq, top_etf=0))

    scored_stocks = recommend_top5_stocks(
        profile,
        top_kospi=top_kospi,
        top_kosdaq=top_kosdaq,
        lookback_years=lookback_years,
    )

    items: List[StockItem] = []
    for rank, s in enumerate(scored_stocks, 1):
        f = s.features
        explanation: Optional[str] = None
        try:
            scores_dict = dict(getattr(s, "scores", {}))
            features_dict = {
                "ret_3m": getattr(f, "ret_3m", None),
                "ret_6m": getattr(f, "ret_6m", None),
                "vol_ann": getattr(f, "vol_ann", None),
                "beta":   getattr(f, "beta", None),
                "mdd":    getattr(f, "mdd", None),
            }
            explanation = explain_stock_beginner(
                s.ticker, s.name, features_dict, scores_dict,
                s.total_score, profile.risk_tier,
                detail=explain_detail, lang=explain_lang, style=explain_style,
            )
        except Exception:
            pass

        items.append(StockItem(
            rank=rank,
            ticker=s.ticker,
            name=s.name,
            market=s.market,
            total_score=round(s.total_score, 2),
            reasons=list(s.reasons),
            features=StockFeatures(
                ret_3m=getattr(f, "ret_3m", None),
                ret_6m=getattr(f, "ret_6m", None),
                ret_1y=getattr(f, "ret_1y", None),
                vol_ann=getattr(f, "vol_ann", None),
                beta=getattr(f, "beta", None),
                mdd=getattr(f, "mdd", None),
            ),
            explanation=explanation,
        ))

    return StockRecommendationResponse(
        user_id=user_id,
        risk_tier=profile.risk_tier,
        risk_grade=risk_tier_to_grade(profile.risk_tier),
        generated_at=datetime.now().isoformat(),
        items=items,
    )
