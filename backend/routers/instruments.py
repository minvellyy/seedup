"""종목(instruments) 라우터.

가격 데이터는 한국투자증권 오픈 API (KIS) 에서 직접 조회합니다.
종목 기본 정보(코드·이름·섹터 등)는 DB instruments 테이블에서 읽습니다.

Endpoints:
  GET /api/instruments/stocks              — STOCK 목록 (KIS 실시간가 병렬 조회 · 5분 캐시)
  GET /api/instruments/stocks/{stock_code} — 개별 종목 상세 (KIS 실시간가 + 1년 히스토리)
  GET /api/instruments/etfs                — ETF 목록 (DB 기본정보)
"""
from __future__ import annotations

import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymysql
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from kis_client import get_current_price, get_daily_prices_1y, get_etf_info, get_etf_holdings_pykrx

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/instruments", tags=["instruments"])

# ── 현재가 TTL 캐시 (5분) ───────────────────────────────────────────────────
# { stock_code: {"data": {...}, "ts": float} }
_price_cache: Dict[str, Dict] = {}
_CACHE_TTL = 300  # 초


def _get_price_cached(stock_code: str) -> Optional[Dict]:
    """KIS 현재가 조회 with 5분 TTL 캐시."""
    now = time.time()
    cached = _price_cache.get(stock_code)
    if cached and now - cached["ts"] < _CACHE_TTL:
        return cached["data"]
    try:
        data = get_current_price(stock_code)
        _price_cache[stock_code] = {"data": data, "ts": now}
        return data
    except Exception:
        # KIS 실패 시 만료된 캐시라도 반환
        return cached["data"] if cached else None


# ── DB 연결 헬퍼 ────────────────────────────────────────────────────────────
def _db():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


# ── Pydantic 모델 ───────────────────────────────────────────────────────────
class PricePoint(BaseModel):
    date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[int] = None


class StockListItem(BaseModel):
    stock_code: str
    name: str
    exchange: str
    sector: Optional[str] = None
    asset_type: str
    current_price: float
    prev_close: Optional[float] = None
    change: Optional[float] = None
    change_rate: Optional[float] = None
    price_date: Optional[str] = None
    volume: Optional[int] = None


class StockDetail(BaseModel):
    stock_code: str
    name: str
    exchange: str
    sector: Optional[str] = None
    asset_type: str
    current_price: float
    prev_close: Optional[float] = None
    change: Optional[float] = None
    change_rate: Optional[float] = None
    price_date: Optional[str] = None
    price_history: List[PricePoint] = []
    ret_1m: Optional[float] = None
    ret_3m: Optional[float] = None
    ret_6m: Optional[float] = None
    ret_1y: Optional[float] = None
    vol_ann: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None


# ── 지표 계산 유틸 ──────────────────────────────────────────────────────────
def _calc_ret(prices: list, days: int) -> Optional[float]:
    """prices: [{"date": str, "close": float}, ...] 오름차순.
    days 이전 종가 → 최신 종가 수익률(%)."""
    if len(prices) < 2:
        return None
    try:
        latest_date = date.fromisoformat(prices[-1]["date"])
    except ValueError:
        return None
    cutoff = latest_date - timedelta(days=days)
    past = [p for p in prices if date.fromisoformat(p["date"]) <= cutoff]
    base = past[-1]["close"] if past else prices[0]["close"]
    curr = prices[-1]["close"]
    if base <= 0:
        return None
    return round((curr - base) / base * 100, 2)


def _calc_vol(prices: list, ann_days: int = 252) -> Optional[float]:
    """연환산 변동성 (일별 log-return stddev × √252) — %"""
    closes = [p["close"] for p in prices[-ann_days:] if p["close"] > 0]
    if len(closes) < 10:
        return None
    log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(log_rets) / len(log_rets)
    var  = sum((r - mean) ** 2 for r in log_rets) / len(log_rets)
    return round(math.sqrt(var * ann_days) * 100, 2)


# ── 엔드포인트 ──────────────────────────────────────────────────────────────

