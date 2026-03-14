"""키움증권 Open Trading API 클라이언트.

한국투자증권(KIS) API에서 키움증권 REST API로 교체.
함수 인터페이스는 동일하게 유지되어 기존 import 변경 불필요.

사용 예:
    from kis_client import get_current_price, get_daily_prices_1y

    price_info = get_current_price("005930")   # 삼성전자 현재가
    history    = get_daily_prices_1y("005930") # 1년 일별 데이터

키움증권 Open Trading API 공식 문서: https://apiportal.kiwoom.com/
※ 응답 필드명은 공식 문서와 대조하여 확인하세요.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

_logger = logging.getLogger(__name__)

# .env 로드 (backend/ 기준)
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

BASE_URL = "https://api.kiwoom.com"

# 토큰 캐시 파일 경로
_TOKEN_FILE = Path(__file__).parent / ".kiwoom_token_cache"

# ── 토큰 캐시 (메모리 + 파일 이중 저장) ──────────────────────────────────────
import threading as _threading
_token_cache: Dict = {"token": None, "expires_at": 0.0}
_token_lock = _threading.Lock()  # 다중 스레드 동시 갱신 방지
_pykrx_log_lock = _threading.Lock()  # pykrx 호출 시 root logger 레벨 임시 변경 — 레이스 컨디션 방지


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


_LEGACY_TOKEN_FILES = [
    Path(__file__).parent / ".kis_token_cache",
]


def _save_token_to_file(token: str, expires_at: float) -> None:
    try:
        _TOKEN_FILE.write_text(
            json.dumps({"token": token, "expires_at": expires_at}),
            encoding="utf-8",
        )
    except Exception:
        pass
    # 구버전 캐시 파일 삭제
    for legacy in _LEGACY_TOKEN_FILES:
        try:
            if legacy.exists():
                legacy.unlink()
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

        # 키움증권 토큰 발급 (grant_type, appkey, secretkey)
        resp = requests.post(
            f"{BASE_URL}/oauth2/token",
            json={
                "grant_type": "client_credentials",
                "appkey":     os.getenv("APP_KEY", "").strip(),
                "secretkey":  os.getenv("APP_SECRET", "").strip(),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        token      = data["token"]
        expires_at = now + int(data.get("expires_in", 86400))
        _token_cache["token"]      = token
        _token_cache["expires_at"] = expires_at
        _save_token_to_file(token, expires_at)
        return token


# ── Rate limiter (초당 거래건수 초과 방지) ────────────────────────────────────
import time as _time_module

_rate_lock = _threading.Lock()
_last_call_time: float = 0.0
_MIN_INTERVAL = 0.07  # 초 (≈ 14 req/s)


def _rate_limited_post(url: str, headers: Dict, body: Dict, timeout: int = 10):
    """초당 요청 수를 제한하며 POST 요청."""
    global _last_call_time
    with _rate_lock:
        now = _time_module.monotonic()
        elapsed = now - _last_call_time
        if elapsed < _MIN_INTERVAL:
            _time_module.sleep(_MIN_INTERVAL - elapsed)
        _last_call_time = _time_module.monotonic()
    return requests.post(url, headers=headers, json=body, timeout=timeout)


def _kiwoom_post(url: str, tr_id: str, body: Dict, retry: bool = True):
    """키움증권 POST 요청 헬퍼. 토큰 만료 시 갱신 후 1회 재시도."""
    import logging as _logging
    _logger = _logging.getLogger("kiwoom_client")

    r = _rate_limited_post(url, headers=_headers(tr_id), body=body, timeout=10)

    if r.status_code in (401, 500) and retry:
        try:
            body_j = r.json()
            msg = body_j.get("msg", body_j.get("message", ""))
            err_cd = body_j.get("return_code", "")
        except Exception:
            msg, err_cd = r.text[:500], ""

        _logger.warning("키움 API 오류 — status=%s msg=%r url=%s", r.status_code, msg, url)

        # 토큰 만료로 판단되면 재발급 후 재시도
        if r.status_code == 401 or "token" in msg.lower() or "인증" in msg:
            _logger.info("토큰 만료 감지 — force_refresh 후 재시도")
            _get_token(force_refresh=True)
            r = _rate_limited_post(url, headers=_headers(tr_id), body=body, timeout=10)
        elif "초과" in msg or "한도" in msg:
            _logger.warning("Rate limit — 0.5초 대기 후 재시도")
            _time_module.sleep(0.5)
            r = _rate_limited_post(url, headers=_headers(tr_id), body=body, timeout=10)
        else:
            _logger.warning("재시도 불필요 오류, 생략")

    r.raise_for_status()
    return r


def _headers(tr_id: str) -> Dict[str, str]:
    return {
        "authorization": f"Bearer {_get_token()}",
        "api-id":        tr_id,
        "content-type":  "application/json; charset=utf-8",
    }


# ── 현재가 조회 ─────────────────────────────────────────────────────────────
def get_current_price(stock_code: str) -> Dict:
    """국내 주식 현재가 조회 (키움 ka10001).

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
    r = _kiwoom_post(
        f"{BASE_URL}/api/dostk/stkinfo",
        "ka10001",
        {"stk_cd": stock_code},
    )
    data = r.json()

    # 키움 응답: return_code=0 이면 성공
    if str(data.get("return_code", "0")) != "0":
        raise ValueError(f"키움 API 오류 [{stock_code}]: {data.get('return_msg', '')}")

    # ka10001 /api/dostk/stkinfo 응답은 flat dict (output 래퍼 없음)
    out = data

    def _f(key: str) -> float:
        v = out.get(key, 0) or 0
        try:
            return abs(float(str(v).replace(",", "").replace("+", "").replace("-", "")))
        except ValueError:
            return 0.0

    def _signed(key: str) -> float:
        """부호 포함 float (키움은 음수를 '-'로 표기)."""
        v = str(out.get(key, "0") or "0").replace(",", "")
        try:
            return float(v)
        except ValueError:
            return 0.0

    return {
        "current_price": _f("cur_prc"),
        "prev_close":    _f("base_pric"),   # 기준가 = 전일 종가
        "change":        _signed("pred_pre"),  # 전일 대비 (부호 포함)
        "change_rate":   _signed("flu_rt"),
        "volume":        int(_f("trde_qty")),
        "price_date":    datetime.today().strftime("%Y-%m-%d"),
    }


