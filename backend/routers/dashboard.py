from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
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


_REC_CACHE_TTL_SECONDS = 6 * 3600   # 추천 캐시 유효기간 6시간


def _load_pf_cache(user_id: int):
    """파일 캐시에서 포트폴리오를 읽어 반환합니다. 없거나 TTL 만료 시 None."""
    p = _pf_cache_path(user_id)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            saved_at = data.get("saved_at")
            if saved_at:
                from datetime import timezone
                age = (datetime.utcnow() - datetime.fromisoformat(saved_at)).total_seconds()
                if age > _REC_CACHE_TTL_SECONDS:
                    _cache_logger.info("포트폴리오 캐시 TTL 만료 (user_id=%s, age=%.0fh)", user_id, age / 3600)
                    return None
            return data
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
    """파일 캐시에서 종목 추천을 읽어 반환합니다. 없거나 TTL 만료 시 None."""
    p = _stock_rec_cache_path(user_id)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            saved_at = data.get("saved_at")
            if saved_at:
                from datetime import timezone
                age = (datetime.utcnow() - datetime.fromisoformat(saved_at)).total_seconds()
                if age > _REC_CACHE_TTL_SECONDS:
                    _cache_logger.info("종목 추천 캐시 TTL 만료 (user_id=%s, age=%.0fh)", user_id, age / 3600)
                    return None
            return data
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


def _save_portfolio_to_db(user_id: int, conn, pf_results: list):
    """포트폴리오 추천을 DB에 저장합니다 (히스토리 유지)."""
    _MULTI_CACHE_KEYS = ['pf_optimal', 'pf_growth', 'pf_stable']
    
    cur = conn.cursor()
    # 기존 ACTIVE 추천을 ARCHIVED로 변경
    cur.execute(
        """
        UPDATE portfolio_recommendations
        SET state = 'ARCHIVED'
        WHERE user_id = %s
          AND strategy_name IN ('pf_optimal', 'pf_growth', 'pf_stable')
          AND state = 'ACTIVE'
        """,
        (user_id,),
    )
    
    # 새 추천을 ACTIVE로 저장
    for key, rec in zip(_MULTI_CACHE_KEYS, pf_results):
        content_json = json.dumps(
            rec if isinstance(rec, dict) else _safe_model_dump(rec),
            ensure_ascii=False, default=_json_default,
        )
        cur.execute(
            """
            INSERT INTO portfolio_recommendations
                (user_id, strategy_name, strategy_content, state)
            VALUES (%s, %s, %s, 'ACTIVE')
            """,
            (user_id, key, content_json),
        )
    
    # 커밋하여 DB에 반영
    conn.commit()
    _cache_logger.info("포트폴리오 DB 저장 완료: user_id=%s", user_id)


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
    from manager_agent.crew import run_manager_analysis as _run_manager_analysis                          # noqa: E402
    from manager_agent.crew import run_portfolio_recommendation as _run_portfolio_recommendation          # noqa: E402
    from manager_agent.crew import run_stock_recommendation as _run_stock_recommendation                  # noqa: E402
    from manager_agent.crew import run_mc_explanation_agent as _run_mc_explanation_agent                  # noqa: E402
    from manager_agent.crew import run_mc_final_selection_agent as _run_mc_final_selection_agent          # noqa: E402
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


