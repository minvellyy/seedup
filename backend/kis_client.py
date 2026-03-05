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

BASE_URL = "https://openapi.koreainvestment.com:9443"

# 토큰 캐시 파일 경로 (project root 는 backend/ )
_TOKEN_FILE = Path(__file__).parent / ".kis_token_cache"

# ── 토큰 캐시 (메모리 + 파일 이중 저장) ──────────────────────────────────────
_token_cache: Dict = {"token": None, "expires_at": 0.0}


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


def _get_token() -> str:
    """access_token 발급 (1일 1회 제한 → 파일 캐시 우선 사용)."""
    now = time.time()
    # 메모리 캐시 확인
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]
    # 파일 캐시 확인
    if _load_token_from_file():
        return _token_cache["token"]

    # 신규 발급
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
    r = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
        headers=_headers("FHKST01010100"),
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         stock_code,
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()

    if data.get("rt_cd") != "0":
        raise ValueError(f"KIS API 오류 [{stock_code}]: {data.get('msg1', '')}")

    o = data["output"]
    raw_date = o.get("stck_bsop_date", "")  # 'YYYYMMDD' — 장중에는 비어있을 수 있음
    if len(raw_date) == 8:
        fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
    else:
        fmt_date = datetime.today().strftime("%Y-%m-%d")  # fallback: 오늘

    return {
        "current_price": float(o.get("stck_prpr", 0) or 0),
        "prev_close":    float(o.get("stck_sdpr", 0) or 0),
        "change":        float(o.get("prdy_vrss", 0) or 0),
        "change_rate":   float(o.get("prdy_ctrt", 0) or 0),
        "volume":        int(o.get("acml_vol", 0) or 0),
        "price_date":    fmt_date,
    }


# ── 일별 OHLCV 조회 ─────────────────────────────────────────────────────────
def _get_daily_chunk(
    stock_code: str,
    start_yyyymmdd: str,
    end_yyyymmdd: str,
) -> List[Dict]:
    """특정 기간 일별 종가 조회 (최대 ~100 거래일)."""
    r = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        headers=_headers("FHKST03010100"),
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         stock_code,
            "FID_INPUT_DATE_1":       start_yyyymmdd,
            "FID_INPUT_DATE_2":       end_yyyymmdd,
            "FID_PERIOD_DIV_CODE":    "D",
            "FID_ORG_ADJ_PRC":        "0",   # 수정주가 미반영
        },
        timeout=15,
    )
    r.raise_for_status()
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
        result.append({
            "date":   fmt_date,
            "close":  float(c),
            "volume": int(row.get("acml_vol", 0) or 0) or None,
        })
    return result


def get_daily_prices_1y(stock_code: str) -> List[Dict]:
    """최근 1년 일별 종가 리스트 (오름차순).

    KIS API 1회 호출 최대 100건 한계 → 3회로 나눠 1년 커버.
    반환: [{"date": "YYYY-MM-DD", "close": float, "volume": int|None}, ...]
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

    r = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price",
        headers=_headers("FHPUP02100000"),
        params={
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD":         iscd,
        },
        timeout=10,
    )
    r.raise_for_status()
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
    iscd_2 = "S001" if market.upper() == "KOSPI" else "Q001"

    r = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor-time-by-market",
        headers=_headers("FHPTJ04030000"),
        params={
            "FID_INPUT_ISCD":   "999",
            "FID_INPUT_ISCD_2": iscd_2,
        },
        timeout=10,
    )
    r.raise_for_status()
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

    r = requests.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market",
        headers=_headers("FHPTJ04040000"),
        params={
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD":         iscd,
            "FID_INPUT_DATE_1":       today_ymd,
            "FID_INPUT_ISCD_1":       iscd1,
            "FID_INPUT_DATE_2":       today_ymd,
            "FID_INPUT_ISCD_2":       iscd,
        },
        timeout=10,
    )
    r.raise_for_status()
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


# ── 투자자 데이터 (시세 우선, 실패 시 일별 fallback) ──────────────────────────
def get_investor_trading_best(market: str = "KOSPI") -> Dict:
    """get_investor_trading (시세) 우선, 실패 시 get_investor_trading_daily 사용."""
    try:
        result = get_investor_trading(market)
        # 모든 값이 0이면 빈 데이터 → 일별 재시도
        if result["institution_net"] == 0 and result["foreign_net"] == 0:
            raise ValueError("empty snapshot")
        return result
    except Exception:
        return get_investor_trading_daily(market)

