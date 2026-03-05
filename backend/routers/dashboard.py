from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import os
import pymysql
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

# OpenAI API 사용 (선택사항)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# ── KIS 지수 캐시 (5분 TTL) ───────────────────────────────────────────────────
# { "index_KOSPI": {"data": {...}, "ts": float}, ... }
_index_cache: dict = {}

# ── pykrx 수급 캐시 (30분 TTL — 일별 데이터라 자주 변하지 않음) ──────────────
# { "trading_KOSPI": {"data": {...}, "ts": float}, ... }
_trading_cache: dict = {}


def _get_pykrx_trading(market_code: str) -> Dict:
    """pykrx로 최근 영업일 투자자별 순매수 금액(원) 반환.

    Returns:
        {"market": "코스피", "institution": float, "foreign": float, "individual": float,
         "date": "YYYY-MM-DD"}
    """
    import time
    cache_key = f"trading_{market_code.upper()}"
    cached = _trading_cache.get(cache_key)
    if cached and time.time() - cached["ts"] < 1800:  # 30분 TTL
        return cached["data"]

    try:
        from pykrx import stock
        import pandas as pd

        today = datetime.today()
        # 오늘 포함 최근 7일 조회 → 가장 최근 영업일 데이터 사용
        fromdate = (today - timedelta(days=7)).strftime("%Y%m%d")
        todate   = today.strftime("%Y%m%d")

        df = stock.get_market_trading_value_by_date(fromdate, todate, market_code.upper())
        if df is None or df.empty:
            raise ValueError("pykrx 데이터 없음")

        # 가장 최근 행 사용
        row = df.iloc[-1]
        latest_date = str(df.index[-1].date()) if hasattr(df.index[-1], 'date') else str(df.index[-1])

        # 컬럼명 탐색 (버전마다 다를 수 있음)
        def _find_col(df, candidates):
            for c in candidates:
                if c in df.columns:
                    return float(row[c])
            return 0.0

        institution = _find_col(df, ["기관합계", "기관", "기관계"])
        foreign     = _find_col(df, ["외국인합계", "외국인", "외국인계"])
        individual  = _find_col(df, ["개인"])
        market_name = "코스피" if market_code.upper() == "KOSPI" else "코스닥"

        data = {
            "market":     market_name,
            "institution": institution,
            "foreign":     foreign,
            "individual":  individual,
            "date":        latest_date,
        }
        _trading_cache[cache_key] = {"data": data, "ts": time.time()}
        return data

    except Exception as e:
        print(f"pykrx 수급 조회 실패 [{market_code}]: {e}")
        raise

# ── DB 연결 헬퍼 ──────────────────────────────────────────────────────────────
def _db_conn():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )

# Response Models
class MarketWeatherResponse(BaseModel):
    weather: str
    score: int
    recommendation: str
    hint: str

class TradingTrendResponse(BaseModel):
    date: str
    market: str
    institution: float
    foreign: float
    individual: float

class InvestorTradingRow(BaseModel):
    """당일 투자자별 매매동향(매도/매수/순매수, 십억원) — 단일 시장."""
    date: str
    market: str
    institution_sell: float
    institution_buy: float
    institution_net: float
    foreign_sell: float
    foreign_buy: float
    foreign_net: float
    individual_sell: float
    individual_buy: float
    individual_net: float

class MarketIndexResponse(BaseModel):
    market: str
    index: float
    change: float
    change_rate: float
    date: str

class StockRecommendationResponse(BaseModel):
    stock_code: str
    stock_name: str
    current_price: int
    recommendation_type: str
    reason: str

