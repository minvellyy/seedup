"""한국투자증권 오픈 API 클라이언트.

사용 예:
    from kis_client import get_current_price, get_daily_prices_1y

    price_info = get_current_price("005930")   # 삼성전자 현재가
    history    = get_daily_prices_1y("005930") # 1년 일별 데이터
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

# .env 로드 (backend/ 기준)
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# KIS API 서버 URL 설정 (모의투자 / 실거래 구분)
IS_MOCK = os.getenv("KIS_MOCK", "false").lower() == "true"
if IS_MOCK:
    BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자
    print("[KIS] 모의투자 모드로 설정됨")
else:
    BASE_URL = "https://openapi.koreainvestment.com:9443"      # 실거래
    print("[KIS] 실거래 모드로 설정됨")

# 토큰 캐시 파일 경로 (project root 는 backend/ )
_TOKEN_FILE = Path(__file__).parent / ".kis_token_cache"

# ── 토큰 캐시 (메모리 + 파일 이중 저장) ──────────────────────────────────────
import threading as _threading
_token_cache: Dict = {"token": None, "expires_at": 0.0}
_token_lock = _threading.Lock()  # 다중 스레드 동시 갱신 방지

# ── KIS API Rate Limiter (초당 최대 15건, 安全마진 포함) ─────────────────────
_rate_lock = _threading.Lock()
_last_call_time: float = 0.0
_MIN_INTERVAL = 0.1   # 약 10 req/sec (안전 마진 포함)

def _rate_limit() -> None:
    """KIS API 호출 전 속도 제한 적용. 초당 ~14건 이하로 유지."""
    global _last_call_time
    with _rate_lock:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _last_call_time)
        if wait > 0:
            time.sleep(wait)
        _last_call_time = time.time()


def _load_token_from_file() -> bool:
    """파일에서 캐시된 토큰 로드. 유효하면 True."""
    try:
        if not _TOKEN_FILE.exists():
            return False
        data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        expires_at = float(data.get("expires_at", 0))
        if expires_at > time.time() + 60:
            _token_cache["token"]      = data["token"]
            _token_cache["expires_at"] = expires_at
            return True
    except Exception:
        pass
    return False


def _save_token_to_file(token: str, expires_at: float) -> None:
    try:
        _TOKEN_FILE.write_text(
            json.dumps({"token": token, "expires_at": expires_at}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _get_token(force_refresh: bool = False) -> str:
    """access_token 발급 (1일 1회 제한 → 파일 캐시 우선 사용)."""
    now = time.time()
    if not force_refresh:
        # 메모리 캐시 확인 (lock 없이 빠른 읽기)
        if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
            return _token_cache["token"]
        # 파일 캐시 확인
        if _load_token_from_file():
            return _token_cache["token"]

    with _token_lock:
        # lock 획득 후 재확인 — 다른 스레드가 갱신했을 수 있음
        now = time.time()
        if not force_refresh and _token_cache["token"] and _token_cache["expires_at"] > now + 60:
            return _token_cache["token"]

        # 강제갱신이거나 캐시 없음 — 신규 발급
        if force_refresh:
            _token_cache["token"] = None
            _token_cache["expires_at"] = 0.0
            if _TOKEN_FILE.exists():
                try:
                    _TOKEN_FILE.unlink()
                except Exception:
                    pass

        resp = requests.post(
            f"{BASE_URL}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey":     os.getenv("APP_KEY", "").strip(),
                "appsecret":  os.getenv("APP_SECRET", "").strip(),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        token      = data["access_token"]
        expires_at = now + int(data.get("expires_in", 86400))
        _token_cache["token"]      = token
        _token_cache["expires_at"] = expires_at
        _save_token_to_file(token, expires_at)
        return token


def _kis_get(url: str, tr_id: str, params: Dict, retry: bool = True):
    """KIS GET 요청 헬퍼.

    - EGW00201 (초당 거래건수 초과): 1초 대기 후 최대 3회 재시도
    - 토큰 만료(500 + 토큰 오류 메시지): 토큰 갱신 후 1회 재시도
    """
    import logging as _logging
    _logger = _logging.getLogger("kis_client")

    _TOKEN_EXPIRED_KEYWORDS = ("접근토큰", "기간이 만료", "token", "expired", "invalid token", "인증")
    _RATE_LIMIT_CODE = "EGW00201"
    _RATE_LIMIT_WAIT = 1.0   # 초당 한도 초과 시 초기 대기 시간(초) — 지수 백오프 적용
    _RATE_LIMIT_MAX_RETRY = 5

    def _is_token_error(resp: requests.Response) -> bool:
        try:
            body = resp.json()
            msg = (body.get("msg1", "") + body.get("msg", "")).lower()
            rt_cd = str(body.get("rt_cd", ""))
            if rt_cd == "1" and any(k in msg for k in _TOKEN_EXPIRED_KEYWORDS):
                return True
        except Exception:
            pass
        try:
            text = resp.text.lower()
            return any(k in text for k in _TOKEN_EXPIRED_KEYWORDS)
        except Exception:
            return False

    def _is_rate_limit(resp: requests.Response) -> bool:
        try:
            body = resp.json()
            return body.get("message") == _RATE_LIMIT_CODE or _RATE_LIMIT_CODE in body.get("msg1", "")
        except Exception:
            return False

    try:
        r = requests.get(url, headers=_headers(tr_id), params=params, timeout=10)

        # ── Rate Limit 재시도 (지수 백오프 + 지터 적용) ─────────────────────
        if r.status_code == 500 and retry and _is_rate_limit(r):
            import random as _random
            for attempt in range(1, _RATE_LIMIT_MAX_RETRY + 1):
                wait = _RATE_LIMIT_WAIT * (2 ** (attempt - 1)) + _random.uniform(0, 0.5)
                _logger.debug("KIS 초당 한도 초과 — %.2f초 대기 후 재시도 %d/%d (%s)",
                              wait, attempt, _RATE_LIMIT_MAX_RETRY, url)
                time.sleep(wait)
                r = requests.get(url, headers=_headers(tr_id), params=params, timeout=10)
                if not (r.status_code == 500 and _is_rate_limit(r)):
                    break
            else:
                _logger.warning("KIS 초당 한도 초과 반복 — 최종 실패 (%s)", url)

        # ── 토큰 만료 재시도 ───────────────────────────────────────────────
        elif r.status_code == 500 and retry:
            if _is_token_error(r):
                _logger.warning("KIS 토큰 만료 감지 — 토큰 갱신 후 1회 재시도 (%s)", url)
                _get_token(force_refresh=True)
                r = requests.get(url, headers=_headers(tr_id), params=params, timeout=10)
                if r.status_code == 500:
                    _logger.error("KIS 500 재시도 후에도 실패 (%s)\n응답: %s", url, r.text[:300])
            else:
                _logger.warning(
                    "KIS 500 수신 (알 수 없는 오류) (%s)\n응답: %s",
                    url, r.text[:300],
                )

        r.raise_for_status()
        return r
    except Exception as e:
        _logger.debug("KIS API 요청 실패 [%s]: %s", url, e)
        raise


def _headers(tr_id: str) -> Dict[str, str]:
    return {
        "authorization": f"Bearer {_get_token()}",
        "appkey":        os.getenv("APP_KEY", "").strip(),
        "appsecret":     os.getenv("APP_SECRET", "").strip(),
        "tr_id":         tr_id,
        "content-type":  "application/json; charset=utf-8",
    }


# ── 현재가 조회 ─────────────────────────────────────────────────────────────
def get_current_price(stock_code: str) -> Dict:
    """국내 주식 현재가 조회.

    Returns:
        {
            "current_price": float,   # 현재가
            "prev_close":    float,   # 전일 종가
            "change":        float,   # 전일 대비 금액
            "change_rate":   float,   # 등락률 (%)
            "volume":        int,     # 누적 거래량
            "price_date":    str,     # 기준일 'YYYY-MM-DD'
        }
    """
    r = _kis_get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         stock_code,
        },
    )
    data = r.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"KIS API 오류 [{stock_code}]: {data.get('msg1', '')}")

    o = data["output"]
    raw_date = o.get("stck_bsop_date", "")  # 'YYYYMMDD' — 장중에는 비어있을 수 있음
    if len(raw_date) == 8:
        fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
    else:
        fmt_date = datetime.today().strftime("%Y-%m-%d")  # fallback: 오늘

    def _safe_float(v):
        try: return float(v) if v and v not in ("", "0", "0.00") else None
        except: return None

    return {
        "current_price": float(o.get("stck_prpr", 0) or 0),
        "prev_close":    float(o.get("stck_sdpr", 0) or 0),
        "change":        float(o.get("prdy_vrss", 0) or 0),
        "change_rate":   float(o.get("prdy_ctrt", 0) or 0),
        "volume":        int(o.get("acml_vol", 0) or 0),
        "price_date":    fmt_date,
        # 추가 지표
        "market_cap":    _safe_float(o.get("hts_avls")),   # 시가총액 (억원)
        "per":           _safe_float(o.get("per")),
        "pbr":           _safe_float(o.get("pbr")),
        "eps":           _safe_float(o.get("eps")),
        "week52_high":   _safe_float(o.get("w52_hgpr")),
        "week52_low":    _safe_float(o.get("w52_lwpr")),
    }


# ── 일별 OHLCV 조회 ─────────────────────────────────────────────────────────
def _get_daily_chunk(
    stock_code: str,
    start_yyyymmdd: str,
    end_yyyymmdd: str,
) -> List[Dict]:
    """특정 기간 일별 종가 조회 (최대 ~100 거래일)."""
    r = _kis_get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        "FHKST03010100",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         stock_code,
            "FID_INPUT_DATE_1":       start_yyyymmdd,
            "FID_INPUT_DATE_2":       end_yyyymmdd,
            "FID_PERIOD_DIV_CODE":    "D",
            "FID_ORG_ADJ_PRC":        "0",
        },
    )
    data = r.json()

    if data.get("rt_cd") != "0":
        return []

    result: List[Dict] = []
    for row in data.get("output2", []):
        d = row.get("stck_bsop_date", "")
        c = row.get("stck_clpr", "")
        if not d or not c:
            continue
        fmt_date = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d
        o = row.get("stck_oprc", "")
        h = row.get("stck_hgpr", "")
        l = row.get("stck_lwpr", "")
        result.append({
            "date":   fmt_date,
            "open":   float(o) if o else None,
            "high":   float(h) if h else None,
            "low":    float(l) if l else None,
            "close":  float(c),
            "volume": int(row.get("acml_vol", 0) or 0) or None,
        })
    return result


def get_daily_prices_1y(stock_code: str) -> List[Dict]:
    """최근 1년 일별 OHLCV 리스트 (오름차순).

    KIS API 1회 호출 최대 100건 한계 → 3회로 나눠 1년 커버.
    반환: [{"date": "YYYY-MM-DD", "open": float|None, "high": float|None, "low": float|None, "close": float, "volume": int|None}, ...]
    """
    today   = datetime.today()
    cutoff  = today - timedelta(days=365)
    all_records: Dict[str, Dict] = {}

    # 최신 → 과거 방향으로 ~130 캘린더일씩 3회 조회
    chunk_end = today
    for _ in range(4):
        chunk_start = chunk_end - timedelta(days=130)
        if chunk_start < cutoff:
            chunk_start = cutoff

        chunk = _get_daily_chunk(
            stock_code,
            chunk_start.strftime("%Y%m%d"),
            chunk_end.strftime("%Y%m%d"),
        )
        for row in chunk:
            all_records[row["date"]] = row  # 중복 키로 자동 dedup

        chunk_end = chunk_start - timedelta(days=1)
        if chunk_end < cutoff:
            break

    result = sorted(all_records.values(), key=lambda x: x["date"])
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    return [r for r in result if r["date"] >= cutoff_str]


# ── 시장 지수 조회 ──────────────────────────────────────────────────────────
# ISCD 코드: 0001=KOSPI, 1001=KOSDAQ
_INDEX_ISCD = {"KOSPI": "0001", "KOSDAQ": "1001"}


def get_index_price(market: str) -> Dict:
    """국내 주요 지수 현재가 조회.

    Args:
        market: "KOSPI" 또는 "KOSDAQ"

    Returns:
        {
            "market":      str,    # "KOSPI" | "KOSDAQ"
            "index":       float,  # 현재 지수
            "prev_close":  float,  # 전일 종가
            "change":      float,  # 전일 대비
            "change_rate": float,  # 등락률 (%)
            "open":        float,  # 시가
            "high":        float,  # 고가
            "low":         float,  # 저가
            "price_date":  str,    # 기준일 'YYYY-MM-DD' (장중이면 오늘)
        }
    """
    iscd = _INDEX_ISCD.get(market.upper())
    if not iscd:
        raise ValueError(f"지원하지 않는 시장: {market}")

    r = _kis_get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price",
        "FHPUP02100000",
        {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD":         iscd,
        },
    )
    data = r.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"KIS 지수 조회 오류 [{market}]: {data.get('msg1', '')}")

    o = data["output"]

    # 기준일: 응답에 날짜 필드가 없으면 오늘
    raw_date = o.get("bstp_nmix_prdy_vrss_sign", "")  # 사용 불가 → 오늘 날짜 사용
    price_date = datetime.today().strftime("%Y-%m-%d")

    return {
        "market":      market.upper(),
        "index":       float(o.get("bstp_nmix_prpr",    0) or 0),
        "prev_close":  float(o.get("prdy_nmix",          0) or 0),
        "change":      float(o.get("bstp_nmix_prdy_vrss", 0) or 0),
        "change_rate": float(o.get("bstp_nmix_prdy_ctrt", 0) or 0),
        "open":        float(o.get("bstp_nmix_opnprc",   0) or 0),
        "high":        float(o.get("bstp_nmix_hgprc",    0) or 0),
        "low":         float(o.get("bstp_nmix_lwprc",    0) or 0),
        "price_date":  price_date,
    }


def get_investor_trading(market: str = "KOSPI") -> Dict:
    """KIS API - 시장별 투자자매매동향(시세) [국내주식-074] FHPTJ04030000.

    당일 실시간 누적 매도/매수/순매수를 반환합니다. 단위: 십억원.

    Args:
        market: "KOSPI" (FID_INPUT_ISCD_2=S001) 또는 "KOSDAQ" (Q001)

    Returns dict 키:
        institution_sell / institution_buy / institution_net
        foreign_sell     / foreign_buy     / foreign_net
        individual_sell  / individual_buy  / individual_net
        date
    """
    is_kosdaq = market.upper() == "KOSDAQ"
    iscd_2 = "Q001" if is_kosdaq else "S001"

    r = _kis_get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor-time-by-market",
        "FHPTJ04030000",
        {
            "FID_INPUT_ISCD":   "999",
            "FID_INPUT_ISCD_2": iscd_2,
        },
    )
    data = r.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"KIS 투자자 조회 오류 [{market}]: {data.get('msg1', '')}")

    output = data.get("output", [])
    if not output:
        raise ValueError(f"KIS 투자자 데이터 없음 [{market}]")

    row = output[0]

    def _sbj(field: str) -> float:
        """백만원 → 십억원 변환 (÷1000), 소수 1자리."""
        try:
            return round(float(row.get(field, 0) or 0) / 1000, 1)
        except (ValueError, TypeError):
            return 0.0

    today_str = datetime.today().strftime("%Y-%m-%d")
    return {
        "date":             today_str,
        "market":           market.upper(),
        # 기관
        "institution_sell": _sbj("orgn_seln_tr_pbmn"),
        "institution_buy":  _sbj("orgn_shnu_tr_pbmn"),
        "institution_net":  _sbj("orgn_ntby_tr_pbmn"),
        # 외국인
        "foreign_sell":     _sbj("frgn_seln_tr_pbmn"),
        "foreign_buy":      _sbj("frgn_shnu_tr_pbmn"),
        "foreign_net":      _sbj("frgn_ntby_tr_pbmn"),
        # 개인
        "individual_sell":  _sbj("prsn_seln_tr_pbmn"),
        "individual_buy":   _sbj("prsn_shnu_tr_pbmn"),
        "individual_net":   _sbj("prsn_ntby_tr_pbmn"),
    }


def get_investor_trading_daily(market: str = "KOSPI") -> Dict:
    """KIS API - 시장별 투자자매매동향(일별) [국내주식-075] FHPTJ04040000.

    당일 최종 집계 (장 마감 후 또는 시세 API 실패 시 fallback). 단위: 십억원.
    KOSPI:  FID_INPUT_ISCD=0001, FID_INPUT_ISCD_1=KSP, FID_INPUT_ISCD_2=0001
    KOSDAQ: FID_INPUT_ISCD=1001, FID_INPUT_ISCD_1=KSQ, FID_INPUT_ISCD_2=1001
    """
    today_ymd = datetime.today().strftime("%Y%m%d")
    today_str  = datetime.today().strftime("%Y-%m-%d")

    is_kosdaq = market.upper() == "KOSDAQ"
    iscd  = "1001" if is_kosdaq else "0001"
    iscd1 = "KSQ"  if is_kosdaq else "KSP"

    r = _kis_get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market",
        "FHPTJ04040000",
        {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD":         iscd,
            "FID_INPUT_DATE_1":       today_ymd,
            "FID_INPUT_ISCD_1":       iscd1,
            "FID_INPUT_DATE_2":       today_ymd,
            "FID_INPUT_ISCD_2":       iscd,
        },
    )
    data = r.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"KIS 투자자 일별 조회 오류 [{market}]: {data.get('msg1', '')}")

    output = data.get("output", [])
    if not output:
        raise ValueError(f"KIS 투자자 일별 데이터 없음 [{market}]")

    row = output[0]

    def _sbj(field: str) -> float:
        try:
            return round(float(row.get(field, 0) or 0) / 1000, 1)
        except (ValueError, TypeError):
            return 0.0

    return {
        "date":             today_str,
        "market":           market.upper(),
        # 일별 API는 순매수(net)만 제공 — 매도/매수는 0으로 채움
        "institution_sell": 0.0,
        "institution_buy":  0.0,
        "institution_net":  _sbj("orgn_ntby_tr_pbmn"),
        "foreign_sell":     0.0,
        "foreign_buy":      0.0,
        "foreign_net":      _sbj("frgn_ntby_tr_pbmn"),
        "individual_sell":  0.0,
        "individual_buy":   0.0,
        "individual_net":   _sbj("prsn_ntby_tr_pbmn"),
    }


# ── 투자자 데이터 (일별 API 우선) ────────────────────────────────────────────
def get_investor_trading_best(market: str = "KOSPI") -> Dict:
    """당일 투자자별 매매동향 반환.

    순매수(net): 일별 API(FHPTJ04040000) — 시장 전체 합계 기준, 정확.
    매도/매수(sell/buy)는 KIS API에서 시장 전체 단위로 제공하지 않으므로 0 반환.
    """
    try:
        return get_investor_trading_daily(market)
    except Exception:
        raise ValueError(f"투자자 데이터 조회 실패 [{market}]")


def get_investor_trading_history(market: str = "KOSPI", days: int = 20) -> list:
    """KIS FHPTJ04040000으로 투자자별 매매동향 히스토리 조회.

    Args:
        market: "KOSPI" 또는 "KOSDAQ"
        days:   최근 N 영업일 (최대 300)

    Returns:
        [{"date": "YYYY-MM-DD", "market": str,
          "institution": float, "foreign": float, "individual": float}, ...]
        단위: 억원 (1e8원). 최신순 정렬.
    """
    today_ymd = datetime.today().strftime("%Y%m%d")
    # days보다 넉넉하게 조회 (공휴일·주말 포함하므로 *2+10 여유)
    from_dt = (datetime.today() - timedelta(days=days * 2 + 10)).strftime("%Y%m%d")

    is_kosdaq = market.upper() == "KOSDAQ"
    iscd  = "1001" if is_kosdaq else "0001"
    iscd1 = "KSQ"  if is_kosdaq else "KSP"

    r = _kis_get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market",
        "FHPTJ04040000",
        {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD":         iscd,
            "FID_INPUT_DATE_1":       from_dt,
            "FID_INPUT_ISCD_1":       iscd1,
            "FID_INPUT_DATE_2":       today_ymd,
            "FID_INPUT_ISCD_2":       iscd,
        },
    )
    data = r.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"KIS 투자자 히스토리 오류 [{market}]: {data.get('msg1', '')}")

    output = data.get("output", [])
    if not output:
        raise ValueError(f"KIS 투자자 히스토리 없음 [{market}]")

    results = []
    for row in output[:days]:   # 최신순이므로 앞에서 days개 취득
        raw_date = row.get("stck_bsop_date", "")
        if len(raw_date) == 8:
            date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        else:
            date_str = raw_date

        def _to_eok(field: str) -> float:
            """백만원 → 억원 (÷100), 소수 2자리."""
            try:
                return round(float(row.get(field, 0) or 0) / 100, 2)
            except (ValueError, TypeError):
                return 0.0

        results.append({
            "date":        date_str,
            "market":      market.upper(),
            "institution": _to_eok("orgn_ntby_tr_pbmn"),
            "foreign":     _to_eok("frgn_ntby_tr_pbmn"),
            "individual":  _to_eok("prsn_ntby_tr_pbmn"),
        })

    return results


# ── KRX ETF 목록 조회 (pykrx) ───────────────────────────────────────────────

def get_etf_list_from_krx(date_str: str = None) -> List[Dict]:
    """네이버 금융 ETF API로 상장 ETF 전체 목록 조회.

    Returns:
        [{"stock_code": str, "name": str, "exchange": str}, ...]
    """
    import logging as _log
    _logger = _log.getLogger("kis_client")

    try:
        resp = requests.get(
            "https://finance.naver.com/api/sise/etfItemList.nhn",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("resultCode") != "success":
            _logger.warning("네이버 ETF 목록 오류: %s", data.get("resultCode"))
            return []

        result: List[Dict] = []
        for item in data.get("result", {}).get("etfItemList", []):
            code = str(item.get("itemcode", "")).strip()
            if not code or not code.isdigit():
                continue
            name = str(item.get("itemname", "")).strip()
            result.append({"stock_code": code, "name": name, "exchange": "KOSPI"})

        _logger.debug("네이버 ETF 목록 조회 완료: %d개", len(result))
        return result

    except Exception as e:
        _logger.warning("네이버 ETF 목록 조회 실패: %s", e)
        return []


# ── ETF 기본정보 + 구성종목 조회 (네이버 금융 스크래핑) ─────────────────────

_NAVER_ETF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://finance.naver.com/",
}


def _naver_etf_soup(etf_code: str):
    """네이버 금융 ETF 개별 페이지 BeautifulSoup 반환."""
    import logging as _log
    from bs4 import BeautifulSoup

    r = requests.get(
        f"https://finance.naver.com/item/main.naver?code={etf_code}",
        headers=_NAVER_ETF_HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    # 네이버는 EUC-KR 이지만 bytes 그대로 BeautifulSoup에 넘기면 자동 감지됨
    return BeautifulSoup(r.content, "html.parser")


def get_etf_info(etf_code: str) -> Dict:
    """네이버 금융 ETF 페이지에서 기본정보 스크래핑.

    Returns:
        {
            "tracking_index": str | None,   # 기초지수
            "fund_manager":   str | None,   # 자산운용사
            "aum":            float | None, # 순자산 (억원) - 네이버 ETF 목록 API
            "expense_ratio":  float | None, # 총보수율 (현재 None - 미제공)
            "distribution":   str | None,   # 분류 (유형 대용)
        }
    """
    import logging as _log
    _logger = _log.getLogger("kis_client")

    result: Dict = {
        "tracking_index": None,
        "fund_manager":   None,
        "aum":            None,
        "expense_ratio":  None,
        "distribution":   None,
    }

    try:
        soup = _naver_etf_soup(etf_code)
        tables = soup.find_all("table")

        # 테이블[6]: 기초지수·분류·설정일
        # row[0]: 기초지수 / row[1]: 분류 / row[2]: 설정일
        if len(tables) > 6:
            for row in tables[6].find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
                if len(cells) < 2 or not cells[1]:
                    continue
                label, value = cells[0], cells[1]
                if "기초지수" in label and not result["tracking_index"]:
                    result["tracking_index"] = value
                elif "분류" in label and not result["distribution"]:
                    result["distribution"] = value

        # 테이블[7]: 자산운용사
        if len(tables) > 7:
            for row in tables[7].find_all("tr"):
                cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
                if len(cells) >= 2 and cells[1]:
                    result["fund_manager"] = cells[1]
                    break

    except Exception as e:
        _logger.warning("ETF 기본정보 스크래핑 실패 [%s]: %s", etf_code, e)

    # AUM: 네이버 ETF 목록 API (marketSum 단위=억원)
    try:
        resp = requests.get(
            "https://finance.naver.com/api/sise/etfItemList.nhn",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        items = resp.json().get("result", {}).get("etfItemList", [])
        item = next((i for i in items if i.get("itemcode") == etf_code), None)
        if item and item.get("marketSum"):
            result["aum"] = float(item["marketSum"])  # 단위: 억원
    except Exception as e:
        _logger.warning("ETF AUM 조회 실패 [%s]: %s", etf_code, e)

    return result


def get_etf_holdings_pykrx(etf_code: str, top_n: int = 25) -> List[Dict]:
    """네이버 금융 ETF 페이지에서 구성 종목 스크래핑 (상위 10개).

    Returns:
        [{"rank": int, "asset_type": str, "name": str, "weight": float, "stock_code": str | None}, ...]
    """
    import logging as _log
    import re as _re
    _logger = _log.getLogger("kis_client")

    try:
        soup = _naver_etf_soup(etf_code)
        tables = soup.find_all("table")

        # 테이블[3]: 구성종목(구성자산) | 주식수(천주) | 구성비율 | 시세 | 등락 | 등락률
        if len(tables) <= 3:
            return []

        holdings_table = tables[3]
        result = []
        rank = 0

        for row in holdings_table.find_all("tr"):
            # 종목 링크에서 코드 추출
            a_tag = row.find("a", href=_re.compile(r"code=\d+"))
            if not a_tag:
                continue

            name = a_tag.get_text(strip=True)
            code_match = _re.search(r"code=(\d+)", a_tag["href"])
            stock_code = code_match.group(1) if code_match else None

            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            # cells: [종목명, 주식수(천주), 구성비율(%), 시세, 등락, 등락률]
            weight_str = cells[2] if len(cells) > 2 else ""
            weight_str = weight_str.replace("%", "").replace(",", "").strip()
            try:
                weight = float(weight_str)
            except ValueError:
                continue

            rank += 1
            result.append({
                "rank":       rank,
                "asset_type": "주식",
                "name":       name,
                "weight":     round(weight, 2),
                "stock_code": stock_code,
            })

            if rank >= top_n:
                break

        return result

    except Exception as e:
        _logger.warning("ETF 구성 종목 스크래핑 실패 [%s]: %s", etf_code, e)
        return []