@router.get("/stocks", response_model=List[StockListItem])
def list_stocks(
    exchange: Optional[str] = Query(None, description="KOSPI | KOSDAQ"),
    limit: int = Query(100, le=500),
    search: Optional[str] = Query(None, description="종목명 검색"),
    codes: Optional[str] = Query(None, description="쉼표로 구분된 종목코드 목록 (예: 005930,000660)"),
):
    """STOCK 목록.
    종목 기본정보는 DB, 현재가는 KIS API 병렬 조회 (5분 TTL 캐시 적용).
    codes 파라미터로 특정 종목코드만 조회 가능.
    """
    # ── 1. DB에서 종목 기본 정보 조회 ────────────────────────────────────────
    conn = _db()
    try:
        cur = conn.cursor()
        where = ["asset_type = 'STOCK'"]
        params: list = []

        # codes 파라미터가 있으면 해당 종목코드만 조회 (price_status 무관)
        if codes:
            code_list = [c.strip() for c in codes.split(',') if c.strip()]
            if code_list:
                placeholders = ','.join(['%s'] * len(code_list))
                where.append(f"stock_code IN ({placeholders})")
                params.extend(code_list)
        else:
            where.append("price_status = 'ACTIVE'")

        if exchange:
            where.append("exchange = %s")
            params.append(exchange.upper())
        if search:
            where.append("name LIKE %s")
            params.append(f"%{search}%")

        cur.execute(
            f"""
            SELECT stock_code, name, exchange, sector, asset_type,
                   last_price, last_price_date
            FROM instruments
            WHERE {' AND '.join(where)}
            ORDER BY last_price DESC
            LIMIT %s
            """,
            params + [limit],
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    # ── 2. KIS API 순차 현재가 조회 (rate limit 방지) ────────────────────────
    codes = [r["stock_code"] for r in rows]
    live_prices: Dict[str, Dict] = {}

    max_workers = min(10, len(codes))
    if max_workers > 0:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {pool.submit(_get_price_cached, c): c for c in codes}
            for fut in as_completed(future_map):
                code = future_map[fut]
                result = fut.result()
                if result:
                    live_prices[code] = result

    # ── 3. 결합 ───────────────────────────────────────────────────────────────
    result_list = []
    for r in rows:
        code = r["stock_code"]
        live = live_prices.get(code)

        if live:
            curr       = float(live["current_price"])
            prev_close = float(live["prev_close"]) if live.get("prev_close") else None
            change     = float(live["change"]) if live.get("change") else None
            chg_rate   = float(live["change_rate"]) if live.get("change_rate") else None
            price_date = live.get("price_date") or str(r["last_price_date"] or "")
            volume     = live.get("volume")
        else:
            # KIS 실패 시 DB fallback
            curr       = float(r["last_price"] or 0)
            prev_close = None
            change     = None
            chg_rate   = None
            price_date = str(r["last_price_date"] or "")
            volume     = None

        result_list.append(StockListItem(
            stock_code=code,
            name=r["name"],
            exchange=r["exchange"] or "",
            sector=r["sector"],
            asset_type=r["asset_type"],
            current_price=curr,
            prev_close=prev_close,
            change=change,
            change_rate=chg_rate,
            price_date=price_date,
            volume=volume,
        ))

    return result_list


@router.get("/stocks/{stock_code}", response_model=StockDetail)
def get_stock_detail(stock_code: str):
    """개별 종목 상세.
    현재가·등락률·1년 히스토리는 한국투자증권 오픈 API에서 실시간 조회합니다.
    """
    # ── 1. DB에서 종목 기본 정보 조회 ────────────────────────────────────────
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT stock_code, name, exchange, sector, asset_type,
                   last_price, last_price_date
            FROM instruments
            WHERE stock_code = %s
            """,
            (stock_code,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"종목 {stock_code}을 찾을 수 없습니다.")

    # ── 2. KIS API — 현재가 조회 (캐시 우선, 실패 시 DB fallback) ────────────
    live = _get_price_cached(stock_code)
    if live is None:
        # KIS 실패 시 DB 저장 가격으로 폴백
        db_price = float(row["last_price"] or 0)
        if db_price <= 0:
            raise HTTPException(status_code=502, detail=f"KIS 현재가 조회 실패: {stock_code}")
        _logger.warning(f"KIS 현재가 조회 실패, DB fallback 사용: {stock_code}")
        live = {
            "current_price": db_price,
            "prev_close": None,
            "change": None,
            "change_rate": None,
            "volume": None,
            "price_date": str(row["last_price_date"] or ""),
        }

    # ── 3. KIS API — 1년 일별 히스토리 (최대 8초 타임아웃) ──────────────────
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(get_daily_prices_1y, stock_code)
            hist = future.result(timeout=8)
    except Exception:
        hist = []  # 히스토리 실패/타임아웃 시 빈 배열로 폴백 (현재가는 표시)

    price_history = [
        PricePoint(
            date=p["date"],
            open=p.get("open"),
            high=p.get("high"),
            low=p.get("low"),
            close=p["close"],
            volume=p.get("volume"),
        )
        for p in hist
    ]

    # ── 4. 지표 계산 ──────────────────────────────────────────────────────────
    closes_1y = [p["close"] for p in hist]
    ret_1m  = _calc_ret(hist, 30)
    ret_3m  = _calc_ret(hist, 90)
    ret_6m  = _calc_ret(hist, 180)
    ret_1y  = _calc_ret(hist, 365)
    vol_ann = _calc_vol(hist, 252)
    high_52w = max(closes_1y) if closes_1y else None
    low_52w  = min(closes_1y) if closes_1y else None

    return StockDetail(
        stock_code=row["stock_code"],
        name=row["name"],
        exchange=row["exchange"] or "",
        sector=row["sector"],
        asset_type=row["asset_type"],
        current_price=live["current_price"],
        prev_close=live["prev_close"],
        change=live["change"],
        change_rate=live["change_rate"],
        price_date=live["price_date"],
        price_history=price_history,
        ret_1m=ret_1m,
        ret_3m=ret_3m,
        ret_6m=ret_6m,
        ret_1y=ret_1y,
        vol_ann=vol_ann,
        high_52w=high_52w,
        low_52w=low_52w,
    )


@router.get("/stocks/{stock_code}/scores")
def get_stock_scores(stock_code: str):
    """종목 재무 점수 — fin_scores parquet 기반 빠른 조회. 레이더 차트용."""
    import math
    try:
        import sys, os
        _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _backend_dir not in sys.path:
            sys.path.insert(0, _backend_dir)
        from config import FIN_MODEL_DIR
        processed = FIN_MODEL_DIR / "data" / "processed"
        # 가장 최신 연도의 fin_scores 파일을 자동 선택
        candidates = sorted(processed.glob("fin_scores_v2_*_CONSOL_with_mc_with_price.parquet"))
        parquet_path = candidates[-1] if candidates else None
        if parquet_path is None or not parquet_path.exists():
            return {"stock_code": stock_code, "available": False}

        import pandas as pd

        def _load_scores_df(path):
            try:
                return pd.read_parquet(path)
            except Exception:
                import pyarrow.parquet as pq
                table = pq.read_table(path, use_pandas_metadata=False)
                return table.to_pandas()

        df = _load_scores_df(parquet_path)
        sub = df[df["ticker"].astype(str).str.zfill(6) == stock_code.zfill(6)]
        if sub.empty:
            return {"stock_code": stock_code, "available": False}

        row = sub.sort_values("as_of").iloc[-1]

        def _f(key):
            try:
                v = float(row[key]) if key in row.index else None
                if v is None or math.isnan(v):
                    return None
                # Scale 0-1 percentile scores → 0-100
                return round(v * 100, 1) if v <= 1.0 else round(v, 1)
            except Exception:
                return None

        def _raw(key):
            try:
                v = float(row[key]) if key in row.index else None
                return None if v is None or math.isnan(v) else round(v, 2)
            except Exception:
                return None

        def _fallback2(primary_key, sub_keys, weights):
            """pre-computed 점수가 NaN이면 sub-score들로 직접 계산."""
            v = _f(primary_key)
            if v is not None:
                return v
            vals = [(_f(k), w) for k, w in zip(sub_keys, weights)]
            valid = [(sv, w) for sv, w in vals if sv is not None]
            if not valid:
                return None
            total_w = sum(w for _, w in valid)
            return round(sum(sv * w for sv, w in valid) / total_w, 1)

        def _pct_rank_in_df(col, val, higher_is_better=True):
            """전체 종목 최신 row 대비 val의 percentile 점수(0~100) 반환."""
            if val is None:
                return None
            try:
                # 종목별 최신 row만 사용
                snap = df.sort_values("as_of").groupby("ticker")[col].last().dropna()
                if snap.empty:
                    return None
                pct = float((snap <= val).sum()) / len(snap)
                if not higher_is_better:
                    pct = 1.0 - pct
                return round(pct * 100, 1)
            except Exception:
                return None

        mc = _raw("market_cap") if "market_cap" in row.index else None

        # ── 성장성 ─ sub-score → opm/roa 개선도 percentile 순으로 fallback
        growth_score = _fallback2(
            "growth_score",
            ["sales_yoy_score", "op_income_yoy_score"], [0.5, 0.5]
        )
        if growth_score is None:
            opm_now = _raw("opm")
            opm_lag = _raw("opm_lag4") if "opm_lag4" in row.index else None
            roa_now = _raw("roa")
            roa_lag = _raw("roa_lag4") if "roa_lag4" in row.index else None

            def _delta_pct(col_now, col_lag, val_now, val_lag):
                if val_now is None or val_lag is None:
                    return None
                delta = val_now - val_lag
                try:
                    snap = df.sort_values("as_of").groupby("ticker").last().reset_index()
                    pop_delta = (snap[col_now] - snap[col_lag]).dropna()
                    if pop_delta.empty:
                        return None
                    return round(float((pop_delta <= delta).mean()) * 100, 1)
                except Exception:
                    return None

            parts = [
                _delta_pct("opm", "opm_lag4", opm_now, opm_lag),
                _delta_pct("roa", "roa_lag4", roa_now, roa_lag),
            ]
            valid = [p for p in parts if p is not None]
            if valid:
                growth_score = round(sum(valid) / len(valid), 1)

            # 최종 fallback: roa 절대 수준 percentile (수익창출력 기준 근사)
            if growth_score is None and roa_now is not None:
                growth_score = _pct_rank_in_df("roa", roa_now, higher_is_better=True)

        # ── 현금흐름 ─ sub-score → cfo_to_assets 순으로 fallback
        cashflow_score = _fallback2(
            "cashflow_score",
            ["cfo_margin_score", "fcf_margin_score"], [0.6, 0.4]
        )
        if cashflow_score is None and "cfo_to_assets" in row.index:
            cfo_assets = _raw("cfo_to_assets")
            cashflow_score = _pct_rank_in_df("cfo_to_assets", cfo_assets, higher_is_better=True)

        profitability_score = _fallback2(
            "profitability_score",
            ["opm_score", "roa_score"], [0.6, 0.4]
        )
        stability_score = _fallback2(
            "stability_score",
            ["debt_equity_score", "current_ratio_score"], [0.6, 0.4]
        )

        return {
            "stock_code": stock_code,
            "available": True,
            "as_of": str(row["as_of"])[:10] if "as_of" in row.index else None,
            "overall_score": _f("overall_score"),
            "overall_grade": str(row["overall_grade"]) if "overall_grade" in row.index and row["overall_grade"] else None,
            "radar": [
                {"key": "profitability", "label": "수익성",    "score": profitability_score},
                {"key": "growth",        "label": "성장성",    "score": growth_score},
                {"key": "stability",     "label": "안정성",    "score": stability_score},
                {"key": "cashflow",      "label": "현금흐름",  "score": cashflow_score},
                {"key": "valuation",     "label": "밸류에이션", "score": _f("valuation_score")},
            ],
            "market_cap": mc,
        }
    except Exception as exc:
        return {"stock_code": stock_code, "available": False, "error": str(exc)}


@router.get("/etfs", response_model=List[StockListItem])
def list_etfs(
    limit: int = Query(50, le=500),
    search: Optional[str] = Query(None, description="ETF명 검색"),
):
    """ETF 목록. 현재가는 KIS API 병렬 조회 (5분 TTL 캐시 적용)."""
    conn = _db()
    try:
        cur = conn.cursor()
        where = ["asset_type = 'ETF'", "price_status = 'ACTIVE'"]
        params: list = []
        if search:
            where.append("name LIKE %s")
            params.append(f"%{search}%")
        cur.execute(
            f"""
            SELECT stock_code, name, exchange, sector, asset_type,
                   last_price, last_price_date
            FROM instruments
            WHERE {' AND '.join(where)}
            ORDER BY last_price DESC
            LIMIT %s
            """,
            params + [limit],
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    # KIS API 병렬 현재가 조회 (5분 TTL 캐시)
    etf_codes = [r["stock_code"] for r in rows]
    live_prices: Dict[str, Dict] = {}
    max_workers = min(10, len(etf_codes))
    if max_workers > 0:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {pool.submit(_get_price_cached, c): c for c in etf_codes}
            for fut in as_completed(future_map):
                code = future_map[fut]
                result = fut.result()
                if result:
                    live_prices[code] = result

    result_list = []
    for r in rows:
        code = r["stock_code"]
        live = live_prices.get(code)
        if live:
            curr       = float(live["current_price"])
            prev_close = float(live["prev_close"]) if live.get("prev_close") else None
            change     = float(live["change"]) if live.get("change") else None
            chg_rate   = float(live["change_rate"]) if live.get("change_rate") else None
            price_date = live.get("price_date") or str(r["last_price_date"] or "")
            volume     = live.get("volume")
        else:
            curr       = float(r["last_price"] or 0)
            prev_close = None
            change     = None
            chg_rate   = None
            price_date = str(r["last_price_date"] or "")
            volume     = None

        result_list.append(StockListItem(
            stock_code=code,
            name=r["name"],
            exchange=r["exchange"] or "",
            sector=r["sector"],
            asset_type=r["asset_type"],
            current_price=curr,
            prev_close=prev_close,
            change=change,
            change_rate=chg_rate,
            price_date=price_date,
            volume=volume,
        ))

    return result_list


# ── ETF 상세 엔드포인트 ─────────────────────────────────────────────────────

class EtfDetail(BaseModel):
    stock_code: str
    name: str
    exchange: str
    sector: Optional[str] = None
    asset_type: str
    current_price: float
    prev_close: Optional[float] = None
    change: Optional[float] = None
    change_rate: Optional[float] = None
    price_date: Optional[str] = None
    price_history: List[PricePoint] = []
    ret_1m: Optional[float] = None
    ret_3m: Optional[float] = None
    ret_6m: Optional[float] = None
    ret_1y: Optional[float] = None
    vol_ann: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    tracking_index: Optional[str] = None
    fund_manager: Optional[str] = None
    aum: Optional[float] = None
    expense_ratio: Optional[float] = None
    distribution: Optional[str] = None


class EtfHoldingItem(BaseModel):
    rank: int
    asset_type: str = "주식"
    name: str
    weight: float
    stock_code: Optional[str] = None


@router.get("/etfs/{etf_code}", response_model=EtfDetail)
def get_etf_detail(etf_code: str):
    """ETF 상세.
    - 현재가·차트: KIS API
    - ETF 메타데이터(추종지수·운용사·AUM·보수율·분배방식): KIS FHPST02400000
    """
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT stock_code, name, exchange, sector, asset_type, last_price, last_price_date "
            "FROM instruments WHERE stock_code = %s AND asset_type = 'ETF'",
            (etf_code,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"ETF {etf_code}을 찾을 수 없습니다.")

    live = _get_price_cached(etf_code)
    if live is None:
        db_price = float(row["last_price"] or 0)
        if db_price <= 0:
            raise HTTPException(status_code=502, detail=f"KIS 현재가 조회 실패: {etf_code}")
        live = {"current_price": db_price, "prev_close": None, "change": None,
                "change_rate": None, "volume": None, "price_date": str(row["last_price_date"] or "")}

    try:
        hist = get_daily_prices_1y(etf_code)
    except Exception:
        hist = []

    price_history = [
        PricePoint(date=p["date"], open=p.get("open"), high=p.get("high"),
                   low=p.get("low"), close=p["close"], volume=p.get("volume"))
        for p in hist
    ]
    closes_1y = [p["close"] for p in hist]

    # KIS ETF 기본정보 조회 (실패해도 graceful fallback)
    etf_meta = get_etf_info(etf_code)

    return EtfDetail(
        stock_code=row["stock_code"],
        name=row["name"],
        exchange=row["exchange"] or "",
        sector=row["sector"],
        asset_type=row["asset_type"],
        current_price=live["current_price"],
        prev_close=live.get("prev_close"),
        change=live.get("change"),
        change_rate=live.get("change_rate"),
        price_date=live.get("price_date"),
        price_history=price_history,
        ret_1m=_calc_ret(hist, 30),
        ret_3m=_calc_ret(hist, 90),
        ret_6m=_calc_ret(hist, 180),
        ret_1y=_calc_ret(hist, 365),
        vol_ann=_calc_vol(hist, 252),
        high_52w=max(closes_1y) if closes_1y else None,
        low_52w=min(closes_1y) if closes_1y else None,
        tracking_index=etf_meta.get("tracking_index"),
        fund_manager=etf_meta.get("fund_manager"),
        aum=etf_meta.get("aum"),
        expense_ratio=etf_meta.get("expense_ratio"),
        distribution=etf_meta.get("distribution"),
    )


@router.get("/etfs/{etf_code}/holdings", response_model=List[EtfHoldingItem])
def get_etf_holdings(etf_code: str, limit: int = Query(25, le=100)):
    """ETF 구성 종목 TOP N.
    pykrx(KRX 공시 데이터)에서 실시간 조회합니다.
    """
    holdings = get_etf_holdings_pykrx(etf_code, top_n=limit)
    return [
        EtfHoldingItem(
            rank=h["rank"],
            asset_type=h.get("asset_type") or "주식",
            name=h["name"],
            weight=h["weight"],
            stock_code=h.get("stock_code"),
        )
        for h in holdings
    ]