# 유틸리티 함수들
def get_trading_data(days_back: int = 5):
    """최근 N일간의 투자자별 매매동향 데이터 조회"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        fromdate = start_date.strftime("%Y%m%d")
        todate = end_date.strftime("%Y%m%d")
        
        # KOSPI 데이터 가져오기
        df_kospi = stock.get_market_trading_value_by_date(
            fromdate, todate, "KOSPI"
        )
        df_kospi["시장"] = "KOSPI"
        
        # KOSDAQ 데이터 가져오기
        df_kosdaq = stock.get_market_trading_value_by_date(
            fromdate, todate, "KOSDAQ"
        )
        df_kosdaq["시장"] = "KOSDAQ"
        
        # 합치기
        df_all = pd.concat([df_kospi, df_kosdaq])
        df_all = df_all.reset_index()
        
        return df_all
    except Exception as e:
        print(f"Error fetching trading data: {e}")
        return None

def calculate_market_score(institution: float, foreign: float, individual: float, market: str = "코스피") -> int:
    """투자자별 매매동향을 기반으로 시장 점수 계산 (0-100)"""
    # 억원 단위로 변환
    institution_billion = institution / 100_000_000
    foreign_billion = foreign / 100_000_000
    individual_billion = individual / 100_000_000
    
    # 코스닥은 기관 비중이 상대적으로 낮으므로 가중치 조정 (ex, 40% 수준)
    threshold_multiplier = 0.4 if market == "코스닥" else 1.0

    # 스케일링이 적용된 기준선 설정
    t_high = 1000 * threshold_multiplier
    t_mid = 500 * threshold_multiplier

    # 가중치 적용
    score = 50  # 기본 점수
    
    # 외국인 (45%)
    if foreign_billion > t_high:
        score += 22
    elif foreign_billion > t_mid:
        score += 15
    elif foreign_billion > 0:
        score += 8
    elif foreign_billion > -t_mid:
        score -= 8
    elif foreign_billion > -t_high:
        score -= 15
    else:
        score -= 22
    
    # 기관 (35%)
    if institution_billion > t_high:
        score += 17
    elif institution_billion > t_mid:
        score += 12
    elif institution_billion > 0:
        score += 6
    elif institution_billion > -t_mid:
        score -= 6
    elif institution_billion > -t_high:
        score -= 12
    else:
        score -= 17
    
    # 개인 (10% - 역방향)
    if individual_billion > t_high:
        score -= 5
    elif individual_billion > 0:
        score -= 3
    else:
        score += 3
    
    # 0-100 범위로 제한
    return max(0, min(100, score))

def get_weather_from_score(score: int) -> tuple:
    """점수를 기반으로 날씨와 추천 반환"""
    if score >= 80:
        return "맑음", "적극 매수 추천"
    elif score >= 60:
        return "구름조금", "종목 선별 매수"
    elif score >= 40:
        return "흐림", "관망 추천"
    else:
        return "비", "리스크 관리 필요"

def analyze_market_with_llm(trading_data: Dict) -> Dict:
    """LLM을 사용한 시장 분석 (OpenAI API 사용) - 코스피/코스닥 분리 적용"""
    market_type = trading_data.get("market", "코스피")
    institution = trading_data.get("institution", 0)
    foreign = trading_data.get("foreign", 0)
    individual = trading_data.get("individual", 0)

    # LLM 사용 불가 시 기본 분석으로 fallback
    if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
        score = calculate_market_score(institution, foreign, individual, market_type)
        weather, recommendation = get_weather_from_score(score)

        hint = f"[{market_type}] "
        if foreign > 0 and institution > 0:
            hint += "외국인과 기관이 함께 사고 있어요. 긍정적인 신호입니다!"
        elif foreign > 0:
            if market_type == "코스피":
                hint += "외국인이 많이 사고 있습니다. 우량주 위주로 살펴보세요."
            else:
                hint += "외국인 매수세가 들어오며 시장 분위기가 좋아지고 있어요."
        elif institution > 0:
            hint += "기관이 든든하게 받쳐주고 있어 비교적 안정적인 하루가 예상됩니다."
        else:
            hint += "지금은 파는 사람이 더 많네요. 무리한 투자보다는 상황을 지켜보는 것이 좋습니다."

        return {
            "weather": weather,
            "score": score,
            "recommendation": recommendation,
            "hint": hint
        }

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        if market_type == "코스피":
            market_context = "이 시장은 코스피(KOSPI)이며, KOSPI 200 우량 대형주 위주의 시장이야."
        elif market_type == "코스닥":
            market_context = "이 시장은 코스닥(KOSDAQ)이며, KOSDAQ 150 기술/성장주 위주로 코스피보다 변동성이 큰 시장이야."
        else:
            market_context = f"이 시장은 {market_type}이야."

        system_prompt = f"""너는 대한민국 주식 시장 수급 분석 전문가이자, 투자 입문자를 위한 친절한 투자 가이드야.
