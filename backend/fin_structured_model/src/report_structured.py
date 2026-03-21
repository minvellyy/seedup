from __future__ import annotations
import pandas as pd
import numpy as np

def pct(x: float | None) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "N/A"
    return f"{x*100:.2f}%"

def num(x: float | None) -> float | None:
    if x is None:
        return None
    if isinstance(x, float) and np.isnan(x):
        return None
    return float(x)

def build_structured_report(df_scores: pd.DataFrame, ticker: str, as_of: str) -> dict:
    t = str(ticker).zfill(6)
    a = pd.to_datetime(as_of).normalize()

    d = df_scores.copy()
    d["ticker"] = d["ticker"].astype(str).str.zfill(6)
    d["as_of"] = pd.to_datetime(d["as_of"]).dt.normalize()

    row = d[(d["ticker"] == t) & (d["as_of"] == a)]
    if row.empty:
        return {
            "error": "NOT_FOUND",
            "ticker": t,
            "as_of": str(a.date()),
            "message": "해당 ticker/as_of 조합이 스코어 파일에 없습니다."
        }

    r = row.iloc[0].to_dict()

    # 핵심 문장 (필요하면 너 스타일로 더 고급화 가능)
    key_takeaways = []
    if "opm" in r: key_takeaways.append(f"수익성(OPM) {pct(r.get('opm'))}")
    if "roa" in r: key_takeaways.append(f"ROA {pct(r.get('roa'))}")
    if "ret_3m" in r and r.get("ret_3m") is not None: key_takeaways.append(f"3개월 수익률 {pct(r.get('ret_3m'))}")
    if "dd_52w" in r and r.get("dd_52w") is not None: key_takeaways.append(f"52주 낙폭 {pct(r.get('dd_52w'))}")

    # 데이터 품질 노트
    dq_notes = []
    if bool(r.get("ttm_net_income_proxy", False)):
        dq_notes.append("최근 4개 분기 중 일부 분기에서 당기순이익 공시 항목이 없어 세전이익으로 대체 산출했습니다.")
    if pd.isna(r.get("market_cap")):
        dq_notes.append("시가총액 데이터를 연결하지 못해 PER/PBR 산출이 제한될 수 있습니다.")
    if bool(r.get("price_missing", False)):
        dq_notes.append("가격 데이터가 일부 누락되어 수익률/변동성 지표 신뢰도가 낮을 수 있습니다.")
    data_quality_note = " ".join(dq_notes) if dq_notes else None

    out = {
        "ticker": t,
        "as_of": str(a.date()),
        "summary": {
            "overall_grade": r.get("overall_grade"),
            "overall_score": num(r.get("overall_score")),
            "key_takeaways": key_takeaways[:4],
            "data_quality_note": data_quality_note,
        },
        "metrics": {
            "profitability": {
                "opm": num(r.get("opm")),
                "roa": num(r.get("roa")),
            },
            "growth": {
                "sales_yoy": num(r.get("sales_yoy")),
                "op_income_yoy": num(r.get("op_income_yoy")),
            },
            "stability": {
                "debt_equity": num(r.get("debt_equity")),
                "current_ratio": num(r.get("current_ratio")),
            },
            "cashflow": {
                "cfo_margin": num(r.get("cfo_margin")),
                "fcf_margin": num(r.get("fcf_margin")),
            },
            "valuation": {
                "per": num(r.get("per")),
                "pbr": num(r.get("pbr")),
                "market_cap": num(r.get("market_cap")),
            },
            "price": {
                "close_asof": num(r.get("close_asof")),
                "ret_3m": num(r.get("ret_3m")),
                "ret_6m": num(r.get("ret_6m")),
                "ret_12m": num(r.get("ret_12m")),
                "vol_3m": num(r.get("vol_3m")),
                "vol_6m": num(r.get("vol_6m")),
                "dd_52w": num(r.get("dd_52w")),
            }
        },
        "flags": {
            "ttm_net_income_proxy": bool(r.get("ttm_net_income_proxy", False)),
            "has_market_cap": not pd.isna(r.get("market_cap")),
            "has_price": not bool(r.get("price_missing", False)),
            "price_source": r.get("price_source"),
            "market_cap_source": r.get("market_cap_source"),
        },
        "evidence": {
            "source": ["DART", "yfinance"],
            "notes": [
                "재무 지표는 연결 기준, 최근 4개 분기(TTM) 기반",
                "가격 지표는 분기말(as_of) 직전 거래일 종가 기준",
            ],
        }
    }
    return out