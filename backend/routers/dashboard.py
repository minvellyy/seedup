from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
import json
import os
import sys
import pymysql
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

# ── 포트폴리오 파일 캐시 경로 ───────────────────────────────────────────────────
_PF_CACHE_DIR = Path(__file__).parent.parent / "portfolio_cache"
_PF_CACHE_DIR.mkdir(exist_ok=True)

import logging as _logging
_cache_logger = _logging.getLogger(__name__)


def _json_default(obj):
    """json.dumps 의 default 핸들러 — numpy/Pydantic/datetime 타입을 안전하게 변환합니다."""
    # numpy 스칼라 / 배열
    try:
        import numpy as _np
        if isinstance(obj, _np.integer):
            return int(obj)
        if isinstance(obj, _np.floating):
            return float(obj)
        if isinstance(obj, _np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    # datetime / date
    from datetime import datetime as _dt, date as _d
    if isinstance(obj, (_dt, _d)):
        return obj.isoformat()
    # Pydantic v2 모델
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    # Pydantic v1 모델
    if hasattr(obj, "dict"):
        return obj.dict()
    return str(obj)


def _safe_model_dump(obj) -> dict:
    """Pydantic v1/v2 공통 dict 변환 — mode='json' 으로 JSON 직렬화 가능 보장."""
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except TypeError:
            return obj.model_dump()
    return obj.dict()


def _pf_cache_path(user_id: int) -> Path:
    return _PF_CACHE_DIR / f"user_{user_id}_portfolio.json"


def _load_pf_cache(user_id: int):
    """파일 캐시에서 포트폴리오를 읽어 반환합니다. 없으면 None."""
    p = _pf_cache_path(user_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_pf_cache(user_id: int, portfolios: list):
    """포트폴리오를 파일 캐시에 저장합니다."""
    try:
        data = {"saved_at": datetime.utcnow().isoformat(), "portfolios": portfolios}
        _pf_cache_path(user_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        _cache_logger.info("포트폴리오 캐시 저장 완료: user_%s_portfolio.json", user_id)
    except Exception as e:
        _cache_logger.warning("포트폴리오 캐시 저장 실패 (user_id=%s): %s", user_id, e)


# ── 종목 추천 파일 캐시 ──────────────────────────────────────────────────────────
def _stock_rec_cache_path(user_id: int) -> Path:
    return _PF_CACHE_DIR / f"user_{user_id}_stock_rec.json"


def _load_stock_rec_cache(user_id: int):
    """파일 캐시에서 종목 추천을 읽어 반환합니다. 없으면 None."""
    p = _stock_rec_cache_path(user_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_stock_rec_cache(user_id: int, data: dict):
    """종목 추천을 파일 캐시에 저장합니다."""
    try:
        payload = {"saved_at": datetime.utcnow().isoformat(), "data": data}
        _stock_rec_cache_path(user_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        _cache_logger.info("종목 추천 캐시 저장 완료: user_%s_stock_rec.json", user_id)
    except Exception as e:
        _cache_logger.warning("종목 추천 캐시 저장 실패 (user_id=%s): %s", user_id, e)


# ── 종목/포트폴리오 추천 모델 연결 ─────────────────────────────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

try:
    from stock_model import get_stock_recommendations as _get_stock_rec                      # noqa: E402
    from portfolio_model import get_portfolio_recommendation as _get_portfolio_rec            # noqa: E402
    from portfolio_model import get_multi_portfolio_recommendations as _get_multi_pf_rec     # noqa: E402
    from portfolio_model import recommend_stock_with_signals as _recommend_stock_mc          # noqa: E402
    from portfolio_model import get_multi_portfolio_with_signals as _get_multi_pf_mc         # noqa: E402
    from schemas import (                                                                     # noqa: E402
        StockRecommendationResponse as _StockRecResponse,
        PortfolioRecommendationResponse as _PortfolioRecResponse,
    )
    _MODELS_AVAILABLE = True
except ImportError as _model_import_err:
    _MODELS_AVAILABLE = False
    _MODELS_IMPORT_ERR = str(_model_import_err)

# ── CrewAI 매니저 에이전트 연동 (crewai 없어도 서버 기동 가능) ─────────────────
try:
    from manager_agent.crew import run_manager_analysis as _run_manager_analysis  # noqa: E402
    from manager_agent.crew import run_portfolio_recommendation as _run_portfolio_recommendation  # noqa: E402
    from manager_agent.crew import run_stock_recommendation as _run_stock_recommendation          # noqa: E402
    from manager_agent.crew import run_mc_explanation_agent as _run_mc_explanation_agent          # noqa: E402
    _CREW_AVAILABLE = True
except Exception as _crew_err:
    _CREW_AVAILABLE = False
    _CREW_ERR_MSG = str(_crew_err)


def _make_analysis_llm():
    """MANAGER_LLM_MODEL 환경변수 기반 LLM 객체 생성."""
    model = os.getenv("MANAGER_LLM_MODEL", "openai/gpt-4o-mini")
    try:
        from crewai import LLM
        return LLM(model=model)
    except (ImportError, AttributeError):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model.replace("openai/", ""))


def _load_signal_fin_data(top_n: int = 25) -> tuple:
    """
    signal_pack_latest.csv와 fin_scores parquet을 직접 로드합니다.
    Returns: (signal_tickers, fin_scores)
      signal_tickers: [{ticker, name, market, p_adj, rank_overall}, ...] 상위 top_n
      fin_scores: {ticker: {overall_grade, overall_score}}
    """
    signal_tickers = []
    fin_scores: dict = {}
    try:
        import pandas as pd
        from config import SIGNAL_PACK_PATH, FIN_MODEL_DIR  # type: ignore
        from pathlib import Path as _Path

        # signal pack
        if SIGNAL_PACK_PATH.exists():
            df = pd.read_csv(SIGNAL_PACK_PATH, dtype={"ticker": str})
            df_stock = df[df["asset_type"] == "stock"].copy()
            df_top = df_stock.sort_values("rank_overall").head(top_n)
            for _, row in df_top.iterrows():
                signal_tickers.append({
                    "ticker": str(row["ticker"]).zfill(6),
                    "name": str(row["name"]) if pd.notna(row.get("name")) else "",
                    "market": "KOSPI",
                    "p_adj": float(row["p_adj"]) if pd.notna(row.get("p_adj")) else 0.5,
                    "rank_overall": int(row["rank_overall"]) if pd.notna(row.get("rank_overall")) else 999,
                })

        # fin scores parquet
        parquet_path = _Path(FIN_MODEL_DIR) / "data" / "processed" / "fin_scores_v2_2024_CONSOL_with_mc_with_price.parquet"
        if parquet_path.exists() and signal_tickers:
            codes = {s["ticker"] for s in signal_tickers}
            df_fin = pd.read_parquet(parquet_path)
            df_sub = df_fin[df_fin["ticker"].astype(str).str.zfill(6).isin(codes)]
            date_col = "as_of" if "as_of" in df_sub.columns else df_sub.columns[0]
            for t, grp in df_sub.groupby("ticker"):
                row = grp.sort_values(date_col).iloc[-1]
                fin_scores[str(t).zfill(6)] = {
                    "overall_grade": str(row.get("overall_grade") or "") or None,
                    "overall_score": float(row["overall_score"]) if pd.notna(row.get("overall_score")) else None,
                }
    except Exception:
        pass
    return signal_tickers, fin_scores

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

# ── KIS 수급 캐시 (30분 TTL — 일별 데이터라 자주 변하지 않음) ─────────────────
# { "trading_KOSPI": {"data": {...}, "ts": float}, ... }
_trading_cache: dict = {}


def _get_kis_trading(market_code: str) -> Dict:
    """KIS FHPTJ04040000으로 최근 영업일 투자자별 순매수 (억원) 반환.

    Returns:
        {"market": "코스피", "institution": float, "foreign": float, "individual": float,
         "date": "YYYY-MM-DD"}  단위: 억원
    """
    import time
    cache_key = f"trading_{market_code.upper()}"
    cached = _trading_cache.get(cache_key)
    if cached and time.time() - cached["ts"] < 1800:  # 30분 TTL
        return cached["data"]

    from kis_client import get_investor_trading_history
    rows = get_investor_trading_history(market_code, days=1)
    if not rows:
        raise ValueError(f"KIS 수급 데이터 없음 [{market_code}]")

    row = rows[0]
    market_name = "코스피" if market_code.upper() == "KOSPI" else "코스닥"
    # get_investor_trading_history 반환 단위: 억원 → 원으로 변환 (기존 analyze_market_with_llm과 호환)
    data = {
        "market":      market_name,
        "institution": row["institution"] * 1e8,
        "foreign":     row["foreign"]     * 1e8,
        "individual":  row["individual"]  * 1e8,
        "date":        row["date"],
    }
    _trading_cache[cache_key] = {"data": data, "ts": time.time()}
    return data

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


def _get_db_conn_dep():
    """FastAPI Dependency: DB 연결 생성 후 요청이 끝나면 자동 닫음."""
    conn = _db_conn()
    try:
        yield conn
    finally:
        conn.close()

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
    1순위: KRX 직접 HTTP 수급 데이터 (억원)
    2순위: DB 시장 수익률 기반 추정치 (KRX API 오류 시 fallback)
    """
    # ── 1순위: KIS FHPTJ04040000 히스토리 조회 ──────────────────────────────
    try:
        from kis_client import get_investor_trading_history

        results = []
        for market_code in ["KOSPI", "KOSDAQ"]:
            try:
                rows = get_investor_trading_history(market_code, days=days)
                results.extend(rows)
            except Exception as e:
                print(f"KIS trading history [{market_code}] 오류: {e}")
                continue

        if results:
            results.sort(key=lambda x: (x["date"], x["market"]), reverse=True)
            return results[:days * 2]

        print("KIS 수급 데이터 없음 → DB fallback")
    except Exception as e:
        print(f"KIS 수급 조회 오류: {e}")

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

    KIS 일별 API(FHPTJ04040000) 기준 당일 누적 순매수를 반환합니다.
    매도/매수는 미제공(0 반환) — 프론트엔드에서 '-'로 표시합니다.
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

    # KIS 투자자별 수급 데이터 시도, 실패 시 등락률 프록시로 fallback
    try:
        trading_data = _get_krx_trading(market)
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


@router.get("/crew-status")
async def get_crew_status():
    """CrewAI 로드 상태 진단 엔드포인트."""
    return {
        "crew_available": _CREW_AVAILABLE,
        "crew_error": _CREW_ERR_MSG if not _CREW_AVAILABLE else None,
        "models_available": _MODELS_AVAILABLE,
        "models_error": _MODELS_IMPORT_ERR if not _MODELS_AVAILABLE else None,
        "has_run_stock_recommendation": _CREW_AVAILABLE and callable(globals().get("_run_stock_recommendation")),
    }


@router.get("/stock-recommendations")
async def get_stock_recommendations_dashboard(
    user_id: int,
    koscom_score: int = 20,
    refresh: bool = False,
    conn=Depends(_get_db_conn_dep),
):
    """종목 Top5 추천.

    실행 흐름:
      1. Monte Carlo (주 모델) — LightGBM 신호 + 재무등급을 입력 받아 MC로 종목 선정
      2. CrewAI 설명 에이전트 — 선정된 종목에 대해 방향성/재무 조회 후 설명문 추가
      3. 폴백 — MC 모델 실패 시 DB 계량 모델 사용

    - refresh=false(기본): 캐시 반환
    - refresh=true: 재실행 후 캐시 갱신
    """
    # ── 파일 캐시 ──────────────────────────────────────────────────────────
    if not refresh:
        cached = _load_stock_rec_cache(user_id)
        if cached and cached.get("data"):
            return cached["data"]

    # ── 사용자 투자성향 조회 ─────────────────────────────────────────────
    inv_type = "위험중립형"
    try:
        cur = conn.cursor()
        cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row and row.get("investment_type"):
            inv_type = row["investment_type"]
        else:
            for score, lv in _KOSCOM_TO_INV:
                if koscom_score >= score:
                    inv_type = lv
                    break
    except Exception:
        pass

    # ── 1단계: 신호+재무 데이터 직접 로드 (빠름) ─────────────────────────
    signal_tickers, fin_scores = _load_signal_fin_data(top_n=25)
    signal_map = {s["ticker"]: s for s in signal_tickers}

    # ── 2단계: Monte Carlo 주 모델로 종목 선정 ────────────────────────────
    result_dict: dict | None = None
    if signal_tickers and _MODELS_AVAILABLE:
        try:
            mc_rec = await asyncio.to_thread(
                _recommend_stock_mc,
                user_id, conn, signal_tickers, fin_scores, koscom_score,
            )
            result_dict = _safe_model_dump(mc_rec)
        except Exception:
            result_dict = None

    # MC 모델 실패 → DB 계량 폴백
    if result_dict is None:
        if not _MODELS_AVAILABLE:
            raise HTTPException(status_code=503, detail=f"모델 로드 실패: {_MODELS_IMPORT_ERR}")
        try:
            fb = await asyncio.to_thread(_get_stock_rec, user_id=user_id, conn=conn, koscom_score=koscom_score)
            result_dict = _safe_model_dump(fb)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"종목 추천 오류: {e}")

    # ── 3단계: CrewAI 설명 에이전트 (선정 결과에 설명 추가) ──────────────
    if _CREW_AVAILABLE and result_dict:
        try:
            mc_summary = json.dumps([
                {
                    "rank": it["rank"], "ticker": it["ticker"], "name": it["name"],
                    "mc_p10": it["features"].get("vol_ann"),
                    "mc_p50": round(float(it["features"].get("ret_1y") or 0) * 100, 1),
                    "reasons": it.get("reasons", []),
                }
                for it in result_dict.get("items", [])
            ], ensure_ascii=False)
            llm = _make_analysis_llm()
            exp_raw = await asyncio.wait_for(
                asyncio.to_thread(_run_mc_explanation_agent,
                                  llm=llm,
                                  mc_items_json=mc_summary,
                                  user_risk_tier=inv_type,
                                  mode="stock"),
                timeout=120.0,
            )
            try:
                exp_list = json.loads(exp_raw) if isinstance(exp_raw, str) else exp_raw
                if isinstance(exp_list, list):
                    exp_map = {e["ticker"]: e.get("explanation", "") for e in exp_list if "ticker" in e}
                    for it in result_dict["items"]:
                        if it["ticker"] in exp_map and exp_map[it["ticker"]]:
                            it["explanation"] = exp_map[it["ticker"]]
            except Exception:
                pass
        except (asyncio.TimeoutError, Exception):
            pass  # 설명 실패해도 MC 결과는 그대로 반환

    _save_stock_rec_cache(user_id, result_dict)
    return result_dict


@router.get("/portfolio-recommendations", response_model=_PortfolioRecResponse if _MODELS_AVAILABLE else None)
async def get_portfolio_recommendations_dashboard(
    user_id: int,
    koscom_score: int = 20,
    conn=Depends(_get_db_conn_dep),
):
    """사용자 투자성향 기반 포트폴리오 추천 (portfolio_model 연결)."""
    if not _MODELS_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"모델 로드 실패: {_MODELS_IMPORT_ERR}")
    try:
        return _get_portfolio_rec(user_id=user_id, conn=conn, koscom_score=koscom_score)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포트폴리오 추천 모델 오류: {e}")


@router.get("/portfolio-recommendations-multi")
async def get_portfolio_recommendations_multi_dashboard(
    user_id: int,
    koscom_score: int = 20,
    conn=Depends(_get_db_conn_dep),
):
    """균형/모멘텀/저변동 3가지 스타일 포트폴리오를 배열로 반환 (대시보드 미리보기용)."""
    if not _MODELS_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"모델 로드 실패: {_MODELS_IMPORT_ERR}")
    try:
        return _get_multi_pf_rec(user_id=user_id, conn=conn, koscom_score=koscom_score)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포트폴리오 멀티 추천 오류: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CrewAI 통합 포트폴리오 추천 (방향성 신호 + 재무 분석 + LLM 포트폴리오 구성)
# ─────────────────────────────────────────────────────────────────────────────

_KOSCOM_TO_INV = [(30, "공격투자형"), (25, "적극투자형"), (20, "위험중립형"), (15, "안전추구형"), (0, "안정형")]


def _enrich_portfolio_quant_signals(portfolios: list) -> list:
    """각 포트폴리오에 단기 방향성 신호(p_adj), 기대수익률(ret_12m), 리스크(vol_3m)를 추가합니다.
    signal_pack_latest.csv 와 fin_scores parquet 에서 가중평균을 계산합니다."""
    import math

    try:
        import pandas as pd
        from config import SIGNAL_PACK_PATH, FIN_MODEL_DIR

        _parquet_path = Path(FIN_MODEL_DIR) / "data" / "processed" / "fin_scores_v2_2024_CONSOL_with_mc_with_price.parquet"

        # signal_pack 로드 (ticker를 6자리 zfill로 통일)
        sig_latest = None
        if Path(SIGNAL_PACK_PATH).exists():
            sig_df = pd.read_csv(SIGNAL_PACK_PATH, dtype={"ticker": str})
            sig_df["ticker"] = sig_df["ticker"].str.zfill(6)
            sig_latest = sig_df.sort_values("date").groupby("ticker", as_index=False).last()

        # fin parquet 로드 (최신 as_of 기준으로 1행만)
        fin_latest = None
        if _parquet_path.exists():
            fin_df = pd.read_parquet(_parquet_path)
            fin_df["ticker"] = fin_df["ticker"].astype(str).str.zfill(6)
            fin_latest = fin_df.sort_values("as_of").groupby("ticker", as_index=False).last()

        def _safe(v):
            """NaN/None → None, 나머지 float"""
            if v is None:
                return None
            try:
                f = float(v)
                return None if math.isnan(f) else f
            except (TypeError, ValueError):
                return None

        for pf in portfolios:
            items = pf.get("portfolio_items", [])
            if not items:
                continue
            total_weight = sum(it.get("weight_pct", 0) for it in items) or 100.0

            st_items, mt_items, risk_items = [], [], []

            for it in items:
                t = str(it.get("ticker", "")).zfill(6)
                w_pct = it.get("weight_pct", 0)
                nm = it.get("name") or t

                p_adj = ret_12m = vol_3m = None

                if sig_latest is not None:
                    row = sig_latest[sig_latest["ticker"] == t]
                    if not row.empty:
                        p_adj = _safe(row.iloc[0].get("p_adj"))

                if fin_latest is not None:
                    row = fin_latest[fin_latest["ticker"] == t]
                    if not row.empty:
                        ret_12m = _safe(row.iloc[0].get("ret_12m"))
                        vol_3m  = _safe(row.iloc[0].get("vol_3m"))

                st_items.append({"ticker": t, "name": nm, "weight_pct": w_pct,
                                 "p_adj": round(p_adj, 4) if p_adj is not None else None})
                mt_items.append({"ticker": t, "name": nm, "weight_pct": w_pct,
                                 "ret_12m_pct": round(ret_12m * 100, 2) if ret_12m is not None else None})
                risk_items.append({"ticker": t, "name": nm, "weight_pct": w_pct,
                                   "vol_3m_pct": round(vol_3m * 100, 2) if vol_3m is not None else None})

            def _wavg(lst, key):
                pairs = [(it["weight_pct"] / total_weight, it[key]) for it in lst if it.get(key) is not None]
                if not pairs:
                    return None
                tw = sum(w for w, _ in pairs)
                return round(sum(w * v for w, v in pairs) / tw, 4) if tw > 0 else None

            pf["quant_signals"] = {
                "short_term": {
                    "weighted_p_adj": _wavg(st_items, "p_adj"),
                    "items": st_items,
                },
                "medium_term": {
                    "weighted_ret_12m_pct": (_wavg(mt_items, "ret_12m_pct") or None) and
                                            round((_wavg(mt_items, "ret_12m_pct") or 0), 2),
                    "items": mt_items,
                },
                "risk": {
                    "weighted_vol_3m_pct": (_wavg(risk_items, "vol_3m_pct") or None) and
                                           round((_wavg(risk_items, "vol_3m_pct") or 0), 2),
                    "items": risk_items,
                },
            }
            # medium_term/risk wavg를 다시 계산(None 처리 버그 방지)
            pf["quant_signals"]["medium_term"]["weighted_ret_12m_pct"] = _wavg(mt_items, "ret_12m_pct")
            pf["quant_signals"]["risk"]["weighted_vol_3m_pct"] = _wavg(risk_items, "vol_3m_pct")

    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("quant signal enrichment failed: %s", _e)

    return portfolios


@router.get("/portfolio-recommendations-ai")
async def get_portfolio_recommendations_ai(
    user_id: int,
    koscom_score: int = 20,
    refresh: bool = False,
    conn=Depends(_get_db_conn_dep),
):
    """포트폴리오 추천.

    실행 흐름:
      1. Monte Carlo (주 모델) — LightGBM 신호 + 재무등급 부스팅으로 3가지 포트폴리오 구성
      2. CrewAI 설명 에이전트 — 선정 종목들에 자연어 설명 추가
      3. 정량 지표 후처리 (_enrich_portfolio_quant_signals)

    - refresh=false(기본): 캐시 반환
    - refresh=true: 재실행 후 캐시 갱신
    """
    # ── 파일 캐시 ──────────────────────────────────────────────────────────
    if not refresh:
        cached = _load_pf_cache(user_id)
        if cached:
            portfolios = cached.get("portfolios", [])
            if portfolios:
                for pf in portfolios:
                    pf["_cached_at"] = cached.get("saved_at")
                return portfolios

    # ── 사용자 투자성향 ───────────────────────────────────────────────────
    inv_type = "위험중립형"
    try:
        cur = conn.cursor()
        cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row and row.get("investment_type"):
            inv_type = row["investment_type"]
        else:
            for score, lv in _KOSCOM_TO_INV:
                if koscom_score >= score:
                    inv_type = lv
                    break
    except Exception:
        pass

    if not _MODELS_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"모델 로드 실패: {_MODELS_IMPORT_ERR}")

    # ── 1단계: 신호+재무 데이터 직접 로드 ────────────────────────────────
    signal_tickers, fin_scores = _load_signal_fin_data(top_n=25)
    signal_map = {s["ticker"]: s for s in signal_tickers}
    fin_map = {
        ticker: {
            "overall_grade": d.get("overall_grade"),
            "overall_score": d.get("overall_score"),
        }
        for ticker, d in fin_scores.items()
    }

    # ── 2단계: Monte Carlo 주 모델로 3가지 포트폴리오 구성 ────────────────
    try:
        pf_results: list = await asyncio.to_thread(
            _get_multi_pf_mc,
            user_id, conn,
            signal_map=signal_map,
            fin_map=fin_map,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포트폴리오 MC 모델 오류: {e}")

    # ── PortfolioRecommendationResponse → 프런트엔드 dict 변환 ────────────
    _STYLE_MAP = {
        "balanced": "균형 추천형",
        "aggressive": "공격 성장형",
        "conservative": "안전 추구형",
    }
    portfolios: list[dict] = []
    for pf in pf_results:
        pf_d = _safe_model_dump(pf)
        sty = pf_d.get("portfolio_style", "balanced")
        mc = pf_d.get("monte_carlo_1y") or {}
        mc_summary = ""
        if mc:
            mc_summary = (
                f"MC 1년 기대수익률: 하락 시나리오(P10) {mc.get('p10_pct', 0):+.1f}%, "
                f"중앙값(P50) {mc.get('p50_pct', 0):+.1f}%, "
                f"상승 시나리오(P90) {mc.get('p90_pct', 0):+.1f}%. "
                f"기대수익률 {mc.get('mean_pct', 0):+.1f}%, 연간변동성 {mc.get('vol_ann_pct', 0):.1f}%."
            )
        portfolios.append({
            "portfolio_label": pf_d.get("portfolio_label", _STYLE_MAP.get(sty, sty)),
            "portfolio_style": sty,
            "portfolio_summary": mc_summary or pf_d.get("portfolio_summary", ""),
            "risk_tier": inv_type,
            "portfolio_items": [
                {
                    "ticker": it.get("ticker", ""),
                    "name": it.get("name", ""),
                    "weight": it.get("weight", 0),
                    "weight_pct": it.get("weight_pct", 0),
                    "asset_type": it.get("asset_type", "STOCK"),
                    "selection_reason": it.get("selection_reason") or it.get("explanation", ""),
                    "ai_fin_grade": fin_map.get(it.get("ticker", ""), {}).get("overall_grade"),
                    "ai_strengths": [],
                    "ai_weaknesses": [],
                }
                for it in pf_d.get("portfolio_items", [])
            ],
            "monte_carlo_1y": mc,
        })

    # ── 3단계: CrewAI 설명 에이전트 (선정 종목 설명 보강) ────────────────
    if _CREW_AVAILABLE and portfolios:
        try:
            all_tickers = list({
                it["ticker"]
                for pf in portfolios
                for it in pf["portfolio_items"]
            })
            mc_items_for_exp = json.dumps([
                {"ticker": t, "name": signal_map.get(t, {}).get("name", "")}
                for t in all_tickers
            ], ensure_ascii=False)
            llm = _make_analysis_llm()
            exp_raw = await asyncio.wait_for(
                asyncio.to_thread(_run_mc_explanation_agent,
                                  llm=llm,
                                  mc_items_json=mc_items_for_exp,
                                  user_risk_tier=inv_type,
                                  mode="portfolio"),
                timeout=120.0,
            )
            try:
                exp_list = json.loads(exp_raw) if isinstance(exp_raw, str) else exp_raw
                if isinstance(exp_list, list):
                    exp_map = {e["ticker"]: e.get("explanation", "") for e in exp_list if "ticker" in e}
                    for pf in portfolios:
                        for it in pf["portfolio_items"]:
                            t = it["ticker"]
                            if t in exp_map and exp_map[t]:
                                it["selection_reason"] = exp_map[t]
            except Exception:
                pass
        except (asyncio.TimeoutError, Exception):
            pass  # 설명 실패해도 MC 포트폴리오 결과 반환

    # ── 4단계: 정량 지표 후처리 ──────────────────────────────────────────
    portfolios = _enrich_portfolio_quant_signals(portfolios)

    _save_pf_cache(user_id, portfolios)
    return portfolios


# ─────────────────────────────────────────────────────────────────────────────
# CrewAI 매니저 에이전트 기반 포트폴리오 종목 AI 분석 강화
# ─────────────────────────────────────────────────────────────────────────────

class PortfolioAiEnrichRequest(BaseModel):
    tickers: List[str]
    mode: str = "fin"   # "fin" (재무분석) | "signal" (방향성)


@router.post("/portfolio-ai-enrich")
async def portfolio_ai_enrich(req: PortfolioAiEnrichRequest):
    """포트폴리오 편입 종목들에 대해 manager_agent AI 분석을 실행합니다.

    - mode='fin'    : fin_structured_model 재무 데이터 + LLM 해석 (강점/약점)
    - mode='signal' : stock_direction_model LightGBM 방향성 신호 + LLM 해석

    Returns:
        { ticker: { selection_reason, signal_strength?, fin_grade?, ai_analysis } }
    """
    if not _CREW_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"CrewAI 매니저 에이전트를 사용할 수 없습니다: {_CREW_ERR_MSG}",
        )

    from concurrent.futures import ThreadPoolExecutor, as_completed

    mode = req.mode if req.mode in ("fin", "signal") else "fin"
    tickers = list(dict.fromkeys(req.tickers))[:12]  # 중복 제거, 최대 12개

    def _analyze(ticker: str) -> tuple:
        try:
            llm = _make_analysis_llm()
            raw = _run_manager_analysis(
                llm=llm,
                ticker=ticker,
                mode=mode,
                context_description="포트폴리오 추천 화면 — 편입 종목 재무·방향성 분석",
            )
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                # LLM이 JSON 블록으로 감싼 경우 추출 시도
                import re
                m = re.search(r'\{[\s\S]+\}', raw or "")
                parsed = json.loads(m.group()) if m else {"raw": raw}

            if mode == "fin":
                strengths = parsed.get("strengths", [])
                weaknesses = parsed.get("weaknesses", [])
                parts = []
                if strengths:
                    parts.append(strengths[0])
                if weaknesses:
                    parts.append(f"리스크: {weaknesses[0]}")
                selection_reason = " / ".join(parts) if parts else "AI 재무 분석 완료"
                result = {
                    "selection_reason": selection_reason,
                    "fin_grade": parsed.get("overall_grade"),
                    "fin_score": parsed.get("overall_score"),
                    "strengths": parsed.get("strengths", []),
                    "weaknesses": parsed.get("weaknesses", []),
                    "key_metrics": parsed.get("key_metrics"),
                    "ai_analysis": parsed,
                }
            else:  # signal
                signal = parsed.get("signal_strength", "")
                interp = parsed.get("interpretation", "")
                selection_reason = f"[{signal}] {interp}" if signal else "AI 방향성 분석 완료"
                result = {
                    "selection_reason": selection_reason,
                    "signal_strength": signal,
                    "p_up": parsed.get("p_up"),
                    "regime": parsed.get("regime"),
                    "ai_analysis": parsed,
                }
            return ticker, result
        except Exception as exc:
            return ticker, {"error": str(exc), "selection_reason": None}

    results: dict = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_analyze, t): t for t in tickers}
        for future in as_completed(futures, timeout=120):
            try:
                t, data = future.result(timeout=110)
            except Exception as exc:
                t = futures[future]
                data = {"error": f"타임아웃 또는 분석 실패: {exc}", "selection_reason": None}
            results[t] = data

    return results


# ── 포트폴리오 리스크 자연어 분석 ─────────────────────────────────────────────

class PortfolioRiskItem(BaseModel):
    ticker: str
    name: str


class PortfolioRiskRequest(BaseModel):
    items: List[PortfolioRiskItem]
    risk_tier: str = ""


@router.post("/portfolio-risk-analysis")
async def portfolio_risk_analysis(req: PortfolioRiskRequest):
    """포트폴리오 편입 종목들의 리스크를 뉴스 RAG + LLM으로 자연어 분석합니다.

    뉴스 RAG(ChromaDB)에서 각 종목의 리스크 관련 뉴스를 검색하고,
    LLM이 전체 포트폴리오 리스크 요약 및 종목별 리스크를 한국어 자연어로 작성합니다.

    Returns:
        {
          "risk_summary": str,           // 전체 포트폴리오 리스크 2-3문장 요약
          "per_stock": [                  // 종목별 리스크 설명
            {"ticker": str, "name": str, "risk_text": str}
          ]
        }
    """
    if not _CREW_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"CrewAI 매니저 에이전트를 사용할 수 없습니다: {_CREW_ERR_MSG}",
        )

    from crewai import Agent, Task, Crew
    from concurrent.futures import ThreadPoolExecutor

    items = req.items[:10]  # 최대 10개
    risk_tier_label = f" ({req.risk_tier})" if req.risk_tier else ""

    # ── 각 종목에 대한 뉴스 컨텍스트 수집 ──────────────────────────────────────
    news_contexts: dict = {}
    try:
        from news_model.pipeline_news_analysis_mvp import search_news_context

        def _fetch_news(item: PortfolioRiskItem):
            query = f"{item.name} 리스크 위험 요인 시장 환경"
            results = search_news_context(query, n_results=4)
            snippets = []
            for r in results:
                doc = r.get("doc", "")
                if doc:
                    snippets.append(doc[:300])
            return item.ticker, "\n".join(snippets) if snippets else "관련 뉴스 없음"

        with ThreadPoolExecutor(max_workers=4) as pool:
            for ticker, ctx in pool.map(_fetch_news, items):
                news_contexts[ticker] = ctx
    except Exception as e:
        _cache_logger.warning("뉴스 컨텍스트 수집 실패: %s", e)
        for item in items:
            news_contexts[item.ticker] = "뉴스 데이터를 불러올 수 없습니다."

    # ── LLM 프롬프트용 뉴스 텍스트 구성 ─────────────────────────────────────────
    news_block = ""
    for item in items:
        ctx = news_contexts.get(item.ticker, "관련 뉴스 없음")
        news_block += (
            f"\n## {item.name} ({item.ticker})\n"
            f"{ctx}\n"
        )

    ticker_names = ", ".join(f"{item.name}({item.ticker})" for item in items)

    # ── CrewAI 에이전트로 자연어 리스크 분석 ────────────────────────────────────
    llm = _make_analysis_llm()
    from crewai import Agent, Task, Crew

    risk_analyst = Agent(
        role="포트폴리오 리스크 분석 전문가",
        goal=(
            "포트폴리오에 편입된 종목들의 뉴스 데이터를 바탕으로 "
            "투자자가 이해하기 쉬운 자연어 리스크 분석을 제공한다."
        ),
        backstory=(
            "CFA 자격증을 보유한 리스크 전문가로, 뉴스와 시장 동향에서 "
            "기업별 핵심 리스크를 추출하고 일반 투자자에게 쉽게 설명하는 데 특화되어 있다. "
            "전문 용어 없이 누구나 이해할 수 있는 명확한 언어로 리스크를 전달한다."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    task_desc = (
        f"다음 포트폴리오{risk_tier_label}에 편입된 종목들의 리스크를 분석하라.\n\n"
        f"포트폴리오 종목: {ticker_names}\n\n"
        f"[종목별 뉴스 컨텍스트]\n{news_block}\n\n"
        "분석 지침:\n"
        "1. 각 종목별로 뉴스 컨텍스트에서 주요 리스크 요인을 1-2문장으로 파악하라.\n"
        "2. 전체 포트폴리오의 공통 리스크 테마(예: 환율, 금리, 글로벌 수요 등)를 파악하라.\n"
        "3. 전문 용어는 쉽게 풀어서 설명하라.\n"
        "4. 뉴스가 없으면 종목 일반 특성 기반으로 대략적 리스크를 언급하라.\n\n"
        "반드시 아래 JSON 형식으로만 응답하라. 추가 설명 없이 JSON만 출력하라:\n"
        "{\n"
        '  "risk_summary": "전체 포트폴리오 리스크를 2-3문장으로 요약한 한국어 텍스트",\n'
        '  "per_stock": [\n'
        '    {"ticker": "종목코드", "name": "종목명", "risk_text": "해당 종목 리스크 1-2문장 한국어 설명"},\n'
        "    ...\n"
        "  ]\n"
        "}"
    )

    task = Task(
        description=task_desc,
        expected_output=(
            "포트폴리오 전체 리스크 요약과 종목별 리스크 설명이 담긴 JSON 문자열. "
            "risk_summary(str)와 per_stock(list) 필드를 포함해야 한다."
        ),
        agent=risk_analyst,
    )

    crew = Crew(agents=[risk_analyst], tasks=[task], verbose=False)
    raw = crew.kickoff()
    raw_str = str(raw) if not isinstance(raw, str) else raw

    # JSON 파싱
    try:
        import re as _re
        m = _re.search(r'\{[\s\S]+\}', raw_str)
        parsed = json.loads(m.group()) if m else {}
    except (json.JSONDecodeError, AttributeError):
        parsed = {}

    # 파싱 실패 시 기본값
    risk_summary = parsed.get("risk_summary") or raw_str[:500]
    per_stock_raw = parsed.get("per_stock", [])

    # 빠진 종목 보완
    per_stock_tickers = {p.get("ticker") for p in per_stock_raw}
    for item in items:
        if item.ticker not in per_stock_tickers:
            per_stock_raw.append({
                "ticker": item.ticker,
                "name": item.name,
                "risk_text": "분석 데이터가 부족합니다.",
            })

    return {
        "risk_summary": risk_summary,
        "per_stock": per_stock_raw,
    }
