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
    "안정추구형":  ("안전추구형",  "4등급"),  # 구버전 오타 호환
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

    # 1-1. 배당 선호도 (DIVIDEND_PREF: HIGH / MID / LOW)
    # 설문 답변 일괄 조회
    cur.execute(
        """
        SELECT sq.code, sa.value_choice, sa.value_text
        FROM survey_answers sa
        JOIN survey_questions sq ON sa.question_id = sq.id
        WHERE sa.user_id = %s AND sq.code IN (
            'DIVIDEND_PREF', 'TARGET_HORIZON', 'INVEST_GOAL', 'CONTRIBUTION_TYPE', 'ACCOUNT_TYPE'
        )
        ORDER BY sa.updated_at DESC
        """,
        (user_id,),
    )
    _survey: dict = {}
    for _r in (cur.fetchall() or []):
        _c = _r["code"] if isinstance(_r, dict) else _r[0]
        if _c not in _survey:
            _survey[_c] = _r if isinstance(_r, dict) else {"code": _r[0], "value_choice": _r[1], "value_text": _r[2]}

    dividend_pref = (_survey.get("DIVIDEND_PREF", {}).get("value_choice") or "MID").upper()
    invest_goal_raw = (_survey.get("INVEST_GOAL", {}).get("value_text") or "").strip()
    horizon_raw = (_survey.get("TARGET_HORIZON", {}).get("value_text") or "").strip()
    contribution_type = (_survey.get("CONTRIBUTION_TYPE", {}).get("value_choice") or "").upper()
    account_type_raw = (_survey.get("ACCOUNT_TYPE", {}).get("value_text") or "").strip()

    # 2. 유니버스 종목 (active, STOCK) — bucket 포함 조회
    cur.execute("""
        SELECT u.instrument_id, i.stock_code, i.name, u.market,
               COALESCE(u.bucket, 'CORE') AS bucket
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
        raise ValueError("universe_items 에서 유효한 종목을 찾을 수 없습니다.")

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

    # 4. 지표 계산 (Sharpe·MDD·모멘텀·변동성 풀 계산)
    _RF_RATE = 0.035          # 무위험 수익률 3.5% (연)
    ref_date = _date.today()

    def _closest_after(hist, target):
        for d, p in hist:
            if d >= target:
                return p
        return None

    import re as _re

    # ── 투자 기간 파싱 ────────────────────────────────────────────────────
    _horizon_years: int = 3
    _hm = _re.search(r'(\d+)년', horizon_raw)
    if _hm:
        _hy = int(_hm.group(1))
        _horizon_years = _hy if _hy <= 100 else max(1, _hy - _date.today().year)

    computed: List[dict] = []
    for s in stocks:
        hist = price_hist.get(s["instrument_id"], [])
        if len(hist) < 30:
            continue
        prices = [p for _, p in hist]
        cur_price = prices[-1]

        p3m = _closest_after(hist, ref_date - _timedelta(days=91))
        p6m = _closest_after(hist, ref_date - _timedelta(days=182))
        p1y = _closest_after(hist, ref_date - _timedelta(days=365))
        ret_3m = (cur_price / p3m - 1) if p3m else None
        ret_6m = (cur_price / p6m - 1) if p6m else None
        ret_1y = (cur_price / p1y - 1) if p1y else None

        # 변동성·MDD (최근 252 거래일)
        p252 = prices[-252:]
        vol_ann, mdd, sharpe_1y = None, None, None
        if len(p252) >= 20:
            daily_r = [p252[i] / p252[i - 1] - 1 for i in range(1, len(p252))]
            n_dr = len(daily_r)
            mean_r = sum(daily_r) / n_dr
            var_r = sum((r - mean_r) ** 2 for r in daily_r) / max(n_dr - 1, 1)
            vol_ann = _math.sqrt(var_r) * _math.sqrt(252)
            peak = p252[0]
            min_dd = 0.0
            for px in p252:
                peak = max(peak, px)
                min_dd = min(min_dd, (px - peak) / peak)
            mdd = min_dd
            # ── [1] 샤프 지수: (1Y수익률 - 무위험률) / 연변동성 ──────────
            if ret_1y is not None and vol_ann > 0:
                sharpe_1y = (ret_1y - _RF_RATE) / vol_ann

        computed.append({
            **s,
            "ret_3m": ret_3m, "ret_6m": ret_6m, "ret_1y": ret_1y,
            "vol_ann": vol_ann, "mdd": mdd, "sharpe_1y": sharpe_1y, "beta": None,
        })

    if not computed:
        raise ValueError("지표를 계산할 수 있는 종목이 없습니다.")

    # ══════════════════════════════════════════════════════════════════════
    # 4+1단계 스코어링 파이프라인
    #
    # [0] 하드 리스크 필터: 극단적 고위험 종목 사전 제거
    #     - 연 변동성 > 75% 제외
    #     - 52주 MDD < -60% 제외
    # [1] 재무 점수(Fin) 사전 필터 + 코어 스코어 로드
    #     - fin_scores parquet: overall_score, stability_score
    #     - overall_score < 35 (0~100) 이면 제외 (데이터 없는 종목은 통과)
    # [2] 위험조정수익률 (샤프): 높을수록 좋음 → 순위 정규화
    # [3] 다중팩터 가중치 스코어링 (4팩터)
    #     - 모멘텀(Momentum): 기간 맞춤 수익률 (3M/1Y 혼합)
    #     - 우량성(Quality) : 샤프지수 (위험 대비 초과수익)
    #     - 저변동성(LowVol): 연 변동성 역수 → 안정성
    #     - 재무건강성(Fin) : fin_structured overall_score (Piotroski 기반)
    # [4] 유니버스 그룹핑: CORE / GROWTH 체급 리그 분리
    # [5] 투자금·목표 미세조정
    # ══════════════════════════════════════════════════════════════════════

    # ── [0] 하드 리스크 필터 ────────────────────────────────────────────
    _MAX_VOL_ANN = 0.75    # 연 변동성 75% 초과 → 제외
    _MAX_MDD     = -0.60   # MDD -60% 미만 → 제외
    _risk_filtered = [
        s for s in computed
        if not (s["vol_ann"] is not None and s["vol_ann"] > _MAX_VOL_ANN)
        and not (s["mdd"] is not None and s["mdd"] < _MAX_MDD)
    ]
    if len(_risk_filtered) >= 5:
        computed = _risk_filtered

    # ── [1] 재무 점수 로드 (fin_structured parquet) ──────────────────────
    _fin_lookup: dict = {}  # {stock_code_6: {"overall": float(0~100), ...}}
    try:
        from config import FIN_MODEL_DIR
        _parquet_path = (
            FIN_MODEL_DIR / "data" / "processed"
            / "fin_scores_v2_2024_CONSOL_with_mc_with_price.parquet"
        )
        if _parquet_path.exists():
            import pandas as _pd_fin
            _df_fin = _pd_fin.read_parquet(_parquet_path)[
                ["ticker", "as_of", "overall_score", "stability_score", "valuation_score"]
            ]
            # 동일 ticker 중 가장 최근 데이터만 사용
            _df_fin = _df_fin.sort_values("as_of").groupby("ticker").last().reset_index()
            for _, _fr in _df_fin.iterrows():
                _tk = str(_fr["ticker"]).zfill(6)
                def _safe_fin(v):
                    try:
                        f = float(v)
                        return None if _math.isnan(f) or _math.isinf(f) else f
                    except Exception:
                        return None
                _fin_lookup[_tk] = {
                    "overall":    _safe_fin(_fr.get("overall_score")),
                    "stability":  _safe_fin(_fr.get("stability_score")),
                    "valuation":  _safe_fin(_fr.get("valuation_score")),
                }
    except Exception:
        pass  # fin_scores 없으면 재무 필터·팩터 없이 진행

    # 재무 최소 기준 필터: overall_score < 35 제외 (데이터 없는 종목은 통과)
    _MIN_FIN_OVERALL = 35.0
    _fin_filtered = []
    for _s in computed:
        _code = _s["stock_code"].zfill(6)
        _fin_data = _fin_lookup.get(_code, {})
        _fin_overall = _fin_data.get("overall")
        if _fin_overall is not None and _fin_overall < _MIN_FIN_OVERALL:
            continue  # 재무 취약 종목 제외
        _fin_filtered.append(_s)
    if len(_fin_filtered) >= 5:
        computed = _fin_filtered

    def _rank_norm(vals: list) -> list:
        """None 처리 포함 순위 정규화 (0~1).
        후보가 1개 이하면 데이터 부족으로 0.0 반환 (불이익 처리)."""
        idxd = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(idxd) < 2:
            return [0.0] * len(vals)  # 데이터 부족 → 최하점
        srt = sorted(idxd, key=lambda x: x[1])
        rank_map = {i: r / (len(srt) - 1) for r, (i, _) in enumerate(srt)}
        return [rank_map.get(i, 0.0) for i in range(len(vals))]

    # ── [3] 다중팩터 가중치 결정 (투자성향별, 4팩터) ─────────────────────
    # 형식: (모멘텀 가중치, 우량성/샤프 가중치, 저변동성 가중치, 재무건강성 가중치)
    # 합계 = 1.0 / 안전 성향일수록 재무·안정성에 더 높은 비중
    _MF_WEIGHTS = {
        "공격투자형": (0.45, 0.25, 0.10, 0.20),
        "적극투자형": (0.40, 0.30, 0.10, 0.20),
        "위험중립형": (0.30, 0.30, 0.15, 0.25),
        "안전추구형": (0.20, 0.25, 0.20, 0.35),
        "안정추구형": (0.20, 0.25, 0.20, 0.35),
        "안정형":     (0.15, 0.20, 0.25, 0.40),
    }
    _w_mom, _w_qual, _w_vol, _w_fin = _MF_WEIGHTS.get(risk_tier, (0.30, 0.30, 0.15, 0.25))

    # 기간별 모멘텀 혼합 비율
    if _horizon_years <= 2:
        _w3m, _w1y = 0.60, 0.40
    elif _horizon_years >= 7:
        _w3m, _w1y = 0.30, 0.70
    else:
        _w3m, _w1y = 0.40, 0.60

    r3m_n    = _rank_norm([s["ret_3m"]    for s in computed])
    r1y_n    = _rank_norm([s["ret_1y"]    for s in computed])
    sharpe_n = _rank_norm([s["sharpe_1y"] for s in computed])
    vol_n    = _rank_norm([s["vol_ann"]   for s in computed])  # 낮을수록 좋음

    for i, s in enumerate(computed):
        mom_score   = _w3m * r3m_n[i] + _w1y * r1y_n[i]   # 모멘텀
        qual_score  = sharpe_n[i]                            # 우량성 (샤프)
        lowvol_score = 1.0 - vol_n[i]                       # 저변동성

        # 재무건강성 (fin_structured overall_score, 0~100 → 0~1 정규화)
        _code6 = s["stock_code"].zfill(6)
        _fin_data = _fin_lookup.get(_code6, {})
        _fin_ov = _fin_data.get("overall")
        fin_score = (_fin_ov / 100.0) if _fin_ov is not None else 0.50  # 데이터 없으면 중립 0.5
        s["fin_score"] = round(_fin_ov, 1) if _fin_ov is not None else None

        # 투자목표 미세조정
        _at = account_type_raw.lower().replace(' ', '')
        _gl = invest_goal_raw.replace(' ', '')
        _adj = 1.0
        v = s["vol_ann"] or 0.30
        if contribution_type == "DCA" and v < 0.35:
            _adj *= 1.05
        if ('isa' in _at or '연금' in _at) and v < 0.35:
            _adj *= 1.05
        if any(kw in _gl for kw in ('노후', '은퇴', '연금', '안전', '보존')) and v < 0.30:
            _adj *= 1.05
        elif any(kw in _gl for kw in ('자산증식', '증식', '성장', '수익', '공격')) and v > 0.40:
            _adj *= 1.05
        if dividend_pref == "HIGH" and v < 0.30:
            _adj *= 1.03
        elif dividend_pref == "LOW" and v > 0.40:
            _adj *= 1.03

        s["total_score"] = (
            _w_mom  * mom_score  +
            _w_qual * qual_score +
            _w_vol  * lowvol_score +
            _w_fin  * fin_score
        ) * _adj

    # ── [3] 유니버스 그룹핑: CORE / GROWTH 체급 리그 분리 ────────────────
    # CORE = 대형·우량주, GROWTH = 성장·테마주
    # 성향별 TOP5 구성: (core_n, growth_n)
    _LEAGUE_SPLIT = {
        "공격투자형": (2, 3),
        "적극투자형": (2, 3),
        "위험중립형": (3, 2),
        "안전추구형": (4, 1),
        "안정추구형": (4, 1),
        "안정형":     (5, 0),
    }
    _n_core, _n_growth = _LEAGUE_SPLIT.get(risk_tier, (3, 2))

    core_pool   = sorted([s for s in computed if s.get("bucket") == "CORE"],
                          key=lambda x: x["total_score"], reverse=True)
    growth_pool = sorted([s for s in computed if s.get("bucket") != "CORE"],
                          key=lambda x: x["total_score"], reverse=True)

    # 리그에서 부족분은 상대 리그에서 보충
    top_core   = core_pool[:_n_core]
    top_growth = growth_pool[:_n_growth]
    shortfall  = 5 - len(top_core) - len(top_growth)
    if shortfall > 0:
        used = {s["stock_code"] for s in top_core + top_growth}
        extras = [s for s in computed if s["stock_code"] not in used]
        extras.sort(key=lambda x: x["total_score"], reverse=True)
        top_core += extras[:shortfall]

    top5 = sorted(top_core + top_growth, key=lambda x: x["total_score"], reverse=True)[:5]

    # 6. 응답 생성
    items: List[StockItem] = []
    for rank, s in enumerate(top5, 1):
        reasons: List[str] = []
        if s["sharpe_1y"] is not None:
            reasons.append(f"위험조정수익률(샤프) {s['sharpe_1y']:+.2f}")
        if s["ret_3m"] is not None:
            reasons.append(f"3개월 수익률 {s['ret_3m']*100:+.1f}%")
        if s["ret_1y"] is not None:
            reasons.append(f"1년 수익률 {s['ret_1y']*100:+.1f}%")
        if s["vol_ann"] is not None:
            v = s["vol_ann"] * 100
            reasons.append(f"연 변동성 {v:.1f}%" + (" (안정)" if v < 25 else ""))
        if s.get("fin_score") is not None:
            _fv = s["fin_score"]
            _flabel = "탁월" if _fv >= 80 else "우수" if _fv >= 60 else "양호" if _fv >= 40 else "보통"
            reasons.append(f"재무건강성 {_fv:.0f}점 ({_flabel})")
        league_label = "코어(대형)" if s.get("bucket") == "CORE" else "새틀라이트(성장)"
        if not reasons:
            reasons = [league_label]
        else:
            reasons.insert(0, league_label)

        items.append(StockItem(
            rank=rank,
            ticker=s["stock_code"],
            name=s["name"],
            market=s["market"],
            total_score=round(s["total_score"], 4),
            reasons=reasons,
            features=StockFeatures(
                ret_3m=round(s["ret_3m"], 4)    if s["ret_3m"]    is not None else None,
                ret_6m=round(s["ret_6m"], 4)    if s["ret_6m"]    is not None else None,
                ret_1y=round(s["ret_1y"], 4)    if s["ret_1y"]    is not None else None,
                vol_ann=round(s["vol_ann"], 4)  if s["vol_ann"]   is not None else None,
                beta=None,
                mdd=round(s["mdd"], 4)           if s["mdd"]       is not None else None,
            ),
            explanation=(
                f"{s['name']}은(는) {league_label} 종목으로, {risk_tier} 투자자에게 적합합니다. "
                f"샤프지수(위험 대비 수익) 기준 상위권이며, "
                f"모멘텀·우량성·변동성 3개 팩터 종합 평가에서 우수한 점수를 받았습니다."
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
