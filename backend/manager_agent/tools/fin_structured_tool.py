# manager_agent/tools/fin_structured_tool.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from crewai.tools import tool

from config import FIN_MODEL_DIR as _FIN_MODEL_DIR

_PARQUET_PATH = _FIN_MODEL_DIR / "data" / "processed" / "fin_scores_v2_2024_CONSOL_with_mc_with_price.parquet"


def _load_report(ticker: str) -> dict | None:
    """structured_report.json에서 해당 종목 데이터를 읽어 반환합니다.
    없으면 fin_scores parquet에서 fallback으로 읽어 동일 포맷으로 변환합니다."""
    t = str(ticker).zfill(6)

    # 1차: structured_report.json
    report_path = _FIN_MODEL_DIR / "data" / "processed" / "structured_report.json"
    if report_path.exists():
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and str(data.get("ticker", "")).zfill(6) == t:
                return data
            if isinstance(data, list):
                candidates = [r for r in data if str(r.get("ticker", "")).zfill(6) == t]
                if candidates:
                    return candidates[-1]
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
                return {
                    "ticker": t,
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
    Args:
        ticker: 종목코드 (예: '005930')
    """
    report = _load_report(ticker)
    if report:
        return json.dumps(report, ensure_ascii=False, indent=2)
    return json.dumps({
        "error": "NOT_FOUND",
        "ticker": str(ticker).zfill(6),
        "message": (
            f"structured_report.json에 해당 종목 데이터가 없습니다. "
            f"generate_fin_structured_report 툴을 사용해 생성하거나, "
            f"fin_structured_model 파이프라인을 먼저 실행하세요. "
            f"경로: {_FIN_MODEL_DIR / 'data' / 'processed' / 'structured_report.json'}"
        ),
    }, ensure_ascii=False)


@tool("generate_fin_structured_report")
def generate_fin_structured_report(ticker: str, as_of: str) -> str:
    """fin_structured_model 파이프라인을 실행하여 해당 종목/기준일의 재무 리포트를 새로 생성합니다.
    데이터가 없거나 최신화가 필요한 경우 사용하세요. 실행에 수 분이 걸릴 수 있습니다.
    Args:
        ticker: 종목코드 (예: '005930')
        as_of: 기준일 YYYY-MM-DD (예: '2024-12-31')
    """
    cmd = [
        sys.executable, "-m", "scripts.run_full_auto_structured",
        "--ticker", str(ticker).zfill(6),
        "--as_of", str(as_of),
        "--target_year", "2024",
        "--base_year", "2023",
        "--fs_div", "CONSOL",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_FIN_MODEL_DIR))
    if proc.returncode != 0:
        return json.dumps({
            "error": "PIPELINE_FAILED",
            "stderr": proc.stderr[:1000],
            "stdout": proc.stdout[:500],
        }, ensure_ascii=False)

    report = _load_report(ticker)
    if report:
        return json.dumps(report, ensure_ascii=False, indent=2)
    return json.dumps({"error": "REPORT_NOT_GENERATED", "ticker": ticker}, ensure_ascii=False)