투자자별 매매동향 데이터를 분석하여 시장 점수(0~100)와 날씨를 판단해줘.

[현재 분석 시장]: {market_context}

가중치:
- 외국인: 45% (순매수가 클수록 긍정적)
- 기관: 35% (순매수가 클수록 긍정적)
- 개인: 10% (순매수가 클수록 단기 부정적 신호)

날씨 기준:
- 맑음 (80점↑): 외국인/기관 동반 순매수
- 구름조금 (60~79점): 외국인 또는 기관 중 하나만 매수
- 흐림 (40~59점): 외국인/기관 매도세
- 비 (40점↓): 외국인/기관 동반 투매

힌트는 투자 입문자가 이해하기 쉽게 1~2문장으로 다정하게 작성해줘."""

        user_content = f"""다음 수급 데이터를 분석해줘:
시장: {market_type}
기관 순매수: {institution:,.0f}원
외국인 순매수: {foreign:,.0f}원
개인 순매수: {individual:,.0f}원

JSON 형식으로만 답변:
{{"weather": "날씨", "score": 점수, "recommendation": "추천", "hint": "힌트"}}"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.7
        )

        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        print(f"LLM analysis error: {e}")
        score = calculate_market_score(institution, foreign, individual, market_type)
        weather, recommendation = get_weather_from_score(score)
        return {
            "weather": weather,
            "score": score,
            "recommendation": recommendation,
            "hint": "AI 분석을 불러오는 중입니다. 잠시만 기다려주세요!"
        }