# ── 일별 OHLCV 조회 ─────────────────────────────────────────────────────────
def _get_daily_chunk(
    stock_code: str,
    start_yyyymmdd: str,
    end_yyyymmdd: str,
) -> List[Dict]:
    """특정 기간 일별 종가 조회 (키움 ka10081).

    ka10081: base_dt 기준 이전 데이터를 최대 N건 반환 (start 필터는 클라이언트에서 처리).
    """
    r = _kiwoom_post(
        f"{BASE_URL}/api/dostk/chart",
        "ka10081",
        {
            "stk_cd":       stock_code,
            "base_dt":      end_yyyymmdd,   # 기준일자 (YYYYMMDD)
            "upd_stkpc_tp": "1",            # 수정주가 적용
        },
    )
    data = r.json()

    if str(data.get("return_code", "0")) != "0":
        return []

    # 응답: stk_dt_pole_chart_qry 배열
    rows = data.get("stk_dt_pole_chart_qry", [])
    if not rows:
        # fallback — 일부 버전에서 output1 키 사용
        rows = data.get("output1", data.get("output", []))
    if isinstance(rows, dict):
        rows = [rows]

    result: List[Dict] = []
    for row in rows:
        d = str(row.get("dt", "")).replace("-", "")
        c = row.get("cur_prc", "")   # 현재가(종가)
        if not d or not c:
            continue
        if len(d) == 8 and d < start_yyyymmdd:   # start보다 이전 날짜 skip
            continue
        fmt_date = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d

        def _fv(k):
            v = row.get(k, "")
            try:
                return abs(float(str(v).replace(",", "").replace("+", ""))) if v else None
            except ValueError:
                return None

        result.append({
            "date":   fmt_date,
            "open":   _fv("open_pric"),
            "high":   _fv("high_pric"),
            "low":    _fv("low_pric"),
            "close":  abs(float(str(c).replace(",", "").replace("+", "") or 0)),
            "volume": int(_fv("trde_qty") or 0) or None,
        })
    return result


