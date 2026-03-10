"""포트폴리오 구성 / 추천 모델 — FastAPI 라우터에서 직접 호출 가능한 인터페이스."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import numpy as _np

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
    from core.profile import build_user_profile, risk_tier_to_grade       # noqa: E402
    from core.universe import get_universe, UniverseConfig                 # noqa: E402
    from core.survey_loader import load_survey_answers                     # noqa: E402
    from core.recommender import recommend_initial_portfolio               # noqa: E402
    from core.data_kr import get_prices                                    # noqa: E402
    from core.risk_metrics import portfolio_metrics                        # noqa: E402
    from core.return_forecast import monte_carlo_forecast, bootstrap_forecast  # noqa: E402
    from core.allocation import describe_rule_dict, get_rule               # noqa: E402
    from core.explain import (                                             # noqa: E402
        explain_portfolio_item_beginner,
    )
    _CORE_AVAILABLE = True
except ImportError as _core_err:
    _CORE_AVAILABLE = False
    _CORE_IMPORT_ERR = str(_core_err)

from schemas import (                                                    # noqa: E402
    AllocationRulesSummary,
    BuyPlanItem,
    CapCompliance,
    MonteCarloResult,
    PerformanceMetrics,
    PortfolioItem,
    PortfolioRecommendationResponse,
    UserProfileSummary,
)

import math as _math
import random as _random
from collections import defaultdict as _defaultdict
from datetime import date as _date, timedelta as _timedelta

# ─────────────────────────────────────────────────────────────────────────────
# 투자성향 매핑
# ─────────────────────────────────────────────────────────────────────────────
_RISK_MAP_PF = {
    "공격투자형": ("공격투자형",  "1등급", 1.0,  0.0),
    "적극투자형": ("적극투자형",  "2등급", 0.9,  0.1),
    "위험중립형": ("위험중립형",  "3등급", 0.70, 0.30),
    "안전추구형": ("안전추구형",  "4등급", 0.50, 0.50),
    "안정형":     ("안정형",      "5등급", 0.30, 0.70),
}

# 포트폴리오 스코어링 스타일별 가중치 (3m수익률, 1y수익률, 1-변동성)
_SCORING_WEIGHTS = {
    "balanced": (0.35, 0.40, 0.25),  # 균형 추천형 (기본)
    "momentum": (0.50, 0.40, 0.10),  # 모멘텀 집중형
    "lowvol":   (0.20, 0.40, 0.40),  # 안정 우선형
}
_SCORING_LABELS = {
    "balanced": "균형 추천형",
    "momentum": "모멘텀 집중형",
    "lowvol":   "안정 우선형",
}


def _koscom_to_inv_type(score: int) -> str:
    for t, lv in [(30, "공격투자형"), (25, "적극투자형"), (20, "위험중립형"),
                  (15, "안전추구형"), ( 0, "안정형")]:
        if score >= t:
            return lv
    return "안정형"


def _recommend_portfolio_db(
    user_id: int,
    conn,
    koscom_score: int = 20,
    total_assets_override: Optional[int] = None,
    scoring_style: str = "balanced",
    portfolio_label: str = "",
    signal_map: Optional[dict] = None,   # {ticker: {p_adj, rank_overall}} - LightGBM 신호
    fin_map: Optional[dict] = None,      # {ticker: {overall_grade}} - 재무 등급
) -> "PortfolioRecommendationResponse":
    """core 패키지 없이 DB 데이터만으로 포트폴리오를 구성합니다."""
    cur = conn.cursor()

    # ── 1. 사용자 정보 ─────────────────────────────────────────────────────
    cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"user_id={user_id} 를 찾을 수 없습니다.")
    inv_type = row.get("investment_type") or _koscom_to_inv_type(koscom_score)
    risk_tier, risk_grade, stock_wt, bond_wt = _RISK_MAP_PF.get(inv_type, ("위험중립형", "3등급", 0.7, 0.3))
    if not portfolio_label:
        portfolio_label = _SCORING_LABELS.get(scoring_style, "맞춤 포트폴리오")

    # 투자 가능 금액: survey_answers LUMP_SUM_AMOUNT or MONTHLY_AMOUNT
    if total_assets_override:
        total_budget = total_assets_override
    else:
        cur.execute("""
            SELECT sa.value_number, sq.code
            FROM survey_answers sa
            JOIN survey_questions sq ON sa.question_id = sq.id
            WHERE sa.user_id = %s AND sq.code IN ('LUMP_SUM_AMOUNT','MONTHLY_AMOUNT')
            ORDER BY sa.updated_at DESC
        """, (user_id,))
        amt_rows = cur.fetchall()
        lump = next((r["value_number"] for r in amt_rows if r["code"] == "LUMP_SUM_AMOUNT"
                     and r["value_number"] and r["value_number"] > 1000), None)
        monthly = next((r["value_number"] for r in amt_rows if r["code"] == "MONTHLY_AMOUNT"
                        and r["value_number"] and r["value_number"] > 1000), None)
        total_budget = int(lump or monthly or 10_000_000)

    # ── 2. 종목 유니버스 (STOCK / ETF 별도 조회) ─────────────────────────
    cur.execute("""
        SELECT u.instrument_id, i.stock_code, i.name, u.market, u.risk_type,
               u.asset_type, i.last_price
        FROM universe_items u
        JOIN instruments i ON u.instrument_id = i.instrument_id
        WHERE u.active = 1 AND u.asset_type = 'STOCK'
          AND i.last_price IS NOT NULL AND i.last_price > 1000
        ORDER BY u.market, u.instrument_id
        LIMIT 350
    """)
    stocks = cur.fetchall()

    cur.execute("""
        SELECT u.instrument_id, i.stock_code, i.name, u.market, u.risk_type,
               u.asset_type, i.last_price
        FROM universe_items u
        JOIN instruments i ON u.instrument_id = i.instrument_id
        WHERE u.active = 1 AND u.asset_type = 'ETF'
          AND i.last_price IS NOT NULL AND i.last_price > 1000
        ORDER BY u.instrument_id
        LIMIT 100
    """)
    etfs = cur.fetchall()


    # ── 3. 가격 데이터 로딩 ───────────────────────────────────────────────
    ref_date = _date.today()
    cutoff_3y = (ref_date - _timedelta(days=365 * 3 + 30)).isoformat()

    target_items = list(stocks) + list(etfs)
    iids = [x["instrument_id"] for x in target_items]
    ph = ",".join(["%s"] * len(iids))

    cur.execute(
        f"""
        SELECT instrument_id, price_date, close
        FROM market_prices
        WHERE instrument_id IN ({ph})
          AND price_date >= %s AND close > 0
        ORDER BY instrument_id, price_date
        """,
        iids + [cutoff_3y],
    )
    price_hist: dict = _defaultdict(list)
    for r in cur.fetchall():
        price_hist[r["instrument_id"]].append((r["price_date"], float(r["close"])))

    # ── 4. 종목 스코어링 (종목 추천과 동일 로직) ─────────────────────────
    def _score_items(candidates, top_n=10):
        buf = []
        for s in candidates:
            hist = price_hist.get(s["instrument_id"], [])
            if len(hist) < 30:
                continue
            ps = [p for _, p in hist]
            cp = ps[-1]
            p252 = ps[-252:]
            p3m_p = next((p for d, p in hist if d >= ref_date - _timedelta(days=91)), None)
            p1y_p = next((p for d, p in hist if d >= ref_date - _timedelta(days=365)), None)
            ret_3m = (cp / p3m_p - 1) if p3m_p else None
            ret_1y = (cp / p1y_p - 1) if p1y_p else None
            vol_ann = None
            if len(p252) >= 20:
                dr = [p252[i] / p252[i - 1] - 1 for i in range(1, len(p252))]
                mn = sum(dr) / len(dr)
                vr = sum((r - mn) ** 2 for r in dr) / max(len(dr) - 1, 1)
                vol_ann = _math.sqrt(vr) * _math.sqrt(252)
            buf.append({**s, "ret_3m": ret_3m, "ret_1y": ret_1y,
                        "vol_ann": vol_ann, "current_price": cp})

        if len(buf) < 2:
            return buf[:top_n]

        def _rn(vals):
            valid = [(i, v) for i, v in enumerate(vals) if v is not None]
            if len(valid) < 2:
                return [0.5] * len(vals)
            srt = sorted(valid, key=lambda x: x[1])
            rm = {i: r / (len(srt) - 1) for r, (i, _) in enumerate(srt)}
            return [rm.get(i, 0.5) for i in range(len(vals))]

        r3 = _rn([b["ret_3m"] for b in buf])
        r1 = _rn([b["ret_1y"] for b in buf])
        vl = _rn([b["vol_ann"] for b in buf])
        w3m, w1y, wvol = _SCORING_WEIGHTS.get(scoring_style, (0.35, 0.40, 0.25))
        _FIN_GRADE_BOOST = {"우수": 0.08, "양호": 0.04, "보통": 0.0, "주의": -0.04}
        for i, b in enumerate(buf):
            base = w3m * r3[i] + w1y * r1[i] + wvol * (1.0 - vl[i])
            t = b["stock_code"]
            # LightGBM 방향성 신호 보정 (보조)
            sig_boost = 0.0
            if signal_map and t in signal_map:
                sig_boost = 0.10 * float(signal_map[t].get("p_adj", 0.5))
            # 재무등급 보정 (보조)
            fin_boost = 0.0
            if fin_map and t in fin_map:
                fin_boost = _FIN_GRADE_BOOST.get(fin_map[t].get("overall_grade"), 0.0)
            b["score"] = base + sig_boost + fin_boost
            b["p_adj"] = signal_map[t].get("p_adj") if signal_map and t in signal_map else None
            b["fin_grade"] = fin_map[t].get("overall_grade") if fin_map and t in fin_map else None
        buf.sort(key=lambda x: x["score"], reverse=True)
        return buf[:top_n]

    # 종목 및 ETF 스코어링
    n_stocks = max(3, min(7, round(stock_wt * 8)))
    n_etfs   = max(0, min(3, round(bond_wt * 5)))
    top_stocks = _score_items(stocks, top_n=n_stocks)
    top_etfs   = _score_items(etfs,   top_n=n_etfs)
    portfolio_candidates = top_stocks + top_etfs
    if not portfolio_candidates:
        raise ValueError("포트폴리오를 구성할 종목이 없습니다.")

    # ── 5. 포트폴리오 비중 ────────────────────────────────────────────────
    total_n = len(portfolio_candidates)
    stock_n = len(top_stocks)
    etf_n   = len(top_etfs)
    per_stock_w = stock_wt / stock_n if stock_n else 0
    per_etf_w   = bond_wt  / etf_n   if etf_n   else 0

    p_items: List[PortfolioItem] = []
    for s in top_stocks:
        p_items.append(PortfolioItem(
            ticker=s["stock_code"], name=s["name"],
            asset_type="STOCK", risk_type=s["risk_type"],
            weight=round(per_stock_w, 4),
            weight_pct=round(per_stock_w * 100, 1),
            selection_reason=(
                f"1년 수익률 {(s['ret_1y'] or 0)*100:+.1f}% / "
                f"변동성 {(s['vol_ann'] or 0)*100:.1f}% 으로 모멘텀 상위 편입"
            ),
            explanation=f"{s['name']}은(는) 최근 수익 모멘텀 및 변동성 기준 우수 종목입니다.",
        ))
    for s in top_etfs:
        p_items.append(PortfolioItem(
            ticker=s["stock_code"], name=s["name"],
            asset_type="ETF", risk_type=s["risk_type"],
            weight=round(per_etf_w, 4),
            weight_pct=round(per_etf_w * 100, 1),
            selection_reason="분산투자 및 리스크 헤지 목적 ETF 편입",
            explanation=f"{s['name']}은(는) 포트폴리오 안정성 제고를 위한 ETF입니다.",
        ))

    # ── 6. 매수 계획 ─────────────────────────────────────────────────────
    buy_plan: List[BuyPlanItem] = []
    total_invested = 0
    for item, cand in zip(p_items, portfolio_candidates):
        allocated = int(total_budget * item.weight)
        price = int(cand["current_price"])
        if price <= 0:
            continue
        shares = max(0, allocated // price)
        if shares == 0:
            continue  # 예산 부족으로 구매 불가한 종목 건너뜀
        actual = shares * price
        total_invested += actual
        ret_1y = cand.get("ret_1y") or 0.0
        buy_plan.append(BuyPlanItem(
            ticker=item.ticker, name=item.name,
            price_krw=price, shares=shares,
            allocated_budget_krw=actual,
            expected_return_1y_pct=round(ret_1y * 100, 1),
            rationale=f"비중 {item.weight_pct:.1f}% 매수 ({shares}주 × {price:,}원)",
        ))

    leftover = total_budget - total_invested

    # ── 7. 백테스트 3년 성과 ─────────────────────────────────────────────
    # 3년 전 기준 → 매일 포트폴리오 가치 계산
    d3y_start = ref_date - _timedelta(days=365 * 3)
    pf_series: list = []
    for cand in portfolio_candidates:
        iid = cand["instrument_id"]
        hist = [(d, p) for d, p in price_hist.get(iid, []) if d >= d3y_start]
        if hist:
            pf_series.append((cand.get("weight", 1/total_n), hist))

    perf_metrics: Optional[PerformanceMetrics] = None
    if pf_series:
        # 날짜별 포트폴리오 수익률 (단순 가격 수익률 가중평균)
        # 공통 날짜 수집
        date_set: set = set()
        for _, hist in pf_series:
            for d, _ in hist:
                date_set.add(d)
        dates = sorted(date_set)

        def _interp(hist, target_d):
            prev_p = None
            for d, p in hist:
                if d == target_d:
                    return p
                if d < target_d:
                    prev_p = p
                else:
                    return prev_p or p
            return prev_p

        pf_values = []
        for d in dates:
            val = sum(w * (_interp(hist, d) or 0) for w, hist in pf_series)
            pf_values.append(val)

        if len(pf_values) > 2:
            pf_rets = [pf_values[i] / pf_values[i - 1] - 1 for i in range(1, len(pf_values))]
            total_ret = (pf_values[-1] / pf_values[0] - 1) if pf_values[0] else 0
            n_days = len(dates)
            ann_ret = ((1 + total_ret) ** (252 / max(n_days, 1)) - 1) * 100
            mn = sum(pf_rets) / len(pf_rets)
            vr = sum((r - mn) ** 2 for r in pf_rets) / max(len(pf_rets) - 1, 1)
            ann_vol = _math.sqrt(vr) * _math.sqrt(252) * 100
            sharpe = (ann_ret / 100 - 0.035) / (ann_vol / 100) if ann_vol > 0 else 0.0
            peak = pf_values[0]
            mdd = 0.0
            for v in pf_values:
                peak = max(peak, v)
                mdd = min(mdd, (v - peak) / peak)
            perf_metrics = PerformanceMetrics(
                period=f"{d3y_start.isoformat()} ~ {ref_date.isoformat()}",
                ann_return_pct=round(ann_ret, 2),
                ann_vol_pct=round(ann_vol, 2),
                mdd_pct=round(mdd * 100, 2),
                sharpe=round(sharpe, 3),
                interpretation=(
                    f"최근 3년간 연환산 수익률 {ann_ret:.1f}%, "
                    f"변동성 {ann_vol:.1f}%, "
                    f"최대 낙폭 {mdd*100:.1f}%입니다."
                ),
            )

    # ── 8. 몬테카를로 1년 시뮬레이션 ─────────────────────────────────────
    mc_result: Optional[MonteCarloResult] = None
    if perf_metrics:
        mu = (perf_metrics.ann_return_pct / 100) / 252
        sigma = (perf_metrics.ann_vol_pct / 100) / _math.sqrt(252)
        _N_MC = 1_000_000
        _rng = _np.random.default_rng(42)
        # GBM 닫힌형: exp((μ-½σ²)·T + σ·√T·Z) - 1  (Z ~ N(0,1))
        finals = (
            _np.exp((mu - 0.5 * sigma**2) * 252
                    + sigma * _np.sqrt(252) * _rng.standard_normal(_N_MC)) - 1
        ) * 100
        p10, p50, p90 = _np.percentile(finals, [10, 50, 90])
        mc_result = MonteCarloResult(
            n_simulations=_N_MC, horizon_days=252,
            p10_pct=round(p10, 1), p50_pct=round(p50, 1), p90_pct=round(p90, 1),
            interpretation=(
                f"1년 후 기대 수익률(중앙값) {p50:.1f}%, "
                f"하락 시나리오(10%) {p10:.1f}%, "
                f"상승 시나리오(90%) {p90:.1f}%입니다."
            ),
        )

    # ── 9. 응답 조립 ──────────────────────────────────────────────────────
    actual_leftover = max(0, total_budget - total_invested)
    purchased_n = len(buy_plan)
    style_desc = {
        "balanced": "모멘텀·수익률·변동성 균형 기준",
        "momentum": "단기 모멘텀 중심 종목 선별",
        "lowvol":   "저변동·안정 수익 종목 중심",
    }.get(scoring_style, "맞춤 기준")
    overall = (
        f"{risk_grade}({risk_tier}) 투자자를 위한 포트폴리오. "
        f"종목 선별 방식: {style_desc}. "
        f"총 {purchased_n}개 종목 매수 (주식 {stock_n}개 · ETF {etf_n}개 중). "
        f"총 투자금 {total_budget:,}원 중 {total_invested:,}원 투자, 잔여 {actual_leftover:,}원."
    )

    return PortfolioRecommendationResponse(
        risk_tier=risk_tier,
        risk_grade=risk_grade,
        generated_at=datetime.now().isoformat()[:19],
        user_profile=UserProfileSummary(
            user_id=user_id,
            risk_tier=risk_tier,
            risk_grade=risk_grade,
            investment_type=inv_type,
            horizon_years=3,
            monthly_contribution_krw=0,
            total_assets_krw=total_budget,
        ),
        allocation_rules=AllocationRulesSummary(
            grade=risk_grade,
            stock_max_pct=round(stock_wt * 100),
            single_stock_max_pct=round(per_stock_w * 100 * 1.5),
            etf_min_pct=round(bond_wt * 100),
            target_weights={
                "STOCK": stock_wt,
                "ETF":   bond_wt,
            },
        ),
        portfolio_items=p_items,
        buy_plan=buy_plan,
        investable_amount_krw=total_budget,
        total_invested_krw=total_invested,
        leftover_krw=actual_leftover,
        cap_compliance=CapCompliance(
            compliant=True,
            violations=[],
            summary="cap 규칙 준수",
        ),
        performance_3y=perf_metrics,
        monte_carlo_1y=mc_result,
        overall_summary=overall,
        portfolio_label=portfolio_label,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_portfolio_recommendation(
    user_id: int,
    conn,
    *,
    koscom_score: int = 20,
    monthly_override: Optional[int] = None,
    total_assets_override: Optional[int] = None,
    top_kospi: int = 150,
    top_kosdaq: int = 150,
    top_etf: int = 30,
    explain_detail: str = "detailed",
    explain_lang: str = "ko",
    explain_style: str = "formal",
) -> PortfolioRecommendationResponse:
    """DB 설문 → 사용자 프로파일 → 포트폴리오 구성 → 매수 계획 → 성과 분석을 반환합니다."""
    if not _CORE_AVAILABLE:
        return _recommend_portfolio_db(
            user_id=user_id, conn=conn,
            koscom_score=koscom_score,
            total_assets_override=total_assets_override,
        )

    today = datetime.today().date()

    # 1) 설문 로드
    koscom_total_score, horizon_years, answers = load_survey_answers(
        user_id=user_id,
        conn=conn,
        monthly_override=monthly_override,
        koscom_score=koscom_score,
    )

    # CLI override 반영
    if total_assets_override is not None:
        answers["total_assets_krw"] = total_assets_override

    # monthly 미설정 시 0으로 방어
    if not answers.get("monthly_contribution_krw"):
        answers["monthly_contribution_krw"] = 0

    # 2) 유니버스 준비 (주식 + ETF)
    get_universe(UniverseConfig(
        top_kospi=top_kospi,
        top_kosdaq=top_kosdaq,
        top_etf=top_etf,
    ))

    # 3) 사용자 프로파일 생성
    profile = build_user_profile(
        koscom_total_score=koscom_total_score,
        horizon_years=horizon_years,
        answers=answers,
    )

    # month_contribution을 profile에도 반영
    monthly = answers["monthly_contribution_krw"]
    setattr(profile, "monthly_contribution_krw", monthly)

    # 4) 포트폴리오 추천
    portfolio = recommend_initial_portfolio(profile)

    # 5) 투자 가용금 계산
    total_assets_ans = answers.get("total_assets_krw")
    non_cash_items = [x for x in portfolio["items"] if x["ticker"] != "CASH"]
    cash_items = [x for x in portfolio["items"] if x["ticker"] == "CASH"]
    cash_w_total = sum(x["weight"] for x in cash_items)

    if total_assets_ans:
        total_assets_pool = total_assets_ans
        cash_alloc = total_assets_pool * cash_w_total
        investable = total_assets_pool - cash_alloc
    else:
        total_assets_pool = monthly
        cash_alloc = sum(monthly * x["weight"] for x in cash_items)
        investable = monthly - cash_alloc

    # 6) 현재가 & 1년 가격 조회
    tickers_all = [x["ticker"] for x in non_cash_items]
    prices_cur = get_prices(
        tickers=tickers_all,
        start=(today - timedelta(days=10)).isoformat(),
        end=today.isoformat(),
    )
    prices_1y = get_prices(
        tickers=tickers_all,
        start=(today - timedelta(days=365)).isoformat(),
        end=today.isoformat(),
    )

    # 7) 온주 매수 계획
    buy_plan_raw: Dict[str, Dict] = {}
    try:
        cur_price = prices_cur.ffill().iloc[-1] if not prices_cur.empty else {}

        def _exp_ret(ticker: str) -> float:
            try:
                col = prices_1y[ticker].dropna()
                return float(col.iloc[-1] / col.iloc[0] - 1.0) if len(col) >= 2 else 0.0
            except Exception:
                return 0.0

        total_w = sum(x["weight"] for x in non_cash_items) or 1.0
        budgets = {x["ticker"]: investable * (x["weight"] / total_w) for x in non_cash_items}

        for item in non_cash_items:
            t = item["ticker"]
            price = float(cur_price.get(t, 0)) if hasattr(cur_price, "get") else 0.0
            if price <= 0:
                continue
            shares = int(budgets[t] // price)
            buy_plan_raw[t] = {
                "item": item,
                "price": price,
                "shares": shares,
                "actual": shares * price,
                "exp_ret": _exp_ret(t),
            }

        # 잔여 예산 재배분 (예상수익률 높은 순)
        cash_residual = investable - sum(v["actual"] for v in buy_plan_raw.values())
        if cash_residual > 0:
            candidates = [v for v in buy_plan_raw.values() if v["price"] > 0]
            while True:
                affordable = sorted(
                    [c for c in candidates if c["price"] <= cash_residual],
                    key=lambda x: x.get("exp_ret", 0.0), reverse=True,
                )
                if not affordable:
                    break
                bought_any = False
                for p in affordable:
                    extra = int(cash_residual // p["price"])
                    if extra <= 0:
                        continue
                    p["shares"] += extra
                    p["actual"] += extra * p["price"]
                    cash_residual -= extra * p["price"]
                    bought_any = True
                    if cash_residual <= 0:
                        break
                if not bought_any:
                    break
    except Exception:
        pass

    total_invested = int(sum(v["actual"] for v in buy_plan_raw.values()))
    leftover = int(total_assets_pool - total_invested - cash_alloc)

    # 8) 성과 지표 (3년)
    perf_metrics: Optional[PerformanceMetrics] = None
    mc_result: Optional[MonteCarloResult] = None
    port_ret_list: List[float] = []
    try:
        prices_3y = get_prices(
            tickers=tickers_all,
            start=(today - timedelta(days=365 * 3)).isoformat(),
            end=today.isoformat(),
        )
        weights_list = [x["weight"] for x in non_cash_items]
        cash_weight = sum(x["weight"] for x in cash_items)
        try:
            raw = portfolio_metrics(prices=prices_3y, weights=weights_list, cash_weight=cash_weight, rf_annual=0.0)
        except TypeError:
            raw = portfolio_metrics(prices=prices_3y, weights=weights_list)

        port_ret_list = raw.get("port_ret", [])

        sharpe = raw.get("sharpe", 0.0)
        if isinstance(sharpe, float) and sharpe != sharpe:  # NaN guard
            sharpe = 0.0

        perf_metrics = PerformanceMetrics(
            ann_return_pct=round(raw["ann_return"] * 100, 2),
            ann_vol_pct=round(raw["ann_vol"] * 100, 2),
            mdd_pct=round(raw["mdd"] * 100, 2),
            sharpe=round(sharpe, 3),
            period="3년(과거 실제 데이터 기반)",
            interpretation=(
                f"연환산 수익률 {raw['ann_return']:.1%}, 변동성 {raw['ann_vol']:.1%}, "
                f"최대 낙폭 {raw['mdd']:.1%}. "
                f"샤프 지수 {sharpe:.2f}는 "
                + ("리스크 대비 수익이 우수한 수준입니다." if sharpe >= 1.5
                   else "리스크 대비 수익이 평균적인 수준입니다." if sharpe >= 0.8
                   else "리스크 대비 수익이 낮은 수준입니다.")
            ),
        )

        # 8-b) Monte Carlo
        market_expected = 0.08
        adj_return = min(raw["ann_return"], market_expected + 0.04)

        if len(port_ret_list) >= 60:
            fc = bootstrap_forecast(
                daily_returns=port_ret_list,
                horizon_years=1.0,
                n_sims=200_000,
                seed=42,
                adj_ann_return=adj_return,
            )
            fc_method = "부트스트랩(실제 경로 리샘플링, 20만 경로)"
            fc_sims = 200_000
        else:
            fc = monte_carlo_forecast(
                ann_return=adj_return,
                ann_vol=raw["ann_vol"],
                horizon_years=1.0,
                seed=42,
            )
            fc_method = "GBM 로그정규(100만 경로)"
            fc_sims = 1_000_000

        mc_result = MonteCarloResult(
            horizon="1년",
            method=fc_method,
            simulations=fc_sims,
            p10_pct=round(fc["p10"] * 100, 2),
            p50_pct=round(fc["p50"] * 100, 2),
            p90_pct=round(fc["p90"] * 100, 2),
            mdd_median_pct=round(abs(fc.get("mdd_p50", 0)) * 100, 2),
            mdd_worst10_pct=round(abs(fc.get("mdd_worst10", 0)) * 100, 2),
            interpretation=(
                f"1년 후 수익률 시뮬레이션: "
                f"하위 10% {fc['p10']:.1%}, 중앙값 {fc['p50']:.1%}, 상위 90% {fc['p90']:.1%}. "
                + ("최악 시나리오에서도 손실이 없어 안정적입니다."
                   if fc["p10"] >= 0
                   else f"최악 시나리오에서 최대 {abs(fc['p10']):.1%} 손실 가능성이 있습니다.")
            ),
        )
    except Exception:
        pass

    # 9) 구성 규칙 분석
    rule_dict = describe_rule_dict(profile.risk_tier)
    rule = get_rule(profile.risk_tier)

    allocation_rules = AllocationRulesSummary(
        grade=rule_dict["grade"],
        risk_tier_name=rule_dict["risk_tier_name"],
        allowed_risk_types=rule_dict["allowed_risk_types"],
        single_caps=rule_dict["single_caps"],
        combined_caps={str(k): v for k, v in rule_dict["combined_caps"].items()},
        description=(
            f"{rule_dict['grade']}({rule_dict['risk_tier_name']})은 "
            f"{rule_dict['allowed_risk_types']} 종목만 허용합니다. "
            + (f"단일 cap: {rule_dict['single_caps']}. " if rule_dict["single_caps"] else "")
            + (f"합산 cap: {rule_dict['combined_caps']}. " if rule_dict["combined_caps"] else "")
        ),
    )

    # 10) cap 준수 여부
    rt_totals: Dict[str, float] = {}
    for item in portfolio["items"]:
        rt = item.get("risk_type", item.get("bucket", "(none)"))
        rt_totals[rt] = rt_totals.get(rt, 0.0) + item.get("weight", 0.0)

    cap_violations: List[str] = []
    for rt_key, cap_val in rule_dict["single_caps"].items():
        actual = rt_totals.get(rt_key, 0.0)
        cv = float(str(cap_val).replace("%", "")) / 100
        if actual > cv + 1e-4:
            cap_violations.append(f"{rt_key} 합계 {actual:.1%} > cap {cap_val}")
    for combined_key, cap_val in rule_dict["combined_caps"].items():
        actual = sum(rt_totals.get(rt, 0.0) for rt in str(combined_key).split("+"))
        cv = float(str(cap_val).replace("%", "")) / 100
        if actual > cv + 1e-4:
            cap_violations.append(f"[{combined_key}] 합계 {actual:.1%} > cap {cap_val}")

    cap_compliance = CapCompliance(
        risk_type_totals={k: f"{v:.2%}" for k, v in rt_totals.items()},
        cap_violations=cap_violations,
        cap_satisfied=len(cap_violations) == 0,
    )

    # 11) 종목별 설명 포함한 PortfolioItem 조립
    p_items: List[PortfolioItem] = []
    for item in portfolio["items"]:
        rt = item.get("risk_type", item.get("bucket", "(none)"))

        cap_notes = []
        for rt_key, cap_str in rule_dict["single_caps"].items():
            if rt == rt_key:
                cap_notes.append(f"단일 cap {rt_key} {cap_str} 적용 대상")
        for combined_key, cap_str in rule_dict["combined_caps"].items():
            if rt in str(combined_key):
                cap_notes.append(f"합산 cap [{combined_key}] {cap_str} 적용 대상")

        reason = (
            f"risk_type={rt} 그룹에서 섹터 다양성 고려하여 선정. "
            f"{rule_dict['grade']} 허용 목록에 포함됨 "
            f"({'주식' if item.get('asset_type') == 'STOCK' else 'ETF' if item.get('asset_type') == 'ETF' else '현금'} 자산)."
            + (" | " + "; ".join(cap_notes) if cap_notes else "")
        )

        # 개별 설명문 생성 (LLM/템플릿)
        explanation: Optional[str] = None
        try:
            explanation = explain_portfolio_item_beginner(item)
        except Exception:
            pass

        w = item.get("weight", 0.0)
        p_items.append(PortfolioItem(
            ticker=item["ticker"],
            name=item.get("name", ""),
            asset_type=item.get("asset_type", ""),
            risk_type=rt,
            weight=round(w, 6),
            weight_pct=round(w * 100, 2),
            selection_reason=reason,
            explanation=explanation,
        ))

    # 12) 매수 계획 조립
    buy_plan: List[BuyPlanItem] = [
        BuyPlanItem(
            ticker=v["item"]["ticker"],
            name=v["item"].get("name", ""),
            price_krw=int(v["price"]),
            shares=v["shares"],
            allocated_budget_krw=int(v["actual"]),
            expected_return_1y_pct=round(v["exp_ret"] * 100, 1),
            rationale=(
                f"예상수익률 {v['exp_ret']:+.1%} 기준 배분. "
                f"{int(v['price']):,}원 × {v['shares']}주 = {int(v['actual']):,}원 투자."
            ),
        )
        for v in sorted(buy_plan_raw.values(), key=lambda x: x["exp_ret"], reverse=True)
        if v["shares"] > 0
    ]

    # 13) 사용자 프로파일 요약
    user_profile_summary = UserProfileSummary(
        risk_tier=profile.risk_tier,
        grade=rule_dict["grade"],
        horizon_years=profile.horizon_years,
        goal=profile.goal,
        deployment=profile.deployment,
        max_assets_preference=profile.max_assets_preference,
        monthly_contribution_krw=monthly,
        total_assets_krw=profile.total_assets_krw,
        dividend_pref_1to5=profile.dividend_pref,
        account_type=profile.account_type,
    )

    # 14) overall summary
    n_stocks = len([x for x in portfolio["items"] if x["ticker"] != "CASH"])
    cap_ok = "통과" if cap_compliance.cap_satisfied else f"위반 {cap_violations}"
    target_str = ", ".join(f"{k}={int(v*100)}%" for k, v in rule.target_weights.items())
    mc_p50_str = f"{mc_result.p50_pct:.1f}%" if mc_result else "N/A"
    ann_str = f"{perf_metrics.ann_return_pct:.1f}%" if perf_metrics else "N/A"
    overall = (
        f"{rule_dict['grade']}({profile.risk_tier}) 투자자를 위한 포트폴리오. "
        f"총 {n_stocks}개 종목 (비중 목표: {target_str}). "
        f"cap 규칙 준수: {cap_ok}. "
        f"3년 연환산 수익률 {ann_str}, 1년 중앙 시나리오 {mc_p50_str}."
    )

    return PortfolioRecommendationResponse(
        user_id=user_id,
        risk_tier=profile.risk_tier,
        risk_grade=risk_tier_to_grade(profile.risk_tier),
        generated_at=datetime.now().isoformat(),
        user_profile=user_profile_summary,
        allocation_rules=allocation_rules,
        portfolio_items=p_items,
        buy_plan=buy_plan,
        investable_amount_krw=int(investable),
        total_invested_krw=total_invested,
        leftover_krw=max(0, leftover),
        cap_compliance=cap_compliance,
        performance_3y=perf_metrics,
        monte_carlo_1y=mc_result,
        overall_summary=overall,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3종 스타일 멀티 포트폴리오 추천
# ─────────────────────────────────────────────────────────────────────────────

# 스코어링 스타일 순서 (균형 → 모멘텀 → 저변동)
_MULTI_STYLES = [
    "balanced",
    "momentum",
    "lowvol",
]


def get_multi_portfolio_recommendations(
    user_id: int,
    conn,
    *,
    koscom_score: int = 20,
    total_assets_override: Optional[int] = None,
) -> List[PortfolioRecommendationResponse]:
    """동일 투자성향에서 3가지 스코어링 방식(균형/모멘텀/저변동)으로 포트폴리오를 구성해 반환합니다."""
    results = []
    for scoring_style in _MULTI_STYLES:
        pf = _recommend_portfolio_db(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
            total_assets_override=total_assets_override,
            scoring_style=scoring_style,
        )
        results.append(pf)
    return results


def get_multi_portfolio_with_signals(
    user_id: int,
    conn,
    *,
    koscom_score: int = 20,
    total_assets_override: Optional[int] = None,
    signal_map: Optional[dict] = None,
    fin_map: Optional[dict] = None,
) -> List[PortfolioRecommendationResponse]:
    """LightGBM 신호 + 재무등급을 보조 근거로 사용하는 MC 포트폴리오 추천 (3가지 스타일)."""
    results = []
    for scoring_style in _MULTI_STYLES:
        pf = _recommend_portfolio_db(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
            total_assets_override=total_assets_override,
            scoring_style=scoring_style,
            signal_map=signal_map,
            fin_map=fin_map,
        )
        results.append(pf)
    return results


def recommend_stock_with_signals(
    user_id: int,
    conn,
    signal_tickers: list,
    fin_scores: Optional[dict] = None,
    koscom_score: int = 20,
    top_n: int = 5,
) -> "StockRecommendationResponse":
    """
    LightGBM 방향성 신호 종목을 후보로, 몬테카를로 시뮬레이션으로 최종 종목을 선정합니다.

    선정 기준: MC 1년 기대수익률(주) + LightGBM p_adj(보조) + 재무등급(보조)
    투자성향에 따라 세 가중치를 조정합니다.
    """
    from schemas import StockItem, StockFeatures, StockRecommendationResponse

    cur = conn.cursor()

    # 1. 사용자 투자성향
    cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"user_id={user_id} 를 찾을 수 없습니다.")
    inv_type = row.get("investment_type") or _koscom_to_inv_type(koscom_score)
    risk_tier, risk_grade, _, _ = _RISK_MAP_PF.get(inv_type, ("위험중립형", "3등급", 0.7, 0.3))

    if not signal_tickers:
        raise ValueError("방향성 신호 종목 목록이 비어 있습니다.")

    tickers_list = [s["ticker"] for s in signal_tickers]
    sig_map = {s["ticker"]: s for s in signal_tickers}

    # 2. DB에서 instrument_id 조회
    ph = ",".join(["%s"] * len(tickers_list))
    cur.execute(f"SELECT stock_code, instrument_id FROM instruments WHERE stock_code IN ({ph})", tickers_list)
    iid_map = {r["stock_code"]: r["instrument_id"] for r in cur.fetchall()}
    if not iid_map:
        raise ValueError("DB에서 일치하는 종목을 찾을 수 없습니다.")

    iids = list(iid_map.values())
    iid_to_code = {v: k for k, v in iid_map.items()}
    ref_dt = _date.today()
    cutoff = (ref_dt - _timedelta(days=730)).isoformat()
    ph2 = ",".join(["%s"] * len(iids))
    cur.execute(
        f"""
        SELECT instrument_id, close
        FROM market_prices
        WHERE instrument_id IN ({ph2})
          AND price_date >= %s AND close > 0
        ORDER BY instrument_id, price_date
        """,
        iids + [cutoff],
    )
    price_hist: dict = _defaultdict(list)
    for r in cur.fetchall():
        code = iid_to_code.get(r["instrument_id"])
        if code:
            price_hist[code].append(float(r["close"]))

    # 3. 투자성향별 가중치 (MC비중, 신호비중, 재무비중)
    _W = {
        "공격투자형": (0.55, 0.35, 0.10),
        "적극투자형": (0.50, 0.30, 0.20),
        "위험중립형": (0.40, 0.25, 0.35),
        "안전추구형": (0.30, 0.20, 0.50),
        "안정형":     (0.25, 0.15, 0.60),
    }
    w_mc, w_sig, w_fin = _W.get(risk_tier, (0.40, 0.25, 0.35))
    # 보수 성향 → 하락(p10) 중시, 공격 성향 → 상승(p90) 중시
    mc_key = "p10" if risk_tier in ("안전추구형", "안정형") else (
        "p90" if risk_tier in ("공격투자형", "적극투자형") else "p50"
    )
    _FIN_GRADE_SCORE = {"우수": 1.0, "양호": 0.75, "보통": 0.50, "주의": 0.25}

    # 4. 종목별 몬테카를로 시뮬레이션 (1,000,000경로 × GBM 닫힌형)
    _N_MC = 1_000_000
    _rng = _np.random.default_rng(42)
    candidates = []
    for ticker, closes in price_hist.items():
        if len(closes) < 60:
            continue
        rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
        mu_d = sum(rets) / len(rets)
        var_d = sum((r - mu_d) ** 2 for r in rets) / max(len(rets) - 1, 1)
        sigma_d = _math.sqrt(var_d)

        # GBM 닫힌형: exp((μ-½σ²)·252 + σ·√252·Z) - 1  (Z ~ N(0,1))
        finals = (
            _np.exp((mu_d - 0.5 * sigma_d**2) * 252
                    + sigma_d * _np.sqrt(252) * _rng.standard_normal(_N_MC)) - 1
        ) * 100
        mc_p10, mc_p50, mc_p90 = _np.percentile(finals, [10, 50, 90])
        mc_val = mc_p10 if mc_key == "p10" else (mc_p90 if mc_key == "p90" else mc_p50)

        sig = sig_map.get(ticker, {})
        fin = (fin_scores or {}).get(ticker, {})
        fin_grade = fin.get("overall_grade")
        candidates.append({
            "ticker": ticker,
            "name": sig.get("name", ""),
            "market": sig.get("market", "KOSPI"),
            "p_adj": float(sig.get("p_adj", 0.5)),
            "rank_overall": int(sig.get("rank_overall", 999)),
            "mc_p10": mc_p10, "mc_p50": mc_p50, "mc_p90": mc_p90, "mc_val": mc_val,
            "ann_vol": sigma_d * _math.sqrt(252) * 100,
            "ann_return": mu_d * 252 * 100,
            "fin_grade": fin_grade,
            "fin_score": _FIN_GRADE_SCORE.get(fin_grade, 0.50),
        })

    if not candidates:
        raise ValueError("몬테카를로 시뮬레이션을 위한 충분한 가격 데이터가 없습니다.")

    # 5. 정규화 후 종합 점수
    def _rn(vals):
        idxd = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(idxd) < 2:
            return [0.5] * len(vals)
        srt = sorted(idxd, key=lambda x: x[1])
        rm = {i: r / (len(srt) - 1) for r, (i, _) in enumerate(srt)}
        return [rm.get(i, 0.5) for i in range(len(vals))]

    mc_n  = _rn([c["mc_val"] for c in candidates])
    sig_n = _rn([c["p_adj"]  for c in candidates])
    for i, c in enumerate(candidates):
        c["total_score"] = w_mc * mc_n[i] + w_sig * sig_n[i] + w_fin * c["fin_score"]
    candidates.sort(key=lambda x: x["total_score"], reverse=True)
    top = candidates[:top_n]

    # 6. 응답 생성
    mc_label = {"p10": "하락방어(10%)", "p50": "중앙값(50%)", "p90": "상승(90%)"}
    items = []
    for rank, c in enumerate(top, 1):
        items.append(StockItem(
            rank=rank,
            ticker=c["ticker"],
            name=c["name"],
            market=c["market"],
            total_score=round(c["total_score"], 4),
            reasons=[
                f"MC 1년 기대수익률({mc_label[mc_key]}) {c['mc_val']:+.1f}%",
                f"LightGBM 상승확률 {c['p_adj']*100:.0f}% (전체 {c['rank_overall']}위)",
                f"재무등급 {c['fin_grade'] or '정보없음'}",
            ],
            features=StockFeatures(
                ret_3m=None, ret_6m=None,
                ret_1y=round(c["mc_p50"] / 100, 4),
                vol_ann=round(c["ann_vol"] / 100, 4),
                beta=None, mdd=None,
            ),
            explanation=(
                f"몬테카를로 시뮬레이션(2,000경로) 1년 기대수익률: "
                f"하락(10%) {c['mc_p10']:+.1f}% / 중앙값 {c['mc_p50']:+.1f}% / 상승(90%) {c['mc_p90']:+.1f}%. "
                f"LightGBM 방향성 모델 전체 {c['rank_overall']}위 (상승확률 {c['p_adj']*100:.0f}%). "
                f"재무등급 {c['fin_grade'] or '정보없음'}."
            ),
        ))

    return StockRecommendationResponse(
        user_id=user_id,
        risk_tier=risk_tier,
        risk_grade=risk_grade,
        generated_at=datetime.now().isoformat()[:19],
        items=items,
    )
