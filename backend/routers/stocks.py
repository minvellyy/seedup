"""FastAPI 라우터 — 개별 주식 추천 엔드포인트.

main.py에서 include_router() 로 등록:

    from routers.stocks import router as stocks_router
    app.include_router(stocks_router, prefix="/api/v1")
"""
from __future__ import annotations

import sys
import os

# ── backend/ 디렉터리를 sys.path에 추가 ──────────────────────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# DB_PKG_PATH 환경변수가 있으면 추가로 경로 등록 (core 패키지 위치 지정 시 사용)
_PKG_PATH = os.environ.get("DB_PKG_PATH")
if _PKG_PATH and _PKG_PATH not in sys.path:
    sys.path.insert(0, os.path.abspath(_PKG_PATH))

import json as _json
import logging as _logging
import time
import pymysql
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from pathlib import Path as _Path
load_dotenv(dotenv_path=_Path(__file__).parent.parent / '.env')

from schemas import (  # noqa: E402
    UserSurveyRequest,
    StockRecommendationResponse,
)
from stock_model import get_stock_recommendations  # noqa: E402

router = APIRouter(prefix="/stocks", tags=["stocks"])

_CACHE_DIR = _Path(__file__).resolve().parent.parent / "portfolio_cache"
_logger = _logging.getLogger(__name__)

# 종목코드 -> 종목명 매핑 (주요 종목)
STOCK_NAME_MAP = {
    '005930': '삼성전자',
    '373220': 'LG에너지솔루션',
    '000660': 'SK하이닉스',
    '207940': '삼성바이오로직스',
    '005935': '삼성전자우',
    '051910': 'LG화학',
    '006400': '삼성SDI',
    '005380': '현대차',
    '336260': '두산퓨얼셀',
    '000270': '기아',
    '068270': '셀트리온',
    '035420': 'NAVER',
    '105560': 'KB금융',
    '055550': '신한지주',
    '035720': '카카오',
    '012330': '현대모비스',
    '028260': '삼성물산',
    '066570': 'LG전자',
    '003670': '포스코퓨처엠',
    '096770': 'SK이노베이션',
    '017670': 'SK텔레콤',
    '009150': '삼성전기',
    '032830': '삼성생명',
    '018260': '삼성에스디에스',
    '033780': 'KT&G',
    '003550': 'LG',
    '015760': '한국전력',
    '010130': '고려아연',
    '047050': '포스코인터내셔널',
    '086790': '하나금융지주',
    '034730': 'SK',
    '030200': 'KT',
    '323410': '카카오뱅크',
    '251270': '넷마블',
    '036570': '엔씨소프트',
    '259960': '크래프톤',
    '047810': '한국항공우주',
    '402340': 'SK스퀘어',
    '042700': '한미반도체',
    '011200': 'HMM',
    '352820': '하이브',
    '003490': '대한항공',
    '009540': 'HD한국조선해양',
    '010950': 'S-Oil',
    '000810': '삼성화재',
    '086280': '현대글로비스',
    '138040': '메리츠금융지주',
    '316140': '우리금융지주',
    '024110': '기업은행',
    '161390': '한국타이어앤테크놀로지',
    '011070': 'LG이노텍',
    '329180': '현대에너지솔루션',
    '010140': '삼성중공업',
    '267250': 'HD현대',
    '377300': '카카오페이',
    '004020': '현대제철',
    '034020': '두산에너빌리티',
    '271560': '오리온',
    '241560': '두산밥캣',
    '003540': '대신증권',
    '004170': '신세계',
    '012450': '한화에어로스페이스',
    '361610': 'SK아이이테크놀로지',
    '139480': '이마트',
    '018880': '한온시스템',
    '081660': '휠라홀딩스',
    '128940': '한미약품',
    '097950': 'CJ제일제당',
    '000720': '현대건설',
    '078930': 'GS',
    '004990': '롯데칠성',
    '006260': 'LS',
    '004370': '농심',
    '006800': '미래에셋증권',
    '071050': '한국금융지주',
    '000100': '유한양행',
    '005940': 'NH투자증권',
    '043260': '성호전자',
    '348210': '넥스틴',
    '263750': '펄어비스',
    '293490': '카카오게임즈',
    '282330': 'BGF리테일',
    '001230': '동국제강',
    '005490': 'POSCO홀딩스',
    '009830': '한화솔루션',
    '002380': 'KCC',
    '088350': '한화생명',
    '064350': '현대로템',
    '009970': '영원무역홀딩스',
    '003620': 'KG모빌리티',
    '004000': '롯데정밀화학',
    '298020': '효성티앤씨',
    '298050': '효성첨단소재',
    '298040': '효성중공업',
    '051900': 'LG생활건강',
    '180640': '한진칼',
    '000120': 'CJ대한통운',
    '108670': 'LX세미콘',
    '145020': '휴젤',
    '187660': '현대퓨처넷',
    '122870': '와이지엔터테인먼트',
    '036460': '한국가스공사',
    '001450': '현대해상',
    '069620': '대웅제약',
    '095720': '웅진씽크빅',
    '090430': '아모레퍼시픽',
    '002790': '아모레G',
}