def get_daily_prices_1y(stock_code: str) -> List[Dict]:
    """최근 1년 일별 OHLCV 리스트 (오름차순).

    키움 ka10081 최대 ~100건 → 4회로 나눠 1년 커버.
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
# 키움 지수 코드: 001=KOSPI, 101=KOSDAQ
_INDEX_MRKT = {"KOSPI": "001", "KOSDAQ": "101"}
# 장 휴장일에 모든 데이터 소스 실패 시 반환할 직전 성공값 캐시 (프로세스 수명 동안 유지)
_last_known_index: Dict[str, Dict] = {}


def get_index_price(market: str) -> Dict:
    """국내 주요 지수 현재가 조회 (키움 ka20004).

    Args:
        market: "KOSPI" 또는 "KOSDAQ"

    Returns:
        {
            "market":      str,
            "index":       float,
            "prev_close":  float,
            "change":      float,
            "change_rate": float,
            "open":        float,
            "high":        float,
            "low":         float,
            "price_date":  str,
        }
    """
    mrkt_tp = _INDEX_MRKT.get(market.upper())
    if not mrkt_tp:
        raise ValueError(f"지원하지 않는 시장: {market}")

    YAHOO_IDX = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
    yf_ticker = YAHOO_IDX.get(market.upper())

    # 1순위: yfinance (^KS11 / ^KQ11)
    try:
        import yfinance as _yf
        yt = _yf.Ticker(yf_ticker)
        hist = yt.history(period="5d")
        if hist is not None and len(hist) >= 1:
            cur = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else cur
            chg = cur - prev_close
            chg_rt = round(chg / prev_close * 100, 2) if prev_close else 0.0
            result = {
                "market":      market.upper(),
                "index":       round(cur, 2),
                "prev_close":  round(prev_close, 2),
                "change":      round(chg, 2),
                "change_rate": chg_rt,
                "open":        round(float(hist["Open"].iloc[-1]), 2),
                "high":        round(float(hist["High"].iloc[-1]), 2),
                "low":         round(float(hist["Low"].iloc[-1]), 2),
                "price_date":  datetime.today().strftime("%Y-%m-%d"),
            }
            _last_known_index[market.upper()] = result
            return result
    except Exception as _yf_err:
        _logger.debug("yfinance 지수 조회 실패: %s", _yf_err)

    # 2순위: pykrx (get_index_ohlcv_by_date — KRX 서버 상태에 따라 실패할 수 있음)
    try:
        import logging as _logging
        from pykrx import stock as _pykrx_stock
        idx_ticker = "1001" if market.upper() == "KOSPI" else "2001"
        today_str = datetime.today().strftime("%Y%m%d")
        # pykrx util.py 버그: logging.info(args, kwargs) 형식 오류로 --- Logging error --- 발생
        # root logger도 일시 억제 (pykrx는 내부적으로 root logging 사용)
        # _pykrx_log_lock 으로 멀티스레드 환경에서 log level 레이스 컨디션 방지
        with _pykrx_log_lock:
            _root = _logging.getLogger()
            _prev_lvl = _root.level
            _root.setLevel(_logging.CRITICAL)
            try:
                df = _pykrx_stock.get_index_ohlcv_by_date(
                    (datetime.today() - timedelta(days=10)).strftime("%Y%m%d"),
                    today_str, idx_ticker
                )
            finally:
                _root.setLevel(_prev_lvl)
        if df is not None and len(df) >= 1:
            row = df.iloc[-1]
            prev_close = float(df.iloc[-2]["종가"]) if len(df) >= 2 else float(row["시가"])
            cur = float(row["종가"])
            chg = cur - prev_close
            chg_rt = round(chg / prev_close * 100, 2) if prev_close else 0.0
            result = {
                "market":      market.upper(),
                "index":       cur,
                "prev_close":  prev_close,
                "change":      round(chg, 2),
                "change_rate": chg_rt,
                "open":        float(row["시가"]),
                "high":        float(row["고가"]),
                "low":         float(row["저가"]),
                "price_date":  datetime.today().strftime("%Y-%m-%d"),
            }
            _last_known_index[market.upper()] = result
            return result
    except Exception as _pykrx_err:
        _logger.debug("pykrx 지수 조회 실패: %s", _pykrx_err)

    # 모든 소스 실패 시 직전 성공값 반환 (휴장일 대응)
    if market.upper() in _last_known_index:
        _logger.debug("지수 조회 실패 — 직전 성공값 반환 (%s)", market.upper())
        return _last_known_index[market.upper()]

    # 완전 초기 상태에서도 실패하면 0 구조 반환
    return {
        "market": market.upper(), "index": 0.0, "prev_close": 0.0,
        "change": 0.0, "change_rate": 0.0, "open": 0.0, "high": 0.0,
        "low": 0.0, "price_date": datetime.today().strftime("%Y-%m-%d"),
    }


def get_investor_trading(market: str = "KOSPI") -> Dict:
    """시장별 투자자 매매동향 당일 — pykrx 폴백 (키움 ka10064 미서비스)."""
    today_str = datetime.today().strftime("%Y-%m-%d")
    try:
        import logging as _logging
        # pykrx 내부 logging.info(args, kwargs) 버그로 인한 --- Logging error --- 억제
        # pykrx는 named logger가 아닌 root logging 직접 사용하므로 root도 억제
        # _pykrx_log_lock 으로 멀티스레드 환경에서 log level 레이스 컨디션 방지
        _pykrx_logger = _logging.getLogger("pykrx")
        _pykrx_logger.setLevel(_logging.CRITICAL)
        with _pykrx_log_lock:
            _root = _logging.getLogger()
            _prev_lvl = _root.level
            _root.setLevel(_logging.CRITICAL)
            from pykrx import stock as _pykrx_stock
            today_ymd = datetime.today().strftime("%Y%m%d")
            from_ymd = (datetime.today() - timedelta(days=7)).strftime("%Y%m%d")
            ticker = "KOSPI" if market.upper() == "KOSPI" else "KOSDAQ"
            try:
                df = _pykrx_stock.get_market_trading_value_by_investor(from_ymd, today_ymd, ticker)
            finally:
                _root.setLevel(_prev_lvl)
        if df is not None and len(df) > 0:
            row = df.iloc[-1]  # 가장 최근 거래일 데이터 사용 (주말/공휴일 대응)
            data_date = df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], "strftime") else today_str
            def _gbj(col):
                try:
                    return round(float(row[col]) / 1e8, 1)  # 원 → 억원
                except Exception:
                    return 0.0
            # pykrx columns: 외국인, 기관, 개인, ...
            frgn = _gbj("외국인")
            orgn = _gbj("기관")
            indv = _gbj("개인")
            return {
                "date": data_date, "market": market.upper(),
                "institution_sell": 0.0, "institution_buy": 0.0, "institution_net": orgn,
                "foreign_sell":     0.0, "foreign_buy":     0.0, "foreign_net":     frgn,
                "individual_sell":  0.0, "individual_buy":  0.0, "individual_net":  indv,
            }
    except Exception as _e:
        logger.debug("pykrx 투자자 조회 실패: %s", _e)
    return _empty_investor(market, today_str)


def _empty_investor(market: str, date_str: str) -> Dict:
    return {
        "date": date_str, "market": market.upper(),
        "institution_sell": 0.0, "institution_buy": 0.0, "institution_net": 0.0,
        "foreign_sell":     0.0, "foreign_buy":     0.0, "foreign_net":     0.0,
        "individual_sell":  0.0, "individual_buy":  0.0, "individual_net":  0.0,
    }


def get_investor_trading_daily(market: str = "KOSPI") -> Dict:
    """당일 최종 집계 투자자 매매동향 (키움 ka10064)."""
    return get_investor_trading(market)


# ── 투자자 데이터 (일별 API 우선) ────────────────────────────────────────────
def get_investor_trading_best(market: str = "KOSPI") -> Dict:
    """당일 투자자별 매매동향 반환. 실패 시 빈 구조 반환 (예외 raise 없음)."""
    today_str = datetime.today().strftime("%Y-%m-%d")
    try:
        return get_investor_trading_daily(market)
    except Exception:
        pass
    return _empty_investor(market, today_str)


def get_investor_trading_history(market: str = "KOSPI", days: int = 20) -> list:
    """투자자별 매매동향 히스토리 조회 (키움 ka10008 반복 조회).

    Args:
        market: "KOSPI" 또는 "KOSDAQ"
        days:   최근 N 영업일

    Returns:
        [{"date": "YYYY-MM-DD", "market": str,
          "institution": float, "foreign": float, "individual": float}, ...]
        단위: 억원. 최신순 정렬.
    """
    today_ymd = datetime.today().strftime("%Y%m%d")
    from_dt = (datetime.today() - timedelta(days=days * 2 + 10)).strftime("%Y%m%d")
    mrkt_tp = "001" if market.upper() == "KOSPI" else "101"

    try:
        r = _kiwoom_post(
            f"{BASE_URL}/api/dostk/invstdivtrnd",
            "ka10064",
            {
                "mrkt_tp":    mrkt_tp,
                "amt_qty_tp": "1",
                "trde_tp":    "0",
                "stk_cd":     "",
            },
        )
        data = r.json()
    except Exception:
        return []

    if str(data.get("return_code", "0")) != "0":
        return []

    rows = data.get("opmr_invsr_trde_chart", [])
    if isinstance(rows, dict):
        rows = [rows]

    today_str = datetime.today().strftime("%Y-%m-%d")
    results = []
    for row in rows[:days]:
        # tm 필드가 HHMMSS 형식이면 당일 시간별 → 날짜는 오늘로 처리
        tm = str(row.get("tm", ""))
        date_str = today_str

        def _to_eok(k: str) -> float:
            """매매금액(백만원) → 억원 (÷100)."""
            v = str(row.get(k, 0) or 0).replace(",", "")
            try:
                return round(float(v) / 100, 2)
            except ValueError:
                return 0.0

        orgn = _to_eok("orgn")
        frgn = _to_eok("frgnr_invsr")
        results.append({
            "date":        date_str,
            "market":      market.upper(),
            "institution": orgn,
            "foreign":     frgn,
            "individual":  round(-(orgn + frgn), 2),
        })
    return results


# ── KRX ETF 목록 조회 ───────────────────────────────────────────────────────

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