def _load_signal_fin_data(top_n: int = 500, conn=None) -> tuple:
    """
    signal_pack_latest.csv와 fin_scores parquet을 직접 로드합니다.
    conn 제공 시 DB instruments에 존재하는 종목만 포함.
    DB 필터 적용 시 top_n 제한을 무시하고 교집합 전체를 반환합니다
    (signal rank로 자르면 고변동성 종목만 남아 개인화 불가).
    Returns: (signal_tickers, fin_scores)
      signal_tickers: [{ticker, name, market, p_adj, rank_overall}, ...]
      fin_scores: {ticker: {overall_grade, overall_score}}
    """
    signal_tickers = []
    fin_scores: dict = {}
    try:
        import pandas as pd
        from config import SIGNAL_PACK_PATH, FIN_MODEL_DIR  # type: ignore
        from pathlib import Path as _Path

        # DB 종목코드 집합 (conn 있을 때만)
        # DB 종목코드 + 이름 (conn 있을 때만)
        db_codes: set | None = None
        db_name_map: dict = {}
        if conn is not None:
            try:
                _cur = conn.cursor()
                _cur.execute("SELECT stock_code, name FROM instruments WHERE asset_type='STOCK'")
                for r in _cur.fetchall():
                    code = r[0] if isinstance(r, tuple) else r['stock_code']
                    name = r[1] if isinstance(r, tuple) else r['name']
                    db_name_map[code] = name
                db_codes = set(db_name_map.keys())
            except Exception:
                db_codes = None

        # signal pack
        if SIGNAL_PACK_PATH.exists():
            df = pd.read_csv(SIGNAL_PACK_PATH, dtype={"ticker": str})
            df_stock = df[df["asset_type"] == "stock"].copy()
            # DB 유니버스로 제한 (매칭 없으면 top_n으로 폴백)
            if db_codes:
                df_filtered = df_stock[df_stock["ticker"].str.zfill(6).isin(db_codes)]
                if not df_filtered.empty:
                    # DB 필터 적용 시 전체 교집합 사용 (top_n 제한 없음)
                    # signal rank로 자르면 고변동성 소형주만 남아 성향별 개인화 불가
                    df_stock = df_filtered.sort_values("rank_overall")
                else:
                    df_stock = df_stock.sort_values("rank_overall").head(top_n)
            else:
                df_stock = df_stock.sort_values("rank_overall").head(top_n)
            for _, row in df_stock.iterrows():
                ticker = str(row["ticker"]).zfill(6)
                csv_name = str(row["name"]) if pd.notna(row.get("name")) else ""
                signal_tickers.append({
                    "ticker": ticker,
                    "name": csv_name or db_name_map.get(ticker, ""),
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
            def _safe_float(row, key):
                try:
                    v = row.get(key)
                    return float(v) if v is not None and pd.notna(v) else None
                except Exception:
                    return None
            for t, grp in df_sub.groupby("ticker"):
                row = grp.sort_values(date_col).iloc[-1]
                fin_scores[str(t).zfill(6)] = {
                    "overall_grade": str(row.get("overall_grade") or "") or None,
                    "overall_score": _safe_float(row, "overall_score"),
                    # 세부 팩터 점수 (0~1 percentile) — 추천 스코어링에 직접 활용
                    "profitability_score": _safe_float(row, "profitability_score"),
                    "growth_score":        _safe_float(row, "growth_score"),
                    "stability_score":     _safe_float(row, "stability_score"),
                    "cashflow_score":      _safe_float(row, "cashflow_score"),
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
    score: float
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
def get_trading_trends(days: int = 5):
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
def get_investor_trading_today():
    """당일 투자자별 매매동향 (KOSPI + KOSDAQ, 십억원).

    KIS 일별 API(FHPTJ04040000) 기준 당일 누적 순매수를 반환합니다.
    매도/매수는 미제공(0 반환) — 프론트엔드에서 '-'로 표시합니다.
    """
    from kis_client import get_investor_trading_best
    results: list = [None, None]  # KOSPI=0, KOSDAQ=1 순서 유지
    markets = ["KOSPI", "KOSDAQ"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_map = {pool.submit(get_investor_trading_best, m): i for i, m in enumerate(markets)}
        for fut in as_completed(future_map):
            idx = future_map[fut]
            try:
                results[idx] = fut.result()
            except Exception:
                results[idx] = None  # 조용히 무시 — 장 외 시간/KRX 미응답 정상
    return [r for r in results if r is not None]


@router.get("/market-weather", response_model=MarketWeatherResponse)
def get_market_weather(market: str = "KOSPI"):
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
        trading_data = _get_kis_trading(market)
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
def get_market_indices():
    """KIS API로 KOSPI/KOSDAQ 실시간 지수 조회 (5분 TTL 캐시)"""
    from kis_client import get_index_price
    import time

    now = time.time()
    markets = ["KOSPI", "KOSDAQ"]

    def _fetch_index(market_code: str):
        cache_key = f"index_{market_code}"
        cached = _index_cache.get(cache_key)
        if cached and now - cached["ts"] < 300:
            return cached["data"]
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
            return item
        except Exception as e:
            print(f"KIS 지수 조회 실패 [{market_code}]: {e}")
            return cached["data"] if cached else None

    results = [None, None]
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_map = {pool.submit(_fetch_index, m): i for i, m in enumerate(markets)}
        for fut in as_completed(future_map):
            idx = future_map[fut]
            results[idx] = fut.result()

    filtered = [r for r in results if r is not None]
    if not filtered:
        raise HTTPException(status_code=502, detail="KIS 지수 조회 실패")
    return filtered


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
    signal_tickers, fin_scores = _load_signal_fin_data(conn=conn)
    signal_map = {s["ticker"]: s for s in signal_tickers}

    # ── 1.5단계: MC 입력 전 사전 필터 ────────────────────────────────────
    # 기획 의도: KOSPI200/KOSDAQ150 우량주 한정 → 재무 데이터 없는 저신호 종목 차단
    #   · 재무 데이터(fin_scores) 있는 종목 → 무조건 통과
    #   · 재무 데이터 없는 종목 → rank_overall 상위 60 이내일 때만 통과
    #     (신호가 매우 강한 종목은 데이터 부족이어도 일단 후보에 포함)
    _SIGNAL_ONLY_RANK_LIMIT = 60
    signal_tickers_mc = [
        s for s in signal_tickers
        if s["ticker"] in fin_scores
        or s.get("rank_overall", 9999) <= _SIGNAL_ONLY_RANK_LIMIT
    ]
    # 필터 후 후보가 너무 적으면 원본 사용 (안전망)
    if len(signal_tickers_mc) < 20:
        signal_tickers_mc = signal_tickers
    _cache_logger.info(
        "[MC 사전필터] 전체 %d → 필터 후 %d개 (재무데이터 보유 또는 rank<=%d)",
        len(signal_tickers), len(signal_tickers_mc), _SIGNAL_ONLY_RANK_LIMIT,
    )

    # ── 2단계: Monte Carlo 전체 채점 + 순위표 생성 (top_n=30) ──────────────
    # MC는 모든 후보 종목에 대해 시뮬레이션을 돌린 뒤 total_score로 정렬한다.
    # top_n은 단순히 순위표 앞부분 슬라이스이므로, 넉넉히 30개를 받아
    # CrewAI가 충분한 선택지를 갖고 최종 확정할 수 있도록 한다.
    mc_ranked: dict | None = None
    if signal_tickers_mc and _MODELS_AVAILABLE:
        try:
            mc_rec = await asyncio.to_thread(
                _recommend_stock_mc,
                user_id, conn, signal_tickers_mc, fin_scores, koscom_score,
                30,  # top_n=30: 계산비용 동일, CrewAI에 넓은 순위표 제공
            )
            mc_ranked = _safe_model_dump(mc_rec)
        except Exception:
            mc_ranked = None

    # ── 3단계: CrewAI 최종 확정 (30위 순위표 → 5개 선정 + 설명) ────────────
    # 퀀트(MC)는 순위표를 제시하고, CrewAI가 재무 검증 + 잡주 필터로 최종 확정
    result_dict: dict | None = None
    if _CREW_AVAILABLE and mc_ranked:
        try:
            def _safe_pct(v, cap: float = 300.0):
                """MC 수익률 → % 변환 + 클램핑 (LLM 주입 전 전처리)"""
                if v is None:
                    return None
                try:
                    f = float(v) * 100
                    return round(max(-99.0, min(cap, f)), 1)
                except (TypeError, ValueError):
                    return None

            candidates_json = json.dumps([
                {
                    "rank": it["rank"],
                    "ticker": it["ticker"],
                    "name": it["name"],
                    "market": it.get("market", ""),
                    "p_adj": it.get("p_adj"),
                    "rank_overall": it.get("rank_overall"),
                    "ai_fin_grade": it.get("ai_fin_grade", "정보없음"),
                    "mc_p10_pct": _safe_pct(it["features"].get("mc_p10")),
                    "mc_p50_pct": _safe_pct(it["features"].get("mc_p50")),
                    "mc_p90_pct": _safe_pct(it["features"].get("mc_p90")),
                    "vol_ann_pct": round((it["features"].get("vol_ann") or 0) * 100, 1),
                }
                for it in mc_ranked.get("items", [])
            ], ensure_ascii=False)

            llm = _make_analysis_llm()
            sel_raw = await asyncio.wait_for(
                asyncio.to_thread(
                    _run_mc_final_selection_agent,
                    llm=llm,
                    candidates_json=candidates_json,
                    user_risk_tier=inv_type,
                ),
                timeout=300.0,
            )

            # JSON 파싱 (마크다운 코드블록 제거 후)
            try:
                import re as _re
                _stripped = sel_raw.strip() if isinstance(sel_raw, str) else str(sel_raw)
                _m = _re.search(r"```(?:json)?\s*([\s\S]*?)```", _stripped)
                _json_str = _m.group(1).strip() if _m else _stripped
                sel_data = json.loads(_json_str)
                crew_items = sel_data.get("items", []) if isinstance(sel_data, dict) else []
            except Exception:
                crew_items = []

            # CrewAI 선정 결과와 MC 수치 데이터 병합
            if crew_items:
                mc_feature_map = {it["ticker"]: it for it in mc_ranked.get("items", [])}
                merged_items = []
                for crew_item in crew_items:
                    ticker = crew_item.get("ticker", "")
                    mc_data = mc_feature_map.get(ticker, {})
                    merged_items.append({
                        "rank": crew_item.get("rank", len(merged_items) + 1),
                        "ticker": ticker,
                        "name": crew_item.get("name") or mc_data.get("name", ""),
                        "market": mc_data.get("market", ""),
                        "p_adj": mc_data.get("p_adj"),
                        "rank_overall": mc_data.get("rank_overall"),
                        "ai_fin_grade": mc_data.get("ai_fin_grade"),
                        "total_score": mc_data.get("total_score"),
                        "features": mc_data.get("features", {}),
                        "reasons": crew_item.get("reasons") or mc_data.get("reasons", []),
                        "explanation": crew_item.get("explanation", ""),
                    })
                result_dict = {"items": merged_items}
                # rank 오름차순 정렬 후 1-5 재번호 부여
                # (CrewAI가 원본 30위 순위표의 rank를 그대로 가져오기 때문)
                merged_items.sort(key=lambda x: x.get("rank", 999))
                for new_rank, item in enumerate(merged_items, 1):
                    item["rank"] = new_rank
                result_dict = {"items": merged_items}
                _cache_logger.info(
                    "[CrewAI 최종확정] MC %d위 순위표 → CrewAI 확정 %d개",
                    len(mc_ranked.get("items", [])), len(merged_items),
                )
        except (asyncio.TimeoutError, Exception) as _crew_sel_err:
            _cache_logger.warning("[CrewAI 최종확정] 실패, MC top5 폴백: %s", _crew_sel_err)

    # CrewAI 확정 실패 → MC top5 직접 사용 (폴백)
    if result_dict is None and mc_ranked:
        top5 = mc_ranked.get("items", [])[:5]
        result_dict = {"items": top5}
        _cache_logger.info("[폴백] CrewAI 미실행/실패 → MC top5 직접 반환")

    # MC 모델 자체 실패 → DB 계량 폴백
    if result_dict is None:
        if not _MODELS_AVAILABLE:
            raise HTTPException(status_code=503, detail=f"모델 로드 실패: {_MODELS_IMPORT_ERR}")
        try:
            fb = await asyncio.to_thread(_get_stock_rec, user_id=user_id, conn=conn, koscom_score=koscom_score)
            result_dict = _safe_model_dump(fb)
        except Exception as e:
            # DB 계량 폴백도 실패 시 마지막 캐시 반환
            cached_fb = _load_stock_rec_cache(user_id)
            if cached_fb and cached_fb.get("data"):
                _cache_logger.warning("종목 추천 DB 폴백 실패 — 캐시 반환: %s", e)
                return cached_fb["data"]
            raise HTTPException(status_code=500, detail=f"종목 추천 오류: {e}")

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


def _compute_user_fit_score(pf: dict, inv_type: str, survey_ctx: dict) -> float:
    """포트폴리오가 이 사용자에게 얼마나 적합한지 점수를 계산합니다. (0~1, 높을수록 좋음)

    구성:
    - 기대수익률(MC 중앙값)    — 성향별 가중치
    - 하방위험(MC P10 기준)   — 성향별 가중치
    - 샤프 프록시(수익률/변동성) — 공통
    - 설문 기반 보너스(배당, 기여방식, 기간)
    """
    mc = pf.get("monte_carlo_1y") or {}
    mean_ret = float(mc.get("mean_pct") or 0)
    vol = float(mc.get("vol_ann_pct") or 1)
    p50 = float(mc.get("p50_pct") or 0)
    p10 = float(mc.get("p10_pct") or 0)

    # 수익률/변동성/하방 점수 정규화 (클램프 0~1)
    ret_score  = min(max((mean_ret + 10) / 50.0, 0.0), 1.0)   # -10~+40 → 0~1
    risk_score = min(max((p10 + 30)     / 50.0, 0.0), 1.0)    # -30~+20 → 0~1 (downside safety)
    sharpe_proxy = mean_ret / max(vol, 1.0)
    sharpe_score = min(max((sharpe_proxy + 0.5) / 3.5, 0.0), 1.0)

    # 성향별 가중치: (기대수익, 하방안전, 샤프)
    _W = {
        "공격투자형": (0.55, 0.15, 0.30),
        "적극투자형": (0.45, 0.20, 0.35),
        "위험중립형": (0.35, 0.30, 0.35),
        "안전추구형": (0.20, 0.50, 0.30),
        "안정추구형": (0.20, 0.50, 0.30),
        "안정형":     (0.10, 0.65, 0.25),
    }
    w_ret, w_risk, w_sharpe = _W.get(inv_type, (0.35, 0.30, 0.35))
    score = w_ret * ret_score + w_risk * risk_score + w_sharpe * sharpe_score

    # 설문 보너스
    div_pref = survey_ctx.get("DIVIDEND_PREF", "")
    horizon  = survey_ctx.get("TARGET_HORIZON", "")
    contrib  = survey_ctx.get("CONTRIBUTION_TYPE", "")
    sty      = pf.get("portfolio_style", "")

    if div_pref == "HIGH" and sty == "lowvol":
        score += 0.04
    if div_pref == "LOW" and sty == "momentum":
        score += 0.04
    if contrib == "DCA" and sty == "balanced":
        score += 0.03
    if any(y in (horizon or "") for y in ["1년", "2년"]) and sty == "momentum":
        score += 0.03
    if any(y in (horizon or "") for y in ["7년", "10년", "15년"]) and sty == "lowvol":
        score += 0.03

    return score


def _build_fit_label(pf: dict, inv_type: str, survey_ctx: dict) -> str:
    """포트폴리오의 실제 특성과 사용자 목표를 기반으로 라벨을 자동 생성합니다."""
    mc = pf.get("monte_carlo_1y") or {}
    mean_ret = float(mc.get("mean_pct") or 0)
    vol      = float(mc.get("vol_ann_pct") or 15)

    goal    = survey_ctx.get("INVEST_GOAL", "")
    horizon = survey_ctx.get("TARGET_HORIZON", "")
    div     = survey_ctx.get("DIVIDEND_PREF", "")

    # 목표 prefix
    _GOAL_PFX = [
        (["노후", "은퇴"],    "노후"),
        (["주택", "집 구입"], "내집마련"),
        (["증식", "목돈"],    "자산증식"),
        (["교육"],            "교육자금"),
        (["여유"],            "여유자금"),
    ]
    goal_prefix = next((pfx for keys, pfx in _GOAL_PFX if any(k in goal for k in keys)), "")

    # 포트폴리오 특성 분류
    if div == "HIGH" and vol < 15:
        char = "배당 안정"
    elif vol < 12:
        char = "저위험 안정"
    elif vol > 22 or mean_ret > 18:
        char = "고수익 성장"
    elif mean_ret > 12:
        char = "성장 중심"
    elif mean_ret < 5 and vol < 14:
        char = "원금 보전"
    else:
        char = "균형 성장"

    suffix = "포트폴리오"
    if goal_prefix:
        return f"{goal_prefix} {char} {suffix}"
    return f"{char} {suffix}"


_NAMING_PROMPT_TEMPLATE = """\
당신은 투자 입문자를 위한 '국내 주식 투자 네이밍 전문가'입니다.
아래 제공된 [추천 종목 리스트]와 [사용자 성향]을 분석하여, 이 포트폴리오의 특징을 한눈에 보여주는 이름을 5개 생성하세요.

### 지침(Instructions)
1. **테마 반영**: 종목들의 공통 산업군(예: 반도체, 2차전지, 저PBR 등)을 키워드로 활용하세요.
2. **성향 맞춤**: 사용자의 손실 허용 범위에 따라 어조를 조절하세요.
   - 공격형: "성장", "도약", "주도" 키워드 중심
   - 안정형: "방어", "수성", "기초", "배당" 키워드 중심
3. **입문자 친화**: 너무 어려운 금융 용어보다는 직관적이고 이해하기 쉬운 단어를 사용하세요.
4. **금지 사항**: "100% 수익", "원금 보장" 등 확정적인 수익을 약속하는 단어는 절대 사용하지 마세요.
5. **섹터 불일치 대응**: 만약 종목들의 섹터가 서로 판이하게 다르다면, '산업 명칭' 대신 '상태 키워드'를 조합하여 이름을 지으세요.

### 입력 데이터
- 추천 종목: {stock_list}
- 주요 산업군: {sector_info}
- 사용자 투자 성향: {user_profile}
- 투자 목적: {investment_goal}

### 출력 형식 (JSON만 반환, 설명 없이)
{{
  "portfolio_names": [
    {{"name": "이름1", "reason": "이 이름이 추천된 근거"}},
    {{"name": "이름2", "reason": "이 이름이 추천된 근거"}},
    {{"name": "이름3", "reason": "이 이름이 추천된 근거"}},
    {{"name": "이름4", "reason": "이 이름이 추천된 근거"}},
    {{"name": "이름5", "reason": "이 이름이 추천된 근거"}}
  ]
}}"""


async def _generate_portfolio_names_llm(
    portfolios: list, inv_type: str, survey_ctx: dict, llm
) -> list | None:
    """LLM으로 포트폴리오별 맞춤 이름을 생성합니다. 실패 시 None 반환."""
    results = []

    for pf in portfolios:
        items = pf.get("portfolio_items", [])

        stock_list = ", ".join(
            f"{it.get('name', it.get('ticker', ''))}({it.get('weight_pct', 0):.1f}%)"
            for it in items
        ) or "정보 없음"

        # asset_type 기반 산업군 추정 (sector 필드가 있으면 활용)
        sectors = list({
            it.get("sector") or it.get("asset_type", "STOCK")
            for it in items
            if it.get("sector") or it.get("asset_type")
        })
        sector_info = ", ".join(sectors) if sectors else "다양한 산업"

        goal = survey_ctx.get("INVEST_GOAL", "미입력")
        horizon = survey_ctx.get("TARGET_HORIZON", "")
        investment_goal = f"{goal}" + (f" / 목표 기간: {horizon}" if horizon else "")

        prompt = _NAMING_PROMPT_TEMPLATE.format(
            stock_list=stock_list,
            sector_info=sector_info,
            user_profile=inv_type,
            investment_goal=investment_goal,
        )

        def _call(p=prompt):
            return llm.call([{"role": "user", "content": p}])

        raw = await asyncio.to_thread(_call)
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("```")[1].lstrip("json").strip()

        parsed = json.loads(s)
        names = parsed.get("portfolio_names", [])
        # 후보 중 첫 번째 이름 사용
        chosen = names[0]["name"] if names else None
        results.append(chosen)

    if all(r is not None for r in results):
        return results
    return None


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
    available_amount: int = None,
    conn=Depends(_get_db_conn_dep),
):
    """포트폴리오 추천.

    실행 흐름:
      1. Monte Carlo (주 모델) — LightGBM 신호 + 재무등급 부스팅으로 3가지 포트폴리오 구성
      2. CrewAI 설명 에이전트 — 선정 종목들에 자연어 설명 추가
      3. 정량 지표 후처리 (_enrich_portfolio_quant_signals)

    - refresh=false(기본): 캐시 반환
    - refresh=true: 재실행 후 캐시 갱신
    - available_amount: 가용자산 직접 입력 시 survey_ctx의 LUMP_SUM_AMOUNT를 덮어씀
    """
    # ── 파일 캐시 (가용자산 직접 입력 시 캐시 우회) ────────────────────────
    if not refresh and available_amount is None:
        cached = _load_pf_cache(user_id)
        if cached:
            portfolios = cached.get("portfolios", [])
            if portfolios:
                for pf in portfolios:
                    pf["_cached_at"] = cached.get("saved_at")
                return portfolios

    # ── 사용자 투자성향 + 설문 컨텍스트 ────────────────────────────────────
    inv_type = "위험중립형"
    survey_ctx: dict = {}
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
        # 설문 응답 로드 (개인화 추천 이유에 활용)
        cur.execute("""
            SELECT sq.code,
                   sa.value_text, sa.value_number, sa.value_choice
            FROM survey_answers sa
            JOIN survey_questions sq ON sa.question_id = sq.id
            WHERE sa.user_id = %s
              AND sq.code IN (
                'INVEST_GOAL','TARGET_HORIZON','TARGET_AMOUNT',
                'CONTRIBUTION_TYPE','LUMP_SUM_AMOUNT','MONTHLY_AMOUNT',
                'MAX_HOLDINGS','DIVIDEND_PREF','ACCOUNT_TYPE'
              )
        """, (user_id,))
        for r in cur.fetchall():
            code = r["code"]
            val = (
                r.get("value_choice")
                or r.get("value_text")
                or (str(int(r["value_number"])) if r.get("value_number") else None)
            )
            if val:
                survey_ctx[code] = val
    except Exception:
        pass

    # 가용자산 직접 입력 시 survey_ctx 덮어쓰기
    if available_amount is not None and available_amount > 0:
        survey_ctx["LUMP_SUM_AMOUNT"] = str(available_amount)
        survey_ctx["CONTRIBUTION_TYPE"] = "LUMP_SUM"

    if not _MODELS_AVAILABLE:
        raise HTTPException(status_code=503, detail=f"모델 로드 실패: {_MODELS_IMPORT_ERR}")

    # ── 1단계: 신호+재무 데이터 직접 로드 ────────────────────────────────
    signal_tickers, fin_scores = _load_signal_fin_data(conn=conn)
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
            total_assets_override=available_amount if available_amount and available_amount > 0 else None,
        )
    except Exception as e:
        # MC 모델 오류 시 마지막 캐시 반환 (refresh=true여도 캐시 우선)
        _cache_logger.error("포트폴리오 MC 모델 오류 — 캐시 폴백 시도: %s", e)
        cached_fb = _load_pf_cache(user_id)
        if cached_fb:
            portfolios_fb = cached_fb.get("portfolios", [])
            if portfolios_fb:
                for pf in portfolios_fb:
                    pf["_cached_at"] = cached_fb.get("saved_at")
                return portfolios_fb
        raise HTTPException(status_code=500, detail=f"포트폴리오 MC 모델 오류: {e}")

    # ── PortfolioRecommendationResponse → 프런트엔드 dict 변환 ────────────
    # get_multi_portfolio_with_signals 은 항상 [balanced, momentum, lowvol] 순으로 반환
    _MULTI_STYLES_LIST = ["balanced", "momentum", "lowvol"]

    # 1차: 스타일 키 매핑
    _raw_portfolios: list[dict] = []
    for i, pf in enumerate(pf_results):
        pf_d = _safe_model_dump(pf)
        sty = _MULTI_STYLES_LIST[i] if i < len(_MULTI_STYLES_LIST) else "balanced"
        mc = pf_d.get("monte_carlo_1y") or {}
        mc_summary = ""
        if mc:
            mc_summary = (
                f"MC 1년 기대수익률: 하락 시나리오(P10) {mc.get('p10_pct', 0):+.1f}%, "
                f"중앙값(P50) {mc.get('p50_pct', 0):+.1f}%, "
                f"상승 시나리오(P90) {mc.get('p90_pct', 0):+.1f}%. "
                f"기대수익률 {mc.get('mean_pct', 0):+.1f}%, 연간변동성 {mc.get('vol_ann_pct', 0):.1f}%."
            )
        _raw_portfolios.append({
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
            "buy_plan": [
                {
                    "ticker": bp.get("ticker", ""),
                    "name": bp.get("name", ""),
                    "price_krw": bp.get("price_krw", 0),
                    "shares": bp.get("shares", 0),
                    "allocated_budget_krw": bp.get("allocated_budget_krw", 0),
                    "expected_return_1y_pct": bp.get("expected_return_1y_pct"),
                }
                for bp in pf_d.get("buy_plan", [])
            ],
            "investable_amount_krw": pf_d.get("investable_amount_krw"),
            "total_invested_krw": pf_d.get("total_invested_krw"),
            "leftover_krw": pf_d.get("leftover_krw"),
            "monte_carlo_1y": mc,
            "survey_context": survey_ctx,
        })

    # 2차: 사용자 적합도 점수로 정렬 → 라벨 부여 (Top1/2/3)
    for pf in _raw_portfolios:
        pf["_fit_score"] = _compute_user_fit_score(pf, inv_type, survey_ctx)
    _raw_portfolios.sort(key=lambda x: x["_fit_score"], reverse=True)

    portfolios: list[dict] = []
    for pf in _raw_portfolios:
        pf["portfolio_label"] = _build_fit_label(pf, inv_type, survey_ctx)
        del pf["_fit_score"]
        portfolios.append(pf)

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

    # ── 5단계: LLM 포트폴리오 이름 생성 ──────────────────────────────────
    if _CREW_AVAILABLE:
        try:
            llm_for_names = _make_analysis_llm()
            generated_names = await asyncio.wait_for(
                _generate_portfolio_names_llm(portfolios, inv_type, survey_ctx, llm_for_names),
                timeout=30.0,
            )
            if generated_names:
                for pf, name in zip(portfolios, generated_names):
                    pf["portfolio_label"] = name
        except Exception as _name_err:
            _cache_logger.warning("포트폴리오 LLM 이름 생성 실패 — 규칙 기반 유지: %s", _name_err)

    # 가용자산 직접 입력 시 캐시 저장 생략 (1회성 조회)
    if available_amount is None:
        _save_pf_cache(user_id, portfolios)

    # ── 6단계: DB에 히스토리 저장 (enriched portfolios 기준) ──────────────
    try:
        _save_portfolio_to_db(user_id, conn, portfolios)
    except Exception as e:
        import traceback
        _cache_logger.error("포트폴리오 DB 저장 실패 (user_id=%s): %s\n%s", user_id, e, traceback.format_exc())

    # ── 개별 종목 저장 (추천 빈도 집계용) ────────────────────────────────
    try:
        cur = conn.cursor()
        for pf in portfolios:
            for it in pf.get("portfolio_items", []):
                ticker = it.get("ticker")
                if not ticker:
                    continue
                cur.execute(
                    """
                    INSERT INTO portfolio_recommendations
                        (user_id, strategy_name, stock_code, state)
                    VALUES (%s, %s, %s, 'ACTIVE')
                    """,
                    (user_id, "stock_pick", ticker),
                )
        conn.commit()
    except Exception as _db_err:
        _cache_logger.warning("개별 종목 DB 저장 실패 (user_id=%s): %s", user_id, _db_err)

    return portfolios


@router.get("/portfolio-history")
async def get_portfolio_history(
    user_id: int,
    strategy_name: str = None,
    state: str = None,
    limit: int = 50,
    conn=Depends(_get_db_conn_dep),
):
    """
    포트폴리오 추천 히스토리를 조회합니다.
    
    Args:
        user_id: 사용자 ID
        strategy_name: 특정 전략명으로 필터링 (선택사항: balanced, momentum, lowvol)
        state: 상태로 필터링 (ACTIVE, ARCHIVED 등, 선택사항)
        limit: 최대 결과 개수 (기본값: 50)
        
    Returns:
        포트폴리오 추천 히스토리 리스트 (최신순)
    """
    cur = conn.cursor()
    
    portfolio_strategy_names = ("pf_optimal", "pf_growth", "pf_stable")

    # 동적 쿼리 생성
    query = """
        SELECT id, user_id, strategy_name, strategy_content, state, 
               created_at, updated_at
        FROM portfolio_recommendations
        WHERE user_id = %s
          AND strategy_content IS NOT NULL
    """
    params = [user_id]
    
    if strategy_name:
        query += " AND strategy_name = %s"
        params.append(strategy_name)
    else:
        placeholders = ",".join(["%s"] * len(portfolio_strategy_names))
        query += f" AND strategy_name IN ({placeholders})"
        params.extend(portfolio_strategy_names)
    
    if state:
        query += " AND state = %s"
        params.append(state)
    
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    
    cur.execute(query, params)
    rows = cur.fetchall()
    
    result = []
    for row in rows:
        content = row['strategy_content']
        if isinstance(content, str):
            content = json.loads(content)
        
        history_item = {
            "id": row['id'],
            "user_id": row['user_id'],
            "strategy_name": row['strategy_name'],
            "state": row['state'],
            "created_at": row['created_at'].isoformat() if hasattr(row['created_at'], 'isoformat') else str(row['created_at']),
            "updated_at": row['updated_at'].isoformat() if hasattr(row['updated_at'], 'isoformat') else str(row['updated_at']),
            "recommendation": content,
        }
        result.append(history_item)
    
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CrewAI 매니저 에이전트 기반 포트폴리오 종목 AI 분석 강화
# ─────────────────────────────────────────────────────────────────────────────

class PortfolioAiEnrichRequest(BaseModel):
    tickers: List[str]
    mode: str = "fin"   # "fin" (재무분석) | "signal" (방향성) | "news" (뉴스 기반 선정 근거)
    items: List[dict] = []  # [{"ticker": str, "name": str}, ...] — mode='news'에서 활용


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

    mode = req.mode if req.mode in ("fin", "signal", "news") else "fin"
    tickers = list(dict.fromkeys(req.tickers))[:12]  # 중복 제거, 최대 12개

    # ── news 모드: 뉴스 RAG + CrewAI 배치 처리 ───────────────────────────────
    if mode == "news":
        ticker_to_name = {it.get("ticker", ""): it.get("name", it.get("ticker", ""))
                         for it in (req.items or [])}
        for t in tickers:
            if t not in ticker_to_name:
                ticker_to_name[t] = t

        # 1) 뉴스 컨텍스트 병렬 수집
        news_contexts: dict = {}
        try:
            from news_model.pipeline_news_analysis_mvp import search_news_context

            def _fetch_news_for_ticker(ticker: str) -> tuple:
                name = ticker_to_name.get(ticker, ticker)
                query = f"{name} 사업 실적 전망 호재 뉴스"
                try:
                    results = search_news_context(query, n_results=5)
                    snippets = [r.get("doc", "")[:300] for r in results if r.get("doc")]
                except Exception:
                    snippets = []
                return ticker, "\n".join(snippets) if snippets else "관련 뉴스 없음"

            with ThreadPoolExecutor(max_workers=4) as pool:
                for ticker, ctx in pool.map(_fetch_news_for_ticker, tickers):
                    news_contexts[ticker] = ctx
        except Exception as e:
            _cache_logger.warning("뉴스 컨텍스트 수집 실패: %s", e)
            for t in tickers:
                news_contexts[t] = "뉴스 데이터를 불러올 수 없습니다."

        # 2) LLM 프롬프트용 뉴스 블록 구성
        news_block = ""
        for t in tickers:
            name = ticker_to_name.get(t, t)
            ctx = news_contexts.get(t, "관련 뉴스 없음")
            news_block += f"\n## {name} ({t})\n{ctx}\n"

        ticker_names_str = ", ".join(
            f"{ticker_to_name.get(t, t)}({t})" for t in tickers
        )

        # 3) CrewAI 에이전트로 종목별 선정 근거 생성
        narratives_map: dict = {}
        try:
            from crewai import Agent, Task, Crew

            llm = _make_analysis_llm()
            news_analyst = Agent(
                role="주식 뉴스 분석 전문가",
                goal=(
                    "포트폴리오에 편입된 각 종목이 왜 선정됐는지를 "
                    "최신 뉴스 근거 기반으로 투자 입문자가 이해할 수 있도록 자연어로 설명한다."
                ),
                backstory=(
                    "증권사 리서치 전문가로, 각 기업의 사업부별 뉴스와 시장 동향을 분석하여 "
                    "어떤 사업부·제품이 어떤 이유로 성장하고 있는지, 어떤 촉매제가 주가 상승을 이끄는지를 "
                    "쉬운 말로 일반 투자자에게 설명하는 데 특화되어 있다."
                ),
                llm=llm,
                verbose=False,
                allow_delegation=False,
            )

            task_desc = (
                f"다음 포트폴리오 편입 종목들에 대해 '왜 이 종목이 선정됐는가'를 뉴스 근거 기반으로 설명하라.\n\n"
                f"종목 목록: {ticker_names_str}\n\n"
                f"[종목별 뉴스 컨텍스트]\n{news_block}\n\n"
                "작성 지침:\n"
                "1. 각 종목별로 뉴스에서 확인되는 주요 호재(어떤 사업부·제품·이벤트)를 구체적으로 언급하라.\n"
                "2. 투자 입문자도 이해할 수 있도록 전문용어 없이 2-3문장으로 설명하라.\n"
                "3. 뉴스가 없는 경우 종목의 일반적 특징과 편입 의미를 설명하라.\n"
                "4. 모든 설명은 반드시 한국어로 작성하라.\n\n"
                "반드시 아래 JSON 형식으로만 응답하라. 추가 설명 없이 JSON만 출력하라:\n"
                "{\n"
                '  "narratives": [\n'
                '    {"ticker": "종목코드", "company_overview": "기업명 + 주요 사업(제품·서비스) + 시장 내 위치를 사실 기반으로 1문장. 예: \'삼성전자는 반도체·스마트폰·가전을 제조하는 글로벌 전자기업으로, 메모리 반도체 세계 1위 기업입니다.\' — 성장 가능성·투자 의견 등 전망 문구 금지", "narrative": "왜 이 종목이 선정됐는지 뉴스 근거 기반 2-3문장"},\n'
                "    ...\n"
                "  ]\n"
                "}"
            )

            task = Task(
                description=task_desc,
                expected_output=(
                    "각 편입 종목에 대해 뉴스 기반 선정 근거가 담긴 JSON 문자열. "
                    "narratives(list) 필드를 포함해야 한다."
                ),
                agent=news_analyst,
            )

            crew = Crew(agents=[news_analyst], tasks=[task], verbose=False)
            raw = crew.kickoff()
            raw_str = str(raw) if not isinstance(raw, str) else raw

            try:
                import re as _re
                m = _re.search(r'\{[\s\S]+\}', raw_str)
                parsed_crew = json.loads(m.group()) if m else {}
            except (json.JSONDecodeError, AttributeError):
                parsed_crew = {}

            narratives_map = {
                n.get("ticker"): {
                    "narrative": n.get("narrative", ""),
                    "company_overview": n.get("company_overview", ""),
                }
                for n in parsed_crew.get("narratives", [])
            }
        except Exception as crew_err:
            _cache_logger.error("뉴스 CrewAI 분석 실패: %s", crew_err)

        news_results: dict = {}
        for t in tickers:
            name = ticker_to_name.get(t, t)
            ctx_snippet = news_contexts.get(t, "")
            crew_entry = narratives_map.get(t)
            if crew_entry:
                narrative = crew_entry.get("narrative", "")
                company_overview = crew_entry.get("company_overview", "")
            elif ctx_snippet and ctx_snippet not in ("관련 뉴스 없음", "뉴스 데이터를 불러올 수 없습니다."):
                # CrewAI 실패 시 뉴스 첫 문장만 fallback으로 사용
                first_line = ctx_snippet.strip().split("\n")[0][:200]
                narrative = f"{name}: {first_line}"
                company_overview = ""
            else:
                narrative = f"{name}에 대한 뉴스 데이터가 충분하지 않습니다. 재무 실적 및 시장 모멘텀을 바탕으로 선정되었습니다."
                company_overview = ""
            news_results[t] = {
                "narrative": narrative,
                "company_overview": company_overview,
                "selection_reason": narrative,
            }
        return news_results

    # ── fin / signal 모드: 종목별 병렬 처리 ────────────────────────────────────
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
    ticker: str = Field(..., description="종목코드 (6자리, 예: 005930)")
    name: str = Field(..., description="종목명 (예: 삼성전자)")


class PortfolioRiskRequest(BaseModel):
    items: List[PortfolioRiskItem] = Field(
        ...,
        description="포트폴리오 편입 종목 목록 (최대 10개)",
    )
    risk_tier: str = Field(
        default="",
        description="투자 성향 등급 (예: 안정형, 중립형, 공격형)",
    )


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
        '    {\n'
        '      "ticker": "종목코드",\n'
        '      "name": "종목명",\n'
        '      "company_overview": "이 기업이 실제로 무엇을 만들거나 파는지 1문장. 반드시 \'[기업명]은(는) [주요제품/서비스]를 [생산/운영/판매]하는 [업종] 기업입니다\' 형식으로 작성. 성장성·투자의견·전망 표현 금지. 예시: \'삼성전자는 반도체·스마트폰·TV·가전을 제조하는 글로벌 전자기업으로, D램 메모리 반도체 세계 1위입니다.\'",\n'
        '      "narrative": "뉴스 근거 기반으로 이 종목이 포트폴리오에 선정된 이유 2문장",\n'
        '      "risk_text": "해당 종목의 주요 리스크 1-2문장"\n'
        '    },\n'
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