# API 엔드포인트들
# API 엔드포인트들
@router.get("/trading-trends", response_model=List[TradingTrendResponse])
async def get_trading_trends(days: int = 5):
    """투자자별 매매동향.
    1순위: pykrx 실제 순매수 데이터 (억원)
    2순위: DB 시장 수익률 기반 추정치 (pykrx KRX API 오류 시 fallback)
    """
    # ── 1순위: pykrx ────────────────────────────────────────────────────────
    try:
        from pykrx import stock as pykrx_stock

        today = datetime.today()
        fromdate = (today - timedelta(days=days * 2 + 5)).strftime("%Y%m%d")
        todate   = today.strftime("%Y%m%d")

        results = []
        for market_code in ["KOSPI", "KOSDAQ"]:
            try:
                df = pykrx_stock.get_market_trading_value_by_date(
                    fromdate, todate, market_code
                )
                if df is None or df.empty:
                    continue

                def _col(candidates):
                    for c in candidates:
                        if c in df.columns:
                            return c
                    return None

                inst_col = _col(["기관합계", "기관", "기관계"])
                fore_col = _col(["외국인합계", "외국인", "외국인계"])
                indi_col = _col(["개인"])

                if not inst_col or not fore_col or not indi_col:
                    continue

                df = df.tail(days)
                market_name = "KOSPI" if market_code == "KOSPI" else "KOSDAQ"
                for idx, row in df.iterrows():
                    date_str = str(idx.date()) if hasattr(idx, 'date') else str(idx)
                    results.append({
                        "date":        date_str,
                        "market":      market_name,
                        "institution": round(float(row[inst_col]) / 1e8, 2),
                        "foreign":     round(float(row[fore_col]) / 1e8, 2),
                        "individual":  round(float(row[indi_col]) / 1e8, 2),
                    })
            except Exception as e:
                print(f"pykrx trading [{market_code}] 오류: {e}")
                continue

        if results:
            results.sort(key=lambda x: (x["date"], x["market"]), reverse=True)
            return results[:days * 2]

        print("pykrx 데이터 없음 → DB fallback")
    except Exception as e:
        print(f"pykrx import 오류: {e}")

    # ── 2순위: DB 기반 추정 (fallback) ───────────────────────────────────────
    try:
        conn = _db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT mp.price_date AS trade_date,
                   u.market,
                   AVG(mp.close) AS avg_close
            FROM market_prices mp
            JOIN universe_items u ON mp.instrument_id = u.instrument_id
            WHERE mp.price_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
              AND u.active = 1 AND u.asset_type = 'STOCK'
              AND mp.close > 0
            GROUP BY mp.price_date, u.market
            ORDER BY mp.price_date ASC, u.market
        """, (days * 2 + 10,))
        rows = cur.fetchall()
        conn.close()

        from collections import defaultdict
        by_market: dict = defaultdict(list)
        for row in rows:
            by_market[row["market"]].append(row)

        results = []
        for market, mrows in by_market.items():
            for i in range(1, len(mrows)):
                prev_close = float(mrows[i-1]["avg_close"])
                curr_close = float(mrows[i]["avg_close"])
                if prev_close <= 0:
                    continue
                avg_ret = (curr_close - prev_close) / prev_close * 100
                base = 5000 if market == "KOSPI" else 1500
                results.append({
                    "date":        str(mrows[i]["trade_date"]),
                    "market":      market,
                    "institution": round(avg_ret * base * 0.35 / 100, 0),
                    "foreign":     round(avg_ret * base * 0.45 / 100, 0),
                    "individual":  round(avg_ret * base * -0.20 / 100, 0),
                })

        # ── 오늘치: DB에 아직 없으면 KIS 투자자별 매매현황으로 보완 ──────────────
        today_str = datetime.today().strftime("%Y-%m-%d")
        try:
            from kis_client import get_investor_trading_best, get_index_price
            for market_code, market_name, base in [("KOSPI", "KOSPI", 5000), ("KOSDAQ", "KOSDAQ", 1500)]:
                if today_str not in {r["date"] for r in results if r["market"] == market_name}:
                    try:
                        inv = get_investor_trading_best(market_code)
                        # 新형식: institution_net(십억원) → 억원 × 10
                        results.append({
                            "date":        today_str,
                            "market":      market_name,
                            "institution": round(inv["institution_net"] * 10, 0),
                            "foreign":     round(inv["foreign_net"] * 10, 0),
                            "individual":  round(inv["individual_net"] * 10, 0),
                        })
                        print(f"KIS 투자자 데이터 사용 [{market_name}]: 기관={inv['institution_net']}십억, 외국={inv['foreign_net']}십억, 개인={inv['individual_net']}십억")
                    except Exception as e1:
                        print(f"KIS 투자자 조회 실패 [{market_name}]: {e1} → 등락률 추정 사용")
                        try:
                            d = get_index_price(market_code)
                            pct = d["change_rate"]
                            results.append({
                                "date":        today_str,
                                "market":      market_name,
                                "institution": round(pct * base * 0.35 / 100, 0),
                                "foreign":     round(pct * base * 0.45 / 100, 0),
                                "individual":  round(pct * base * -0.20 / 100, 0),
                            })
                        except Exception as e2:
                            print(f"오늘치 등락률 보완도 실패 [{market_name}]: {e2}")
        except Exception as e:
            print(f"오늘치 보완 오류: {e}")

        results.sort(key=lambda x: x["date"], reverse=True)
        return results[:days * 2]

    except Exception as e:
        print(f"DB fallback 오류: {e}")
        return []


@router.get("/investor-trading", response_model=List[InvestorTradingRow])
async def get_investor_trading_today():
    """당일 투자자별 매매동향 (KOSPI + KOSDAQ, 십억원).

    KIS 시세 API(FHPTJ04030000) 기준 실시간 누적 값을 반환합니다.
    매도/매수/순매수 모두 제공합니다.
    """
    from kis_client import get_investor_trading_best
    results: list = []
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            row = get_investor_trading_best(market)
            results.append(row)
        except Exception as e:
            print(f"investor-trading [{market}] 오류: {e}")
    return results


@router.get("/market-weather", response_model=MarketWeatherResponse)
async def get_market_weather(market: str = "KOSPI"):
    """KIS API 지수 등락률로 시장 날씨 산출 (market-indices 캐시 재사용)"""
    from kis_client import get_index_price
    import time

    cache_key = f"index_{market.upper()}"
    now = time.time()
    cached = _index_cache.get(cache_key)

    d = None
    if cached and now - cached["ts"] < 300:
        d = cached["data"]
    else:
        try:
            raw = get_index_price(market)
            d = {
                "market":      raw["market"],
                "index":       raw["index"],
                "change":      raw["change"],
                "change_rate": raw["change_rate"],
                "date":        raw["price_date"],
            }
            _index_cache[cache_key] = {"data": d, "ts": now}
        except Exception as e:
            print(f"KIS 지수 조회 실패 [{market}]: {e}")
            if cached:
                d = cached["data"]

    if d is None:
        return {"weather": "흐림", "score": 50, "recommendation": "관망 추천", "hint": "지수 데이터 조회 실패"}

    pct = d["change_rate"]
    index_label = f"{d['market']} {d['index']:,.2f}pt ({pct:+.2f}%)"

    # pykrx 실제 투자자별 수급 데이터 시도, 실패 시 등락률 프록시로 fallback
    try:
        trading_data = _get_pykrx_trading(market)
        data_source = f"수급기준 {trading_data['date']}"
    except Exception:
        scale = pct * 1_000_000_000_000
        trading_data = {
            "market":      "코스피" if market.upper() == "KOSPI" else "코스닥",
            "institution": scale * 0.35,
            "foreign":     scale * 0.45,
            "individual":  -scale * 0.10,
        }
        data_source = "지수등락률 기반 추정"

    result = analyze_market_with_llm(trading_data)
    result["hint"] = f"{index_label} ({data_source}) | " + result["hint"]
    return result


@router.get("/market-indices", response_model=List[MarketIndexResponse])
async def get_market_indices():
    """KIS API로 KOSPI/KOSDAQ 실시간 지수 조회 (5분 TTL 캐시)"""
    from kis_client import get_index_price
    import time

    results = []
    for market_code in ["KOSPI", "KOSDAQ"]:
        # 5분 TTL 캐시
        cache_key = f"index_{market_code}"
        now = time.time()
        cached = _index_cache.get(cache_key)
        if cached and now - cached["ts"] < 300:
            results.append(cached["data"])
            continue

        try:
            d = get_index_price(market_code)
            item = {
                "market":      d["market"],
                "index":       d["index"],
                "change":      d["change"],
                "change_rate": d["change_rate"],
                "date":        d["price_date"],
            }
            _index_cache[cache_key] = {"data": item, "ts": now}
            results.append(item)
        except Exception as e:
            print(f"KIS 지수 조회 실패 [{market_code}]: {e}")
            # 캐시 만료된 값이라도 사용
            if cached:
                results.append(cached["data"])

    if not results:
        raise HTTPException(status_code=502, detail="KIS 지수 조회 실패")
    return results

@router.get("/stock-recommendations", response_model=List[StockRecommendationResponse])
async def get_stock_recommendations():
    """종목 추천 목록 (더미 데이터)"""
    # 실제로는 DB나 추천 알고리즘에서 가져와야 함
    return [
        {
            "stock_code": "005930",
            "stock_name": "삼성전자",
            "current_price": 75000,
            "recommendation_type": "매수",
            "reason": "반도체 업황 개선 기대"
        },
        {
            "stock_code": "000660",
            "stock_name": "SK하이닉스",
            "current_price": 145000,
            "recommendation_type": "매수",
            "reason": "HBM 수요 증가"
        },
        {
            "stock_code": "035420",
            "stock_name": "NAVER",
            "current_price": 220000,
            "recommendation_type": "보유",
            "reason": "AI 서비스 확대"
        }
    ]

@router.get("/portfolio-recommendations")
async def get_portfolio_recommendations():
    """포트폴리오 추천 목록 (더미 데이터)"""
    return {
        "portfolios": [
            {
                "name": "안정형 포트폴리오",
                "stocks": ["005930", "000660", "051910"],
                "expected_return": 8.5,
                "risk_level": "낮음"
            },
            {
                "name": "성장형 포트폴리오",
                "stocks": ["035420", "035720", "068270"],
                "expected_return": 15.2,
                "risk_level": "중간"
            }
        ]
    }
