# manager_agent/tools/fin_structured_tool.py
from __future__ import annotations

import json
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path


from crewai.tools import tool

from config import FIN_MODEL_DIR as _FIN_MODEL_DIR


def _resolve_parquet_path() -> Path:
    """가장 최신 연도의 fin_scores parquet 파일을 자동 선택."""
    processed = _FIN_MODEL_DIR / "data" / "processed"
    candidates = sorted(processed.glob("fin_scores_v2_*_CONSOL_with_mc_with_price.parquet"))
    return candidates[-1] if candidates else processed / "fin_scores_v2_2024_CONSOL_with_mc_with_price.parquet"

_PARQUET_PATH   = _resolve_parquet_path()
_UNIVERSE_PATH  = _FIN_MODEL_DIR / "data" / "processed" / "universe_k200_k150_fixed.parquet"
_NO_FIN_PATH    = _FIN_MODEL_DIR / "data" / "processed" / "no_fin_data_tickers.json"


@lru_cache(maxsize=1)
def _load_no_fin_set() -> dict:
    """재무 데이터 없는 종목 목록 {ticker: {name, exchange}} — 최초 1회만 로드."""
    if _NO_FIN_PATH.exists():
        try:
            return json.loads(_NO_FIN_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _get_alternatives(ticker: str, top_n: int = 3) -> list[dict]:
    """같은 거래소에서 overall_score 상위 N개 종목을 대안으로 반환."""
    try:
        import pandas as pd
        no_fin = _load_no_fin_set()
        exchange = no_fin.get(ticker, {}).get("exchange", "")

        univ = pd.read_parquet(_UNIVERSE_PATH)
        univ["ticker"] = univ["ticker"].astype(str).str.zfill(6)

        scores = pd.read_parquet(_PARQUET_PATH)
        scores["ticker"] = scores["ticker"].astype(str).str.zfill(6)

        # exchange 필터
        if exchange:
            cands = univ[univ["exchange"] == exchange]["ticker"].tolist()
        else:
            cands = univ["ticker"].tolist()

        # 데이터 없는 종목 제외
        no_fin_set = set(no_fin.keys())
        cands = [t for t in cands if t not in no_fin_set]

        # overall_score 기준 정렬
        score_col = next((c for c in scores.columns if "overall_score" in c), None)
        if score_col:
            sub = scores[scores["ticker"].isin(cands)].copy()
            sub = sub.sort_values(score_col, ascending=False).drop_duplicates("ticker")
            top = sub.head(top_n)
            name_map = univ.set_index("ticker")["name"].to_dict()
            return [
                {
                    "ticker": row["ticker"],
                    "name": name_map.get(row["ticker"], ""),
                    "exchange": exchange,
                    "overall_score": round(float(row[score_col]), 2) if row[score_col] is not None else None,
                }
                for _, row in top.iterrows()
            ]
    except Exception:
        pass
    return []


def _get_db_sector(ticker: str) -> str | None:
    """DB instruments 테이블에서 종목의 sector 값을 반환합니다."""
    try:
        import os
        import pymysql
        from dotenv import load_dotenv
        _here = Path(__file__).resolve().parent.parent.parent  # backend/
        for _env in (_here / ".env", _here.parent / ".env"):
            if _env.exists():
                load_dotenv(_env, override=False)
                break
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            db=os.getenv("DB_NAME"),
            charset="utf8mb4",
            connect_timeout=5,   # 연결 대기 최대 5초
            read_timeout=5,      # 쿼리 응답 대기 최대 5초
            write_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT sector FROM instruments WHERE stock_code = %s LIMIT 1",
                    (str(ticker).zfill(6),),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        return str(row[0]) if row and row[0] else None
    except Exception:
        return None


def _load_report(ticker: str) -> dict | None:
    """structured_report.json에서 해당 종목 데이터를 읽어 반환합니다.
    없으면 fin_scores parquet에서 fallback으로 읽어 동일 포맷으로 변환합니다."""
    t = str(ticker).zfill(6)

    # 1차: structured_report.json
    report_path = _FIN_MODEL_DIR / "data" / "processed" / "structured_report.json"
    if report_path.exists():
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            matched: dict | None = None
            if isinstance(data, dict) and str(data.get("ticker", "")).zfill(6) == t:
                matched = data
            elif isinstance(data, list):
                candidates = [r for r in data if str(r.get("ticker", "")).zfill(6) == t]
                if candidates:
                    matched = candidates[-1]
            if matched is not None:
                # sector가 없거나 비어 있으면 DB에서 보완
                if not matched.get("sector"):
                    matched["sector"] = _get_db_sector(t)
                return matched
        except (json.JSONDecodeError, OSError):
            pass

    # 2차: fin_scores parquet fallback
    if _PARQUET_PATH.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(_PARQUET_PATH)
            sub = df[df["ticker"].astype(str).str.zfill(6) == t]
            if not sub.empty:
                row = sub.sort_values("as_of").iloc[-1]
                def _f(v):
                    import math
                    if v is None: return None
                    try:
                        return None if math.isnan(float(v)) else float(v)
                    except (TypeError, ValueError):
                        return None

                # 회사명 조회 — universe parquet 우선, 없으면 pykrx
                company_name: str | None = None
                try:
                    if _UNIVERSE_PATH.exists():
                        univ = pd.read_parquet(_UNIVERSE_PATH)
                        univ["ticker"] = univ["ticker"].astype(str).str.zfill(6)
                        univ_row = univ[univ["ticker"] == t]
                        if not univ_row.empty:
                            company_name = str(univ_row.iloc[0].get("name", "")) or None
                except Exception:
                    pass
                if not company_name:
                    try:
                        from pykrx import stock as _pykrx
                        _raw_name = _pykrx.get_market_ticker_name(t)
                        if isinstance(_raw_name, str) and _raw_name:
                            company_name = _raw_name
                    except Exception:
                        pass

                return {
                    "ticker": t,
                    "company_name": company_name,
                    "sector": _get_db_sector(t),
                    "as_of": str(row["as_of"])[:10] if "as_of" in row.index else None,
                    "source": "parquet",
                    "summary": {
                        "overall_score": _f(row.get("overall_score")),
                        "overall_grade": str(row["overall_grade"]) if "overall_grade" in row.index and row["overall_grade"] else None,
                        "profitability_score": _f(row.get("profitability_score")),
                        "growth_score": _f(row.get("growth_score")),
                        "stability_score": _f(row.get("stability_score")),
                        "cashflow_score": _f(row.get("cashflow_score")),
                        "valuation_score": _f(row.get("valuation_score")),
                    },
                    "metrics": {
                        "opm": _f(row.get("opm")),
                        "roa": _f(row.get("roa")),
                        "sales_yoy": _f(row.get("sales_yoy")),
                        "op_income_yoy": _f(row.get("op_income_yoy")),
                        "debt_equity": _f(row.get("debt_equity")),
                        "current_ratio": _f(row.get("current_ratio")),
                        "cfo_margin": _f(row.get("cfo_margin")),
                        "fcf_margin": _f(row.get("fcf_margin")),
                        "per": _f(row.get("per")),
                        "pbr": _f(row.get("pbr")),
                        "ret_3m": _f(row.get("ret_3m")),
                        "ret_12m": _f(row.get("ret_12m")),
                        "vol_3m": _f(row.get("vol_3m")),
                    },
                }
        except Exception:
            pass

    return None


@tool("read_fin_structured_report")
def read_fin_structured_report(ticker: str) -> str:
    """fin_structured_model이 생성한 structured_report.json에서 종목의 재무 지표와 종합 스코어를 읽어 반환합니다.
    수익성(OPM/ROA), 성장성(매출/영업이익 YoY), 안정성(부채비율/유동비율),
    현금흐름(CFO/FCF margin), 밸류에이션(PER/PBR), overall_score/grade를 포함합니다.
    재무 데이터가 없는 신규 상장 종목의 경우 대안 종목을 함께 반환합니다.
    Args:
        ticker: 종목코드 (예: '005930')
    """
    report = _load_report(ticker)
    if report:
        return json.dumps(report, ensure_ascii=False, indent=2)

    # crewai .run(dict) 호출 시 ticker가 "{'ticker': '468530'}" 형태로 올 수 있음 — 추출
    _raw_ticker = str(ticker)
    if _raw_ticker.startswith("{") and "ticker" in _raw_ticker:
        try:
            import ast
            _parsed = ast.literal_eval(_raw_ticker)
            _raw_ticker = str(_parsed.get("ticker", _raw_ticker))
        except Exception:
            pass
    t = _raw_ticker.strip().zfill(6)

    # 종목명 조회 — no_fin 캐시 우선, 없을 때만 pykrx 호출
    ticker_name = _load_no_fin_set().get(t, {}).get("name") or None
    if not ticker_name:
        try:
            import logging as _logging
            from pykrx import stock as _pykrx
            # pykrx가 존재하지 않는 ticker 조회 시 내부에서 logging.info(args, kwargs)를
            # 잘못 호출하여 stderr에 "Logging error" 노이즈가 출력됨.
            # root 로거 레벨을 일시 상향해 해당 로그 레코드가 핸들러에 도달하기 전에 차단.
            _root = _logging.getLogger()
            _prev_level = _root.level
            _root.setLevel(_logging.CRITICAL)
            try:
                _raw_name = _pykrx.get_market_ticker_name(t)
            finally:
                _root.setLevel(_prev_level)
            # pykrx가 종목 없으면 빈 DataFrame 반환 → 안전하게 처리
            if isinstance(_raw_name, str) and _raw_name:
                ticker_name = _raw_name
        except Exception:
            pass

    # 같은 거래소에서 재무 데이터가 있는 대안 종목 추천
    alternatives = _get_alternatives(t, top_n=3)

    return json.dumps({
        "error": "NO_FINANCIAL_DATA",
        "ticker": t,
        "ticker_name": ticker_name,
        "reason": (
            "DART 재무제표 데이터가 없습니다. 우선주(preferred stock)이거나 신규 상장·비상장·관리종목일 수 있습니다. "
            "반드시 현재 분석 대상 종목({t})의 분석을 계속 진행하되, "
            "재무 지표 없이 가격·뉴스·ESG 데이터만으로 분석을 수행하세요. "
            "아래 alternatives 종목은 절대로 현재 종목의 분석 내용으로 사용하지 마세요."
        ).format(t=t),
        "fin_score": None,
        "summary": None,
        "alternatives": alternatives,
    }, ensure_ascii=False)


@tool("get_no_fin_data_tickers")
def get_no_fin_data_tickers(dummy: str = "") -> str:
    """재무 데이터(DART 재무제표)가 없는 종목 전체 목록을 반환합니다.
    신규 상장 종목이나 비상장 종목 분석 전에 호출하여 확인하세요.
    Args:
        dummy: 사용 안 함 (툴 인터페이스 호환용)
    """
    no_fin = _load_no_fin_set()
    if not no_fin:
        return json.dumps({"count": 0, "tickers": []}, ensure_ascii=False)
    return json.dumps({
        "count": len(no_fin),
        "tickers": [
            {"ticker": t, **info}
            for t, info in no_fin.items()
        ],
        "note": "이 종목들은 재무 분석 불가. 가격/뉴스/ESG만 활용하거나 대안 종목으로 교체하세요.",
    }, ensure_ascii=False)


# 종목별 생성 락 — 같은 종목의 동시 중복 실행 방지
_generate_locks: dict[str, threading.Lock] = {}
_generate_locks_mutex = threading.Lock()


def _get_generate_lock(ticker: str) -> threading.Lock:
    with _generate_locks_mutex:
        if ticker not in _generate_locks:
            _generate_locks[ticker] = threading.Lock()
        return _generate_locks[ticker]


@tool("generate_fin_structured_report")
def generate_fin_structured_report(ticker: str, as_of: str) -> str:
    """fin_structured_model 파이프라인을 실행하여 해당 종목/기준일의 재무 리포트를 새로 생성합니다.
    데이터가 없거나 최신화가 필요한 경우 사용하세요. 실행에 수 분이 걸릴 수 있습니다.
    Args:
        ticker: 종목코드 (예: '005930')
        as_of: 기준일 YYYY-MM-DD (예: '2024-12-31')
    """
    t = str(ticker).zfill(6)
    lock = _get_generate_lock(t)

    # 이미 같은 종목 생성 중이면 완료될 때까지 대기 후 결과 반환 (중복 subprocess 방지)
    if not lock.acquire(blocking=True, timeout=360):
        return json.dumps({"error": "GENERATE_TIMEOUT", "ticker": t}, ensure_ascii=False)

    try:
        # 락 획득 직후 다른 스레드가 이미 생성했을 수 있으므로 다시 확인
        report = _load_report(t)
        if report:
            return json.dumps(report, ensure_ascii=False, indent=2)

        try:
            _target_year = int(str(as_of)[:4])
        except (ValueError, TypeError):
            from datetime import date
            _target_year = date.today().year - 1
        _base_year = _target_year - 1

        cmd = [
            sys.executable, "-m", "scripts.run_full_auto_structured",
            "--ticker", t,
            "--as_of", str(as_of),
            "--target_year", str(_target_year),
            "--base_year", str(_base_year),
            "--fs_div", "CONSOL",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_FIN_MODEL_DIR), timeout=300)
        if proc.returncode != 0:
            return json.dumps({
                "error": "PIPELINE_FAILED",
                "stderr": proc.stderr[:1000],
                "stdout": proc.stdout[:500],
            }, ensure_ascii=False)

        report = _load_report(t)
        if report:
            return json.dumps(report, ensure_ascii=False, indent=2)
        return json.dumps({"error": "REPORT_NOT_GENERATED", "ticker": t}, ensure_ascii=False)
    finally:
        lock.release()