# ── DB 종목 캐시 (1시간) ─────────────────────────────────────────────────────
_db_stock_cache: dict = {}    # {stock_code: {name, market, last_price}}
_db_stock_cache_ts: float = 0.0
_DB_CACHE_TTL = 3600


def _load_db_stocks() -> dict:
    """DB instruments 테이블에서 종목명+last_price 전체 조회 — 1시간 캐시."""
    global _db_stock_cache, _db_stock_cache_ts
    if _db_stock_cache and (time.time() - _db_stock_cache_ts) < _DB_CACHE_TTL:
        return _db_stock_cache
    try:
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            db=os.getenv("DB_NAME"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT stock_code, name, exchange, last_price "
                    "FROM instruments "
                    "WHERE asset_type='STOCK' AND price_status='ACTIVE'"
                )
                rows = cur.fetchall()
            _db_stock_cache = {
                r["stock_code"]: {
                    "name": r["name"],
                    "market": r["exchange"] or "KOSPI",
                    "last_price": float(r["last_price"] or 0),
                }
                for r in rows
            }
            _db_stock_cache_ts = time.time()
        finally:
            conn.close()
    except Exception as e:
        _logger.warning("DB 종목 일괄 조회 실패: %s", e)
    return _db_stock_cache


def _save_stock_rec_json(user_id: int, result: StockRecommendationResponse) -> None:
    """종목 추천 결과를 portfolio_cache/user_{id}_stock_rec.json 에 저장합니다."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"user_{user_id}_stock_rec.json"
        path.write_text(
            _json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        _logger.warning("종목 추천 JSON 저장 실패 (user_id=%s): %s", user_id, exc)


def _get_db_conn():
    """FastAPI Dependency: pymysql DB 연결을 생성하고 요청이 끝나면 자동으로 닫습니다."""
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


@router.post(
    "/recommend",
    response_model=StockRecommendationResponse,
    summary="개별 주식 Top5 추천",
    description=(
        "user_id와 코스콤 투자성향 점수를 기반으로 DB 설문 답변을 로드하고 "
        "개별 주식 Top5 추천 결과를 반환합니다."
    ),
)
def recommend_stocks(
    req: UserSurveyRequest,
    conn=Depends(_get_db_conn),
) -> StockRecommendationResponse:
    try:
        result = get_stock_recommendations(
            user_id=req.user_id,
            conn=conn,
            koscom_score=req.koscom_score,
            monthly_override=req.monthly_override,
            explain_detail=req.explain_detail,
            explain_lang=req.explain_lang,
            explain_style=req.explain_style,
        )
        _save_stock_rec_json(req.user_id, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 모델 오류: {e}")


@router.get(
    "/recommend/{user_id}",
    response_model=StockRecommendationResponse,
    summary="개별 주식 Top5 추천 (GET)",
    description="user_id를 경로 매개변수로 전달하는 GET 버전입니다. koscom_score는 기본값(20)을 사용합니다.",
)
def recommend_stocks_get(
    user_id: int,
    koscom_score: int = 20,
    conn=Depends(_get_db_conn),
) -> StockRecommendationResponse:
    try:
        result = get_stock_recommendations(
            user_id=user_id,
            conn=conn,
            koscom_score=koscom_score,
        )
        _save_stock_rec_json(user_id, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 모델 오류: {e}")


@router.get(
    "/top",
    summary="거래대금 Top 100 조회",
    description="기간별 거래대금 상위 종목 리스트를 반환합니다.",
)
def get_top_stocks(
    period: str = "realtime",
    limit: int = 100,
    conn=Depends(_get_db_conn),
):
    """
    거래대금 Top 100 종목 조회
    
    Args:
        period: 조회 기간 (realtime, 1d, 1w, 1m, 3m, 6m)
        limit: 반환할 종목 수 (기본 100)
    """
    try:
        from kis_ws_client import get_price_store
        price_store = get_price_store()

        # ── DB 종목 사전 로드 (name + last_price) ─────────────────────────────
        db_stocks = _load_db_stocks()

        def _get_name(code: str) -> str:
            return STOCK_NAME_MAP.get(code) or (db_stocks.get(code) or {}).get("name") or code

        # ── price_store 데이터 → 실시간 딕셔너리 ─────────────────────────────
        live: dict = {}
        for code, data in (price_store or {}).items():
            if not data:
                continue
            cp = data.get("current_price", 0) or 0
            vol = data.get("volume", 0) or 0
            live[code] = {
                "stock_code": code,
                "stock_name": _get_name(code),
                "market": data.get("market", "KOSPI"),
                "current_price": cp,
                "change": data.get("change", 0),
                "change_rate": data.get("change_rate", 0),
                "volume": vol,
                "trade_value": cp * vol,
            }

        # ── price_store가 limit보다 부족하면 DB last_price로 보완 ─────────────
        if len(live) < limit:
            _logger.info("price_store 종목 수(%d) < %d → DB last_price로 보완", len(live), limit)
            for code, info in db_stocks.items():
                if code in live:
                    continue  # 실시간 데이터 우선
                lp = info["last_price"]
                if lp <= 0:
                    continue
                live[code] = {
                    "stock_code": code,
                    "stock_name": info["name"],
                    "market": info["market"],
                    "current_price": lp,
                    "change": 0,
                    "change_rate": 0,
                    "volume": 0,
                    "trade_value": 0,   # 거래량 정보 없음 — 정렬 시 실시간 종목 하위
                }

        if not live:
            _logger.warning("price_store + DB 모두 비어있음")
            return []

        # 정렬: 실시간 trade_value 내림차순 → DB 종목은 last_price 내림차순
        stocks = sorted(
            live.values(),
            key=lambda x: (x["trade_value"], x["current_price"]),
            reverse=True,
        )
        return stocks[:limit]

    except Exception as e:
        _logger.error("거래대금 Top 조회 오류: %s", e)
        raise HTTPException(status_code=500, detail=f"거래대금 Top 조회 오류: {e}")


@router.get(
    "/search",
    summary="종목 검색",
    description="종목명 또는 종목코드로 검색합니다.",
)
def search_stocks(
    q: str,
    limit: int = 20,
    conn=Depends(_get_db_conn),
):
    """
    종목 검색
    
    Args:
        q: 검색어 (종목명 또는 종목코드)
        limit: 반환할 종목 수 (기본 20)
    """
    try:
        if not q or len(q.strip()) == 0:
            return []
        
        query = q.strip()
        
        # DB의 instruments 테이블에서 검색
        with conn.cursor() as cur:
            # 종목명 또는 종목코드로 검색 (LIKE 사용)
            cur.execute(
                """
                SELECT stock_code, name, exchange as market, sector, asset_type
                FROM instruments
                WHERE (name LIKE %s OR stock_code LIKE %s)
                  AND asset_type IN ('STOCK', 'ETF')
                  AND price_status = 'ACTIVE'
                ORDER BY
                    CASE
                        WHEN stock_code = %s THEN 0
                        WHEN stock_code LIKE %s THEN 1
                        WHEN name LIKE %s THEN 2
                        ELSE 3
                    END,
                    asset_type,
                    name
                LIMIT %s
                """,
                (f'%{query}%', f'%{query}%', query, f'{query}%', f'{query}%', limit)
            )
            rows = cur.fetchall()
        
        # KIS WebSocket에서 실시간 가격 가져오기 (있으면)
        from kis_ws_client import get_price_store
        price_store = get_price_store()
        
        results = []
        for row in rows:
            code = row['stock_code']
            price_data = price_store.get(code, {})
            
            results.append({
                "stock_code": code,
                "stock_name": row['name'],
                "market": row['market'] or 'KOSPI',
                "asset_type": row['asset_type'],
                "current_price": price_data.get("current_price", 0),
                "change_rate": price_data.get("change_rate", 0),
            })
        
        return results
        
    except Exception as e:
        _logger.error(f"종목 검색 오류: {e}")
        raise HTTPException(status_code=500, detail=f"종목 검색 오류: {e}")


@router.get(
    "/intraday/{stock_code}",
    summary="일중 차트 데이터",
    description="FinanceDataReader를 사용하여 최근 일중 데이터를 가져옵니다.",
)
def get_intraday_data(
    stock_code: str,
    days: int = 5,
):
    """
    일중 차트 데이터 조회 (FinanceDataReader 사용)
    
    Args:
        stock_code: 종목코드
        days: 조회할 일수 (기본 5일)
    """
    try:
        import FinanceDataReader as fdr
        
        # 최근 N일간의 데이터 가져오기
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # FinanceDataReader로 일봉 데이터 가져오기
        df = fdr.DataReader(stock_code, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        
        if df is None or df.empty:
            _logger.warning(f"종목 {stock_code}의 데이터를 가져올 수 없습니다.")
            return {
                "stock_code": stock_code,
                "data": [],
                "error": "데이터를 가져올 수 없습니다."
            }
        
        # DataFrame을 리스트로 변환
        result_data = []
        for idx, row in df.iterrows():
            result_data.append({
                "date": idx.strftime('%Y-%m-%d'),
                "time": idx.strftime('%H:%M:%S') if hasattr(idx, 'hour') else "00:00:00",
                "open": float(row.get('Open', 0)) if 'Open' in row else None,
                "high": float(row.get('High', 0)) if 'High' in row else None,
                "low": float(row.get('Low', 0)) if 'Low' in row else None,
                "close": float(row.get('Close', 0)),
                "volume": int(row.get('Volume', 0)) if 'Volume' in row else None,
            })
        
        return {
            "stock_code": stock_code,
            "period": f"{days}days",
            "data": result_data,
            "count": len(result_data)
        }
        
    except ImportError:
        _logger.error("FinanceDataReader가 설치되지 않았습니다.")
        raise HTTPException(status_code=500, detail="FinanceDataReader가 설치되지 않았습니다. pip install finance-datareader")
    except Exception as e:
        _logger.error(f"일중 데이터 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=f"일중 데이터 조회 오류: {e}")


@router.get(
    "/investor-flow",
    summary="시장별 투자자 매매동향",
    description="한국투자증권 API로 KOSPI·KOSDAQ 투자자별 순매수 현황 반환. 단위: 십억원.",
)
def get_investor_flow():
    """KOSPI / KOSDAQ 투자자별 순매수 현황.

    Returns:
        {
          "kospi":  {institution_net, foreign_net, individual_net, ...},
          "kosdaq": {institution_net, foreign_net, individual_net, ...},
          "combined": {institution_net, foreign_net, individual_net}
        }
    """
    try:
        from kis_client import get_investor_trading_best
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"KIS 클라이언트 임포트 실패: {e}")

    results: dict = {}
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            results[market.lower()] = get_investor_trading_best(market)
        except Exception as exc:
            _logger.warning(f"투자자 데이터 조회 실패 [{market}]: {exc}")
            results[market.lower()] = {
                "market": market,
                "error": str(exc),
                "institution_net": None,
                "foreign_net":     None,
                "individual_net":  None,
            }

    # KOSPI + KOSDAQ 합계 (시장 전체 체온계)
    def _safe_add(a, b):
        if a is None and b is None:
            return None
        return round((a or 0.0) + (b or 0.0), 1)

    kp = results.get("kospi",  {})
    kq = results.get("kosdaq", {})
    results["combined"] = {
        "institution_net": _safe_add(kp.get("institution_net"), kq.get("institution_net")),
        "foreign_net":     _safe_add(kp.get("foreign_net"),     kq.get("foreign_net")),
        "individual_net":  _safe_add(kp.get("individual_net"),  kq.get("individual_net")),
    }

    return results


