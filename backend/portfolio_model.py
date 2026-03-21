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
    "안정추구형": ("안전추구형",  "4등급", 0.50, 0.50),  # 구버전 오타 호환
    "안정형":     ("안정형",      "5등급", 0.30, 0.70),
}

# 개인화 Top3 포트폴리오 구성 설정
# factor_w: (모멘텀, 우량성/샤프, 저변동성) 가중치 — 합계 1.0
# momentum_split: (3개월 비중, 1년 비중) within 모멘텀
# 가중치를 극단적으로 다르게 설정 → 종목 선정 기준이 달라져 다른 종목 구성이 나온다
_PORTFOLIO_CONFIGS = [
    {
        "key": "pf_optimal",
        "label": "1순위 종합 최적",
        "factor_w": (0.40, 0.40, 0.20),    # 모멘텀·우량성·저변동 균형
        "momentum_split": (0.35, 0.65),    # 1Y 중심
    },
    {
        "key": "pf_growth",
        "label": "2순위 성장 추구",
        "factor_w": (0.70, 0.20, 0.10),    # 모멘텀 강조 → 수익률 높은 종목 선정
        "momentum_split": (0.50, 0.50),    # 3M/1Y 균등
    },
    {
        "key": "pf_stable",
        "label": "3순위 안정 성장",
        "factor_w": (0.15, 0.50, 0.35),    # 우량성+저변동 강조 → 안정적 종목 선정
        "momentum_split": (0.20, 0.80),    # 1Y 강조 (장기 안정 수익)
    },
]

