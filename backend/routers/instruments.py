"""종목(instruments) 라우터.

가격 데이터는 한국투자증권 오픈 API (KIS) 에서 직접 조회합니다.
종목 기본 정보(코드·이름·섹터 등)는 DB instruments 테이블에서 읽습니다.

Endpoints:
  GET /api/instruments/stocks              — STOCK 목록 (KIS 실시간가 병렬 조회 · 5분 캐시)
  GET /api/instruments/stocks/{stock_code} — 개별 종목 상세 (KIS 실시간가 + 1년 히스토리)
  GET /api/instruments/etfs                — ETF 목록 (DB 기본정보)
"""
from __future__ import annotations

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

from kis_client import get_current_price, get_daily_prices_1y

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

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
    )


# ── Pydantic 모델 ───────────────────────────────────────────────────────────
class PricePoint(BaseModel):
    date: str
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
):
    """STOCK 목록.
    종목 기본정보는 DB, 현재가는 KIS API 병렬 조회 (5분 TTL 캐시 적용).
    """
    # ── 1. DB에서 종목 기본 정보 조회 ────────────────────────────────────────
    conn = _db()
    try:
        cur = conn.cursor()
        where = ["asset_type = 'STOCK'", "price_status = 'ACTIVE'"]
        params: list = []

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

    # ── 2. KIS API 병렬 현재가 조회 ──────────────────────────────────────────
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
            SELECT stock_code, name, exchange, sector, asset_type
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

    # ── 2. KIS API — 현재가 조회 (캐시 우선) ──────────────────────────────────
    live = _get_price_cached(stock_code)
    if live is None:
        raise HTTPException(status_code=502, detail=f"KIS 현재가 조회 실패: {stock_code}")

    # ── 3. KIS API — 1년 일별 히스토리 ───────────────────────────────────────
    try:
        hist = get_daily_prices_1y(stock_code)   # [{"date","close","volume"}, ...]
    except Exception as e:
        hist = []  # 히스토리 실패 시 빈 배열로 폴백 (현재가는 표시)

    price_history = [
        PricePoint(date=p["date"], close=p["close"], volume=p.get("volume"))
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


@router.get("/etfs", response_model=List[StockListItem])
def list_etfs(limit: int = Query(50, le=200)):
    """ETF 목록 (DB instruments.last_price 기준)."""
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT stock_code, name, exchange, sector, asset_type,
                   last_price, last_price_date
            FROM instruments
            WHERE asset_type = 'ETF' AND price_status = 'ACTIVE'
            ORDER BY last_price DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [
            StockListItem(
                stock_code=r["stock_code"],
                name=r["name"],
                exchange=r["exchange"] or "",
                sector=r["sector"],
                asset_type=r["asset_type"],
                current_price=float(r["last_price"] or 0),
                price_date=str(r["last_price_date"] or ""),
            )
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