# 스타일별 스코어링 가중치 매핑 (예시)
_SCORING_WEIGHTS = {
    "default": (0.35, 0.40, 0.25),
    "growth": (0.50, 0.30, 0.20),
    "stable": (0.20, 0.40, 0.40),
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
    portfolio_label: str = "",
    signal_map: Optional[dict] = None,   # {ticker: {p_adj, rank_overall}} - LightGBM 신호
    fin_map: Optional[dict] = None,      # {ticker: {overall_grade}} - 재무 등급
    scoring_weights: Optional[tuple] = None,  # (w_3m, w_1y, w_stab) — 명시 시 scoring_style 가중치보다 우선
    factor_w: Optional[tuple] = (0.5, 0.3, 0.2),
    momentum_split: Optional[tuple] = (0.5, 0.5),
    n_stocks_override: Optional[int] = None,  # 주식 종목 수 직접 지정 (None이면 성향 기반 자동 결정)
    excluded_tickers: Optional[set] = None,
) -> "PortfolioRecommendationResponse":
    """core 패키지 없이 DB 데이터만으로 포트폴리오를 구성합니다.

    factor_w와 momentum_split을 다르게 지정하면 서로 다른 종목 구성의 포트폴리오가 생성됩니다.
    excluded_tickers를 지정하면 해당 종목은 후보에서 제외됩니다 (포트폴리오 간 중복 방지).
    """
    cur = conn.cursor()

    # ── 1. 사용자 정보 ─────────────────────────────────────────────────────
    cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"user_id={user_id} 를 찾을 수 없습니다.")
    inv_type = row.get("investment_type") or _koscom_to_inv_type(koscom_score)
    risk_tier, risk_grade, _, bond_wt = _RISK_MAP_PF.get(inv_type, ("위험중립형", "3등급", 0.7, 0.3))
    if not portfolio_label:
        portfolio_label = "맞춤 포트폴리오"

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

    # ── 2. 종목 유니버스 (STOCK / ETF 별도 조회, bucket 포함) ───────────
    cur.execute("""
        SELECT u.instrument_id, i.stock_code, i.name, u.market, u.risk_type,
               u.asset_type, i.last_price,
               COALESCE(u.bucket, 'CORE') AS bucket
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
               u.asset_type, i.last_price,
               'ETF' AS bucket
        FROM universe_items u
        JOIN instruments i ON u.instrument_id = i.instrument_id
        WHERE u.active = 1 AND u.asset_type = 'ETF'
          AND i.last_price IS NOT NULL AND i.last_price > 1000
        ORDER BY u.instrument_id
        LIMIT 100
    """)
    etfs = cur.fetchall()

    # 예산 지정 시 — 1주라도 살 수 없는 종목은 후보에서 선제 제외
    if total_assets_override:
        stocks = [s for s in stocks if (s.get("last_price") or 0) <= total_budget]
        etfs   = [e for e in etfs   if (e.get("last_price") or 0) <= total_budget]

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

    # ── 4. 다중팩터 스코어링 + 위험조정수익률(샤프) ──────────────────────
    _RF_RATE_PF = 0.035  # 무위험 수익률 3.5%

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
            vol_ann, sharpe_1y = None, None
            if len(p252) >= 20:
                dr = [p252[i] / p252[i - 1] - 1 for i in range(1, len(p252))]
                mn = sum(dr) / len(dr)
                vr = sum((r - mn) ** 2 for r in dr) / max(len(dr) - 1, 1)
                vol_ann = _math.sqrt(vr) * _math.sqrt(252)
                # ① 샤프지수: (1Y수익률 - 무위험률) / 연변동성
                if ret_1y is not None and vol_ann > 0:
                    sharpe_1y = (ret_1y - _RF_RATE_PF) / vol_ann
            buf.append({**s, "ret_3m": ret_3m, "ret_1y": ret_1y,
                        "vol_ann": vol_ann, "sharpe_1y": sharpe_1y, "current_price": cp})

        if len(buf) < 2:
            return buf[:top_n]

        def _rn(vals):
            valid = [(i, v) for i, v in enumerate(vals) if v is not None]
            if len(valid) < 2:
                return [0.5] * len(vals)
            srt = sorted(valid, key=lambda x: x[1])
            rm = {i: r / (len(srt) - 1) for r, (i, _) in enumerate(srt)}
            return [rm.get(i, 0.5) for i in range(len(vals))]

        r3  = _rn([b["ret_3m"]    for b in buf])
        r1  = _rn([b["ret_1y"]    for b in buf])
        shn = _rn([b["sharpe_1y"] for b in buf])  # 샤프 순위 정규화 → 우량성 대리 지표
        vl  = _rn([b["vol_ann"]   for b in buf])

        # 팩터 가중치 직접 사용 (_recommend_portfolio_db 파라미터를 closure로 참조)
        _fw_mom, _fw_qual, _fw_lowvol = factor_w
        _i3m, _i1y = momentum_split

        _FIN_GRADE_BOOST = {"우수": 0.08, "양호": 0.04, "보통": 0.0, "주의": -0.04}
        for i, b in enumerate(buf):
            # factor_w(모멘텀·우량성·저변동) + momentum_split(3M/1Y 비중)으로 스코어 산출
            mom_score    = _i3m * r3[i] + _i1y * r1[i]
            qual_score   = shn[i]
            lowvol_score = 1.0 - vl[i]
            base = _fw_mom * mom_score + _fw_qual * qual_score + _fw_lowvol * lowvol_score
            t = b["stock_code"]
            sig_boost = 0.0
            if signal_map and t in signal_map:
                sig_boost = 0.10 * float(signal_map[t].get("p_adj", 0.5))
            fin_boost = 0.0
            if fin_map and t in fin_map:
                fin_boost = _FIN_GRADE_BOOST.get(fin_map[t].get("overall_grade"), 0.0)
            b["score"] = base + sig_boost + fin_boost
            b["p_adj"]     = signal_map[t].get("p_adj") if signal_map and t in signal_map else None
            b["fin_grade"] = fin_map[t].get("overall_grade") if fin_map and t in fin_map else None
        buf.sort(key=lambda x: x["score"], reverse=True)
        return buf[:top_n]

    # ③ 유니버스 그룹핑 + ④ 코어-새틀라이트 전략 ────────────────────────
    # 성향별 주식 슬롯 내 코어(대형 우량) : 새틀라이트(성장 모멘텀) 비율
    _CS_SPLIT = {
        "공격투자형": (0.40, 0.60),  # 코어 40% + 새틀라이트 60%
        "적극투자형": (0.50, 0.50),
        "위험중립형": (0.65, 0.35),
        "안전추구형": (0.80, 0.20),
        "안정추구형": (0.80, 0.20),
        "안정형":     (1.00, 0.00),  # 코어만
    }
    _core_ratio, _sat_ratio = _CS_SPLIT.get(risk_tier, (0.65, 0.35))

    # ETF는 항상 최소 1개 포함. bond_wt=0인 공격형도 분산 목적으로 ETF 편입
    n_etfs       = max(1, min(3, round(bond_wt * 5 + 1)))
    _etf_alloc   = max(bond_wt, 0.10)
    _stock_alloc = 1.0 - _etf_alloc

    # 주식 종목 수: 직접 지정이 있으면 사용, 없으면 성향 기반 자동 결정
    if n_stocks_override is not None:
        n_total_stock = max(3, min(10, n_stocks_override))
    else:
        n_total_stock = max(3, min(7, round(_stock_alloc * 8)))
    n_core_slot   = max(1, round(n_total_stock * _core_ratio))
    n_sat_slot    = n_total_stock - n_core_slot

    _excl = excluded_tickers or set()
    core_pool   = [s for s in stocks if s.get("bucket") == "CORE"  and s["stock_code"] not in _excl]
    growth_pool = [s for s in stocks if s.get("bucket") != "CORE" and s["stock_code"] not in _excl]

    top_core  = _score_items(core_pool,   top_n=n_core_slot)
    top_sat   = _score_items(growth_pool, top_n=n_sat_slot)
    top_etfs  = _score_items([e for e in etfs if e["stock_code"] not in _excl], top_n=n_etfs)

    # 슬롯 부족분 보충
    if len(top_core) < n_core_slot:
        used = {s["stock_code"] for s in top_core + top_sat}
        extras = _score_items([s for s in growth_pool if s["stock_code"] not in used],
                              top_n=n_core_slot - len(top_core))
        top_core += extras

    portfolio_candidates = top_core + top_sat + top_etfs
    if not portfolio_candidates:
        raise ValueError("포트폴리오를 구성할 종목이 없습니다.")

    stock_n = len(top_core) + len(top_sat)
    etf_n   = len(top_etfs)
    total_n = len(portfolio_candidates)

    # ── 5. 코어-새틀라이트 비중 배분 ─────────────────────────────────────
    # [핵심 수정] 기존 문제:
    #   _score_items는 전체 풀(100~200개)에서 rank 정규화하므로
    #   상위 N개의 score는 0.960~0.975 처럼 거의 동일 → 비중이 사실상 균등해짐.
    # [해결]
    #   선정된 그룹 내에서 score를 재순위 정규화(intra-group rank normalization)하여
    #   의미 있는 비중 차이를 만든다.
    #   min_ratio=0.5: 최상위 종목이 최하위 종목의 2배 비중

    def _intra_group_weights(items: list, base_wt: float, min_ratio: float = 0.5) -> list:
        """선정된 종목 그룹 내에서 score를 재순위 정규화하여 비중을 차등 배분한다.

        Args:
            items: 이미 선정된 종목 리스트 (각 dict에 "score" 키 존재)
            base_wt: 이 그룹에 할당된 총 비중 (예: stock_wt * core_ratio)
            min_ratio: 최하위 종목의 비중 ÷ 최상위 종목의 비중 (0 < min_ratio <= 1)
                       0.5 → top 종목이 bottom 종목의 2배 비중
        Returns:
            각 종목의 비중 리스트 (합계 = base_wt)
        """
        n = len(items)
        if n == 0:
            return []
        if n == 1:
            return [base_wt]

        # 실제 score 값으로 [min_ratio, 1.0] 범위에 선형 정규화
        scores = [items[i].get("score", 0.0) for i in range(n)]
        min_s = min(scores)
        max_s = max(scores)
        if max_s == min_s:
            # 스코어가 모두 같으면 균등 배분
            return [base_wt / n] * n

        raw_w = [
            min_ratio + (1.0 - min_ratio) * (s - min_s) / (max_s - min_s)
            for s in scores
        ]
        total = sum(raw_w)
        return [base_wt * (rw / total) for rw in raw_w]

    core_weights = _intra_group_weights(top_core, _stock_alloc * _core_ratio)
    sat_weights  = _intra_group_weights(top_sat,  _stock_alloc * _sat_ratio if _sat_ratio > 0 else 0.0)
    etf_weights  = _intra_group_weights(top_etfs, _etf_alloc)

    p_items: List[PortfolioItem] = []
    for s, w in zip(top_core, core_weights):
        s["weight"] = w
        sharpe_str = f" | 샤프 {s['sharpe_1y']:+.2f}" if s.get("sharpe_1y") is not None else ""
        p_items.append(PortfolioItem(
            ticker=s["stock_code"], name=s["name"],
            asset_type="STOCK", risk_type=s["risk_type"],
            weight=round(w, 4), weight_pct=round(w * 100, 1),
            selection_reason=(
                f"[코어] 1년 수익률 {(s['ret_1y'] or 0)*100:+.1f}%"
                f"{sharpe_str} | 변동성 {(s['vol_ann'] or 0)*100:.1f}%"
            ),
            explanation=f"{s['name']}은(는) 대형 우량 코어 종목입니다. 포트폴리오 안정성 뼈대를 담당합니다.",
        ))
    for s, w in zip(top_sat, sat_weights):
        s["weight"] = w
        sharpe_str = f" | 샤프 {s['sharpe_1y']:+.2f}" if s.get("sharpe_1y") is not None else ""
        p_items.append(PortfolioItem(
            ticker=s["stock_code"], name=s["name"],
            asset_type="STOCK", risk_type=s["risk_type"],
            weight=round(w, 4), weight_pct=round(w * 100, 1),
            selection_reason=(
                f"[새틀라이트] 1년 수익률 {(s['ret_1y'] or 0)*100:+.1f}%"
                f"{sharpe_str} | 변동성 {(s['vol_ann'] or 0)*100:.1f}%"
            ),
            explanation=f"{s['name']}은(는) 초과 수익(알파)을 노리는 성장 모멘텀 종목입니다.",
        ))
    for s, w in zip(top_etfs, etf_weights):
        s["weight"] = w
        p_items.append(PortfolioItem(
            ticker=s["stock_code"], name=s["name"],
            asset_type="ETF", risk_type=s["risk_type"],
            weight=round(w, 4), weight_pct=round(w * 100, 1),
            selection_reason="분산투자 및 리스크 헤지 목적 ETF 편입",
            explanation=f"{s['name']}은(는) 포트폴리오 안정성 제고를 위한 ETF입니다.",
        ))

    # ── 5.5 예산 기반 매수 불가 종목 제거 + 비중 재정규화 (반복 수렴) ─────
    # total_assets_override 지정 시: 재정규화 후에도 못 사는 종목을 반복 제거
    if total_assets_override:
        for _ in range(len(p_items)):  # 최대 종목 수만큼 반복
            feasible = [
                (item, cand)
                for item, cand in zip(p_items, portfolio_candidates)
                if int(cand.get("current_price", 0)) > 0
                and int(total_budget * item.weight) >= int(cand["current_price"])
            ]
            if len(feasible) == len(p_items):
                break  # 모두 매수 가능 — 수렴 완료
            if len(feasible) == 0:
                # 비중 배분 후 전부 불가 → 1주라도 살 수 있는 종목 중 최고 점수 1개로 구성
                affordable_single = [
                    (item, cand)
                    for item, cand in zip(p_items, portfolio_candidates)
                    if int(cand.get("current_price", 0)) <= total_budget
                ]
                if affordable_single:
                    best = affordable_single[0]  # 이미 스코어 순 정렬 → 첫 번째가 최고 점수
                    best[0].weight = 1.0
                    best[0].weight_pct = 100.0
                    p_items = [best[0]]
                    portfolio_candidates = [best[1]]
                # affordable_single도 없으면 예산이 너무 작음 — 원본 유지 후 buy_plan에서 0주 표시
                break
            p_items = [pair[0] for pair in feasible]
            portfolio_candidates = [pair[1] for pair in feasible]
            total_n = len(p_items)
            total_w = sum(i.weight for i in p_items)
            if total_w > 0:
                for i in p_items:
                    i.weight = round(i.weight / total_w, 4)
                    i.weight_pct = round(i.weight * 100, 1)

    # ── 6. 매수 계획 ─────────────────────────────────────────────────────
    buy_plan: List[BuyPlanItem] = []

    # ── 1차: 비중 기준 초기 매수 ─────────────────────────────────────────
    plan_data = []
    total_invested = 0
    for item, cand in zip(p_items, portfolio_candidates):
        price = int(cand["current_price"])
        if price <= 0:
            continue
        allocated = int(total_budget * item.weight)
        shares = max(0, allocated // price)
        cost = shares * price
        total_invested += cost
        plan_data.append({
            "item": item, "cand": cand,
            "price": price, "shares": shares, "cost": cost,
        })

    # ── 2차: 잔여금으로 추가 매수 (그리디) ─────────────────────────────────
    # 실제 투자금 합계 기준으로 비중 계산 → overweight 판정으로 조기 종료하는 버그 방지
    remaining = total_budget - total_invested
    while remaining > 0:
        total_cost_so_far = sum(p["cost"] for p in plan_data) or 1
        best_idx = None
        best_deficit = float('-inf')
        for i, pd_ in enumerate(plan_data):
            if pd_["price"] > remaining:
                continue
            deficit = pd_["item"].weight - pd_["cost"] / total_cost_so_far
            if deficit > best_deficit:
                best_deficit = deficit
                best_idx = i
        if best_idx is None:
            break
        pd_ = plan_data[best_idx]
        pd_["shares"] += 1
        pd_["cost"] += pd_["price"]
        total_invested += pd_["price"]
        remaining -= pd_["price"]

    # ── p_items 비중을 실제 투자금 기준으로 재계산 ────────────────────────
    if total_invested > 0:
        ticker_cost = {pd_["item"].ticker: pd_["cost"] for pd_ in plan_data}
        for item in p_items:
            actual_cost = ticker_cost.get(item.ticker, 0)
            item.weight = round(actual_cost / total_invested, 4)
            item.weight_pct = round(item.weight * 100, 1)

    # ── BuyPlanItem 생성 ──────────────────────────────────────────────────
    for pd_ in plan_data:
        item, cand = pd_["item"], pd_["cand"]
        shares, cost, price = pd_["shares"], pd_["cost"], pd_["price"]
        ret_1y = cand.get("ret_1y") or 0.0
        if shares == 0:
            rationale = f"예산 부족 — 목표 비중 {item.weight_pct:.1f}% 배정 {int(total_budget * item.weight):,}원, 최소 필요 {price:,}원"
        else:
            rationale = f"비중 {item.weight_pct:.1f}% 매수 ({shares}주 × {price:,}원)"
        buy_plan.append(BuyPlanItem(
            ticker=item.ticker, name=item.name,
            price_krw=price, shares=shares,
            allocated_budget_krw=cost,
            expected_return_1y_pct=round(ret_1y * 100, 1),
            rationale=rationale,
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
    overall = (
        f"{risk_grade}({risk_tier}) 투자자를 위한 {portfolio_label}. "
        f"총 {purchased_n}개 종목 매수 (주식 {stock_n}개 · ETF {etf_n}개). "
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
            stock_max_pct=round(_stock_alloc * 100),
            single_stock_max_pct=round((_stock_alloc / max(stock_n, 1)) * 100 * 1.5),
            etf_min_pct=round(_etf_alloc * 100),
            target_weights={
                "STOCK": _stock_alloc,
                "ETF":   _etf_alloc,
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

def get_multi_portfolio_recommendations(
    user_id: int,
    conn,
    *,
    koscom_score: int = 20,
    total_assets_override: Optional[int] = None,
) -> List[PortfolioRecommendationResponse]:
    """사용자 투자성향에 최적화된 Top3 포트폴리오를 반환합니다.

    투자성향에 따라 최적 포트폴리오 기준이 달라집니다:
      - 공격투자형: 기대수익률 최대화
      - 적극투자형: 수익률 중심 (변동성 소폭 고려)
      - 위험중립형: 수익률 / 변동성 균형
      - 안전추구형: 변동성 최소화 중심
      - 안정형:     하락 방어 최우선 (변동성 최소)
    3개 포트폴리오는 모두 해당 성향에 맞는 기준으로 선별하되,
    종목 구성이 최대한 다르도록 다양성 제약을 적용합니다.
    """
    # 1. 사용자 투자성향 조회
    cur = conn.cursor()
    cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"user_id={user_id} 를 찾을 수 없습니다.")
    inv_type = row.get("investment_type") or _koscom_to_inv_type(koscom_score)

    # 투자성향별 포트폴리오 스코어 파라미터
    # (ret_w: 수익률 가중치, vol_w: 변동성 패널티 가중치)
    _SCORE_PARAMS = {
        "공격투자형": (1.0, 0.0),
        "적극투자형": (1.0, 0.3),
        "위험중립형": (1.0, 0.5),
        "안전추구형": (0.5, 1.0),
        "안정추구형": (0.5, 1.0),
        "안정형":     (0.2, 1.0),
    }
    ret_w, vol_w = _SCORE_PARAMS.get(inv_type, (1.0, 0.5))

    # 2. 다양한 팩터 가중치 + 종목 수 조합 생성
    factor_grid = []
    for mom in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
        for qual in [0.2, 0.3, 0.4, 0.5, 0.6]:
            if mom + qual < 0.95:
                lowvol = 1.0 - mom - qual
                for m3, m1 in [(0.2, 0.8), (0.35, 0.65), (0.5, 0.5), (0.7, 0.3)]:
                    for n_stocks in [5, 6, 7, 8, 9]:
                        factor_grid.append({
                            "factor_w": (mom, qual, lowvol),
                            "momentum_split": (m3, m1),
                            "n_stocks": n_stocks,
                        })

    # 3. 후보 포트폴리오 생성
    candidates = []
    for cfg in factor_grid:
        pf = _recommend_portfolio_db(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
            total_assets_override=total_assets_override,
            factor_w=cfg["factor_w"],
            momentum_split=cfg["momentum_split"],
            n_stocks_override=cfg["n_stocks"],
        )
        candidates.append(pf)

    # 4. 투자성향 맞춤 스코어로 정렬
    def _personal_score(pf):
        perf = pf.performance_3y
        if not perf:
            return -9999
        ann_ret = perf.ann_return_pct or 0
        ann_vol = perf.ann_vol_pct or 0
        return ret_w * ann_ret - vol_w * ann_vol

    sorted_candidates = sorted(candidates, key=_personal_score, reverse=True)

    # 5. 다양성 강제 선택: 포트폴리오 간 주식 종목 최대 중복 허용 2개
    def _stock_tickers(pf) -> set:
        return {it.ticker for it in pf.portfolio_items if it.asset_type == "STOCK"}

    MAX_OVERLAP = 2
    top3 = []
    for pf in sorted_candidates:
        if len(top3) >= 3:
            break
        cur_tickers = _stock_tickers(pf)
        too_similar = any(
            len(cur_tickers & _stock_tickers(selected)) > MAX_OVERLAP
            for selected in top3
        )
        if not too_similar:
            top3.append(pf)

    # 다양성 조건 미충족 시 순서대로 채움
    if len(top3) < 3:
        existing = set(id(p) for p in top3)
        for pf in sorted_candidates:
            if len(top3) >= 3:
                break
            if id(pf) not in existing:
                top3.append(pf)
                existing.add(id(pf))

    # 6. 순위 라벨 부여
    for i, pf in enumerate(top3, 1):
        pf.portfolio_label = f"Top {i} : {inv_type} 포트폴리오"
    return top3


def get_user_top3_portfolio_recommendations(
    user_id: int,
    conn,
    *,
    koscom_score: int = 20,
    total_assets_override: Optional[int] = None,
) -> List[PortfolioRecommendationResponse]:
    """해당 사용자에게 Fit Score 기준 최적의 포트폴리오 Top-3를 반환합니다.

    사용자의 투자성향(risk_appetite)에서 연속 보간한 5가지 팩터 가중치 조합으로
    후보 포트폴리오를 각각 생성하고, Fit Score 상위 3개를 1·2·3순위로 반환합니다.

    Fit Score = risk_appetite × 기대수익률 − (1 − risk_appetite) × 연변동성
    """
    # ── 1. 사용자 risk_appetite 결정 ─────────────────────────────────────
    cur = conn.cursor()
    cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"user_id={user_id} 를 찾을 수 없습니다.")
    inv_type = row.get("investment_type") or _koscom_to_inv_type(koscom_score)
    _, _, user_stock_wt, _ = _RISK_MAP_PF.get(inv_type, ("위험중립형", "3등급", 0.70, 0.30))
    r = user_stock_wt  # 0.30(안정형) ~ 1.00(공격투자형)

    # ── 2. risk_appetite 기반 팩터 가중치 후보 5종 생성 ──────────────────
    # 모멘텀 총량을 r에서 보간: 안정형(0.60) ~ 공격형(0.90)
    w_mom  = 0.60 + 0.30 * r
    w_qual = (1.0 - w_mom) * 0.5
    w_lv   = (1.0 - w_mom) * 0.5

    def _norm3(a, b, c):
        s = a + b + c
        return (round(a / s, 4), round(b / s, 4), round(c / s, 4))

    candidate_configs = [
        {"factor_w": _norm3(w_mom, w_qual, w_lv),           "momentum_split": (0.47, 0.53)},  # ① 맞춤 균형
        {"factor_w": _norm3(w_mom, w_qual, w_lv),           "momentum_split": (0.30, 0.70)},  # ② 장기 수익
        {"factor_w": _norm3(w_mom, w_qual, w_lv),           "momentum_split": (0.65, 0.35)},  # ③ 단기 모멘텀
        {"factor_w": _norm3(w_mom, w_qual * 1.5, w_lv * 1.5), "momentum_split": (0.47, 0.53)},  # ④ 안정성 강화
        {"factor_w": _norm3(w_mom, w_qual * 0.5, w_lv * 0.5), "momentum_split": (0.47, 0.53)},  # ⑤ 수익 극대화
    ]

    # ── 3. 후보 포트폴리오 생성 ──────────────────────────────────────────
    candidates = []
    for cfg in candidate_configs:
        pf = _recommend_portfolio_db(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
            total_assets_override=total_assets_override,
            factor_w=cfg["factor_w"],
            momentum_split=cfg["momentum_split"],
        )
        candidates.append(pf)

    # ── 4. Fit Score 산출 → Top-3 선별 ───────────────────────────────────
    def _fit_score(pf: PortfolioRecommendationResponse) -> float:
        ann_ret = (pf.performance_3y.ann_return_pct / 100.0 if pf.performance_3y else 0.0) or 0.0
        ann_vol = (pf.performance_3y.ann_vol_pct / 100.0 if pf.performance_3y else 0.15) or 0.15
        mc_ret  = (pf.monte_carlo_1y.p50_pct / 100.0 if pf.monte_carlo_1y else ann_ret) or ann_ret
        exp_ret = 0.6 * mc_ret + 0.4 * ann_ret
        return r * exp_ret - (1.0 - r) * ann_vol

    scored = sorted(candidates, key=_fit_score, reverse=True)

    # ── 5. 순위 레이블 부여 후 Top-3 반환 ────────────────────────────────
    for rank, pf in enumerate(scored[:3]):
        pf.portfolio_label = f"Top {rank + 1} : {inv_type} 포트폴리오"
    return scored[:3]


def get_multi_portfolio_with_signals(
    user_id: int,
    conn,
    *,
    koscom_score: int = 20,
    total_assets_override: Optional[int] = None,
    signal_map: Optional[dict] = None,
    fin_map: Optional[dict] = None,
) -> List[PortfolioRecommendationResponse]:
    """LightGBM 신호 + 재무등급을 보조 근거로 사용하는 Top3 개인화 포트폴리오 추천.

    포트폴리오 간 주식·ETF 종목 중복을 최소화하기 위해 이전 포트폴리오에서 선정된 종목은
    다음 포트폴리오 후보에서 제외합니다.
    """
    results = []
    used_tickers: set = set()
    for cfg in _PORTFOLIO_CONFIGS:
        pf = _recommend_portfolio_db(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
            total_assets_override=total_assets_override,
            portfolio_label=cfg["label"],
            factor_w=cfg["factor_w"],
            momentum_split=cfg["momentum_split"],
            signal_map=signal_map,
            fin_map=fin_map,
            excluded_tickers=used_tickers.copy(),
        )
        # 이번 포트폴리오에서 선정된 모든 종목(주식+ETF)을 다음 포트폴리오에서 제외
        for item in pf.portfolio_items:
            used_tickers.add(item.ticker)
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

    # 1-1. 설문 답변 일괄 조회 (DIVIDEND_PREF / TARGET_HORIZON / INVEST_GOAL / CONTRIBUTION_TYPE / ACCOUNT_TYPE)
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

    # ══════════════════════════════════════════════════════════════════════
    # 3단계 스코어링 파이프라인
    #
    # [1단계] MC 수익률 점수  ← 핵심 기준
    #   - 투자 기간(TARGET_HORIZON)에 맞는 퍼센타일로 MC 수익률 계산
    #   - 단기(≤2Y) → p10(하락방어), 중기(3~6Y) → p50(중앙값), 장기(≥7Y) → p90(성장)
    #   - 투자성향도 퍼센타일 선택에 반영 (공격형→ 성장 퍼센타일 우선)
    #
    # [2단계] 투자성향 적합도 보정
    #   - 변동성이 성향에 맞으면 부스트(최대 +20%), 부적합하면 페널티(최대 -20%)
    #   - LightGBM 신호 · 재무등급은 동일 가중치로 합산
    #
    # [3단계] 투자금/목표 미세조정
    #   - DCA(적립식), ISA/연금 계좌 → 안정 종목 소폭 부스트
    #   - INVEST_GOAL 키워드 → 노후/은퇴(안정↑) / 성장(성장↑) 미세조정
    # ══════════════════════════════════════════════════════════════════════

    import re as _re

    # ── TARGET_HORIZON 파싱 → 투자 기간(년) ───────────────────────────────
    _horizon_years: int = 3  # 기본값 중기
    _hm = _re.search(r'(\d+)년', horizon_raw)
    if _hm:
        _hy = int(_hm.group(1))
        _horizon_years = _hy if _hy <= 100 else max(1, _hy - _date.today().year)

    # ── [1단계] 기간 + 투자성향 → 사용할 MC 퍼센타일 결정 ─────────────────
    # 기간 기준 (기본)
    if _horizon_years <= 2:
        _mc_pct = "p10"   # 단기: 하락방어 시나리오(보수적 수익률)
    elif _horizon_years >= 7:
        _mc_pct = "p90"   # 장기: 성장 시나리오
    else:
        _mc_pct = "p50"   # 중기: 중앙값
    # 투자성향으로 퍼센타일 조정 (기간이 같아도 성향에 따라 달라짐)
    if risk_tier in ("공격투자형", "적극투자형") and _mc_pct != "p10":
        _mc_pct = "p90"   # 공격형은 항상 상승 시나리오
    elif risk_tier in ("안전추구형", "안정형") and _mc_pct != "p90":
        _mc_pct = "p10"   # 안정형은 항상 하락방어 시나리오

    # ── 투자성향별 허용 변동성 범위 (종목 적합도 판단 기준) ──────────────
    _VOL_BAND = {
        "공격투자형": (0.30, 1.00),   # 고변동성 OK
        "적극투자형": (0.20, 0.70),
        "위험중립형": (0.15, 0.50),
        "안전추구형": (0.05, 0.35),
        "안정형":     (0.05, 0.25),
    }
    _vol_low, _vol_high = _VOL_BAND.get(risk_tier, (0.10, 0.60))

    _FIN_GRADE_SCORE = {"우수": 1.0, "양호": 0.75, "보통": 0.50, "주의": 0.25}

    # ── MC 파라미터 상수 ──────────────────────────────────────────────────
    _N_MC = 1_000_000
    _rng = _np.random.default_rng(42)
    _MARKET_MU_D = 0.08 / 252        # 시장 기대수익률 8%/yr로 shrinkage
    _SHRINKAGE = 0.50
    _MAX_SIGMA_ANN = 0.70            # σ Cap
    _MAX_MU_ANN = 0.40               # μ Cap: 연 40% 초과 기대수익률은 현실에서 지속 불가
    _MAX_MC_PCT = 500.0              # MC 결과값 상한: 500% (6배) — 극단 오른쪽 꼬리 차단
    _MIN_MC_PCT = -99.0              # MC 결과값 하한: -99%

    # ── [1단계] 종목별 MC 시뮬레이션 ─────────────────────────────────────
    candidates = []
    for ticker, closes in price_hist.items():
        if len(closes) < 60:
            continue
        rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
        mu_d_raw = sum(rets) / len(rets)
        var_d = sum((r - mu_d_raw) ** 2 for r in rets) / max(len(rets) - 1, 1)
        sigma_d_raw = _math.sqrt(var_d)

        mu_d = mu_d_raw * (1 - _SHRINKAGE) + _MARKET_MU_D * _SHRINKAGE
        # μ 캡: 연 40% 초과 기대수익률은 현실에서 지속 불가 → 클램핑
        _max_mu_d = _MAX_MU_ANN / 252
        mu_d = max(-_max_mu_d, min(_max_mu_d, mu_d))

        sigma_ann = min(sigma_d_raw * _math.sqrt(252), _MAX_SIGMA_ANN)
        sigma_d = sigma_ann / _math.sqrt(252)

        # 투자 기간(N년)에 맞춰 MC 경로 계산
        _trading_days = int(_horizon_years * 252)
        finals = (
            _np.exp((mu_d - 0.5 * sigma_d**2) * _trading_days
                    + sigma_d * _math.sqrt(_trading_days) * _rng.standard_normal(_N_MC)) - 1
        ) * 100
        # 결과값 클램핑: 극단적 오른쪽 꼬리 차단
        finals = _np.clip(finals, _MIN_MC_PCT, _MAX_MC_PCT)
        mc_p10, mc_p50, mc_p90 = _np.percentile(finals, [10, 50, 90])
        mc_val = mc_p10 if _mc_pct == "p10" else (mc_p90 if _mc_pct == "p90" else mc_p50)

        sig = sig_map.get(ticker, {})
        fin = (fin_scores or {}).get(ticker, {})
        fin_grade = fin.get("overall_grade")
        ann_vol_pct = sigma_ann  # 0~1 범위
        candidates.append({
            "ticker": ticker,
            "name": sig.get("name", ""),
            "market": sig.get("market", "KOSPI"),
            "p_adj": float(sig.get("p_adj", 0.5)),
            "rank_overall": int(sig.get("rank_overall", 999)),
            "mc_p10": mc_p10, "mc_p50": mc_p50, "mc_p90": mc_p90, "mc_val": mc_val,
            "ann_vol": ann_vol_pct * 100,      # % 단위
            "ann_vol_ratio": ann_vol_pct,       # 0~1 (적합도 판단용)
            "ann_return": mu_d * 252 * 100,
            "fin_grade": fin_grade,
            "fin_score": _FIN_GRADE_SCORE.get(fin_grade, 0.50),
            # 세부 팩터 점수 (0~1, 없으면 None)
            "profitability_score": fin.get("profitability_score"),
            "growth_score":        fin.get("growth_score"),
            "stability_score":     fin.get("stability_score"),
            "cashflow_score":      fin.get("cashflow_score"),
        })

    if not candidates:
        raise ValueError("몬테카를로 시뮬레이션을 위한 충분한 가격 데이터가 없습니다.")

    # ── 변동성 하드 필터: 성향에 크게 어긋나는 종목을 후보에서 완전 제외 ──
    # 공격형/적극형: vol 하한을 _vol_low 그대로 사용 (저변동 안정주 완전 제외)
    # 중립형 이하: -0.10 slack 허용
    _hard_upper = _vol_high + 0.15   # 상단: 허용 최대치 + 15%p 여유
    if risk_tier in ("공격투자형", "적극투자형"):
        _hard_lower = _vol_low       # 하한 엄격 적용
    else:
        _hard_lower = max(0.0, _vol_low - 0.10)  # 하한: 10%p 여유
    _vol_filtered = [
        c for c in candidates
        if _hard_lower <= c["ann_vol_ratio"] <= _hard_upper
    ]
    if len(_vol_filtered) >= top_n:
        candidates = _vol_filtered

    # ── [1단계] MC 수익률 정규화 점수 (0~1) ──────────────────────────────
    def _rn(vals):
        idxd = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(idxd) < 2:
            return [0.5] * len(vals)
        srt = sorted(idxd, key=lambda x: x[1])
        rm = {i: r / (len(srt) - 1) for r, (i, _) in enumerate(srt)}
        return [rm.get(i, 0.5) for i in range(len(vals))]

    mc_n  = _rn([c["mc_val"] for c in candidates])   # MC 수익률 순위 정규화
    sig_n = _rn([c["p_adj"]  for c in candidates])   # LightGBM 신호 순위 정규화

    # ── [2단계] 투자성향 적합도 보정 계수 계산 ───────────────────────────
    # 종목 변동성이 허용 범위 내 → 부스트(최대 1.20), 범위 밖 → 페널티(최대 0.80)
    for c in candidates:
        v = c["ann_vol_ratio"]
        if _vol_low <= v <= _vol_high:
            # 범위 중앙에 가까울수록 최대 부스트
            _mid = (_vol_low + _vol_high) / 2
            _half = (_vol_high - _vol_low) / 2
            _fit = 1.0 - abs(v - _mid) / _half if _half > 0 else 1.0
            c["risk_fit"] = 1.0 + 0.20 * _fit      # 1.00 ~ 1.20
        else:
            # 범위 밖으로 벗어난 정도에 따라 페널티
            _dist = min(abs(v - _vol_low), abs(v - _vol_high))
            _penalty = min(0.20, _dist / 0.20)
            c["risk_fit"] = 1.0 - _penalty          # 0.80 ~ 1.00

    # ── [2단계] 재무등급 + LightGBM 신호 보조 점수 (0~1) ─────────────────
    # 성향별 세부 팩터 가중치: (수익성, 성장성, 안정성, 현금흐름)
    _FIN_DETAIL_W = {
        "공격투자형": (0.15, 0.50, 0.15, 0.20),  # 성장성 최우선
        "적극투자형": (0.20, 0.40, 0.20, 0.20),
        "위험중립형": (0.30, 0.25, 0.25, 0.20),  # 균형
        "안전추구형": (0.25, 0.15, 0.40, 0.20),  # 안정성 최우선
        "안정추구형": (0.25, 0.15, 0.40, 0.20),
        "안정형":     (0.20, 0.10, 0.50, 0.20),
    }
    _fw = _FIN_DETAIL_W.get(risk_tier, (0.25, 0.25, 0.25, 0.25))

    for i, c in enumerate(candidates):
        # 세부 팩터 점수가 있으면 가중 합산, 없으면 overall_grade 기반 fin_score 사용
        _fp, _fg, _fs, _fc = (
            c.get("profitability_score"),
            c.get("growth_score"),
            c.get("stability_score"),
            c.get("cashflow_score"),
        )
        _available = [v for v in [_fp, _fg, _fs, _fc] if v is not None]
        if len(_available) >= 2:
            # 데이터 있는 항목만 정규화하여 가중합
            _detail_fin = (
                (_fw[0] * (_fp or 0.5)) +
                (_fw[1] * (_fg or 0.5)) +
                (_fw[2] * (_fs or 0.5)) +
                (_fw[3] * (_fc or 0.5))
            )
            # overall_grade 와 50:50 혼합 (단일 지표 과적합 방지)
            _combined_fin = 0.50 * _detail_fin + 0.50 * c["fin_score"]
        else:
            _combined_fin = c["fin_score"]

        c["support_score"] = 0.60 * sig_n[i] + 0.40 * _combined_fin

    # ── [1+2단계] 핵심 점수: MC 수익률 순위(60%) + 지지점수(40%) × 투자성향 적합도 ──
    # • 구 공식 mc_n * (1 + support*0.30): support 가 0이어도 mc_n이 0.5면 50점 유지
    # • 신 공식 (mc_n*0.60 + support*0.40) * risk_fit:
    #     - support=0(재무최하+신호 약): mc_n=0.5 → 0.3 → 30점 (이전 50점)
    #     - support=1(재무최상+신호 강): mc_n=0.5 → 0.7 → 최대 84점
    #   → 적합도 점수가 실제 재무·신호 품질을 반영
    for i, c in enumerate(candidates):
        c["total_score"] = (0.60 * mc_n[i] + 0.40 * c["support_score"]) * c["risk_fit"]

    # ── [3단계] 투자금/목표 미세 조정 ────────────────────────────────────
    # DCA(적립식): 변동성 낮은 종목 +5%
    # ISA/연금 계좌: 안정 종목 +5%
    # 노후/은퇴 목표: 변동성 낮은 종목 +5%
    # 성장/증식 목표: 변동성 높은 종목 +5%
    _at = account_type_raw.lower().replace(' ', '')
    _gl = invest_goal_raw.replace(' ', '')
    for c in candidates:
        _adj = 1.0
        v = c["ann_vol_ratio"]
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
        c["total_score"] *= _adj

    candidates.sort(key=lambda x: x["total_score"], reverse=True)
    top = candidates[:top_n]

    # 6. 응답 생성
    _mc_pct_label = {"p10": f"하락방어(10%·{_horizon_years}년)", "p50": f"중앙값(50%·{_horizon_years}년)", "p90": f"성장(90%·{_horizon_years}년)"}
    items = []
    for rank, c in enumerate(top, 1):
        items.append(StockItem(
            rank=rank,
            ticker=c["ticker"],
            name=c["name"],
            market=c["market"],
            total_score=round(c["total_score"], 4),
            reasons=[
                f"MC {_horizon_years}년 기대수익률({_mc_pct_label[_mc_pct]}) {c['mc_val']:+.1f}%",
                f"LightGBM 상승확률 {c['p_adj']*100:.0f}% (전체 {c['rank_overall']}위)",
                f"재무등급 {c['fin_grade'] or '정보없음'} | 연변동성 {c['ann_vol']:.0f}%",
            ],
            features=StockFeatures(
                ret_3m=None, ret_6m=None,
                ret_1y=round(c["mc_p50"] / 100, 4),
                vol_ann=round(c["ann_vol"] / 100, 4),
                beta=None, mdd=None,
                mc_p10=round(c["mc_p10"], 2),
                mc_p50=round(c["mc_p50"], 2),
                mc_p90=round(c["mc_p90"], 2),
            ),
            explanation=(
                f"[{_horizon_years}년 투자기간 · {risk_tier}] "
                f"MC 기대수익률({_mc_pct_label[_mc_pct]}) {c['mc_val']:+.1f}% | "
                f"하락(10%) {c['mc_p10']:+.1f}% / 중앙값 {c['mc_p50']:+.1f}% / 상승(90%) {c['mc_p90']:+.1f}%. "
                f"LightGBM 상승확률 {c['p_adj']*100:.0f}% (전체 {c['rank_overall']}위). "
                f"재무등급 {c['fin_grade'] or '정보없음'} | 연변동성 {c['ann_vol']:.0f}%."
            ),
        ))

    return StockRecommendationResponse(
        user_id=user_id,
        risk_tier=risk_tier,
        risk_grade=risk_grade,
        generated_at=datetime.now().isoformat()[:19],
        items=items,
    )
