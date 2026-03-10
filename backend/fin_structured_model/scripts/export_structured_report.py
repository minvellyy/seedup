import json
import argparse
import pandas as pd
from pathlib import Path
from src.nlg_structured import make_narrative

DEFAULT_SCORE_PATH = Path("data/processed/fin_scores_v2_smoke_2024_CONSOL_with_mc.parquet")

def make_note(row: dict) -> str | None:
    if row.get("ttm_net_income_proxy", False):
        return "최근 4개 분기 중 일부 분기에서 당기순이익 공시 항목이 없어 세전이익으로 대체 산출했습니다."
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--as_of", default="latest")  # e.g. 2024-09-30
    ap.add_argument("--in_path", default=str(DEFAULT_SCORE_PATH))
    ap.add_argument("--out_path", default="data/processed/structured_report.json")
    args = ap.parse_args()

    df = pd.read_parquet(args.in_path)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    args.ticker = str(args.ticker).zfill(6)

    df["as_of"] = pd.to_datetime(df["as_of"])

    sub = df[df["ticker"] == args.ticker].copy()
    if sub.empty:
        raise SystemExit(f"[ERR] ticker not found: {args.ticker}")

    if args.as_of == "latest":
        row = sub.sort_values("as_of").iloc[-1]
    else:
        target = pd.to_datetime(args.as_of)
        sub2 = sub[sub["as_of"] == target]
        if sub2.empty:
            raise SystemExit(f"[ERR] as_of not found for {args.ticker}: {args.as_of}")
        row = sub2.iloc[0]

    r = row.to_dict()
    note = make_note(r)

    payload = {
        "ticker": r["ticker"],
        "as_of": str(pd.to_datetime(r["as_of"]).date()),
        "summary": {
            "overall_grade": r.get("overall_grade"),
            "overall_score": None if pd.isna(r.get("overall_score")) else float(r.get("overall_score")),
            "key_takeaways": [
                f"수익성(OPM) {None if pd.isna(r.get('opm')) else round(float(r['opm'])*100,2)}%",
                f"ROA {None if pd.isna(r.get('roa')) else round(float(r['roa'])*100,2)}%",
            ],
            "data_quality_note": note,
        },
        "metrics": {
            "profitability": {"opm": None if pd.isna(r.get("opm")) else float(r["opm"]),
                              "roa": None if pd.isna(r.get("roa")) else float(r["roa"])},
            "growth": {"sales_yoy": None if pd.isna(r.get("sales_yoy")) else float(r["sales_yoy"]),
                       "op_income_yoy": None if pd.isna(r.get("op_income_yoy")) else float(r["op_income_yoy"])},
            "stability": {"debt_equity": None if pd.isna(r.get("debt_equity")) else float(r["debt_equity"]),
                          "current_ratio": None if pd.isna(r.get("current_ratio")) else float(r["current_ratio"])},
            "cashflow": {"cfo_margin": None if pd.isna(r.get("cfo_margin")) else float(r["cfo_margin"]),
                         "fcf_margin": None if pd.isna(r.get("fcf_margin")) else float(r["fcf_margin"])},
            "valuation": {"per": None if pd.isna(r.get("per")) else float(r["per"]),
                          "pbr": None if pd.isna(r.get("pbr")) else float(r["pbr"])},
            "price": { "close_asof": None if pd.isna(r.get("close_asof")) else float(r["close_asof"]),
                "ret_3m": None if pd.isna(r.get("ret_3m")) else float(r["ret_3m"]),
                "ret_6m": None if pd.isna(r.get("ret_6m")) else float(r["ret_6m"]),
                "ret_12m": None if pd.isna(r.get("ret_12m")) else float(r["ret_12m"]),
                "vol_3m": None if pd.isna(r.get("vol_3m")) else float(r["vol_3m"]),
                "vol_6m": None if pd.isna(r.get("vol_6m")) else float(r["vol_6m"]),
                "dd_52w": None if pd.isna(r.get("dd_52w")) else float(r["dd_52w"]),
                "price_source": None if pd.isna(r.get("price_source")) else str(r.get("price_source")),
            },
        },
        "flags": {
            "ttm_net_income_proxy": bool(r.get("ttm_net_income_proxy", False)),
            "has_market_cap": not pd.isna(r.get("market_cap")),
            "has_cashflow": not (pd.isna(r.get("cfo_margin")) and pd.isna(r.get("fcf_margin"))),
            "has_price": not bool(r.get("price_missing", False)),
            "price_missing": bool(r.get("price_missing", False)),
            "has_valuation": not (pd.isna(r.get("per")) and pd.isna(r.get("pbr"))),
        },
        "evidence": {
            "source": ["DART", "yfinance"],
            "notes": ["지표는 연결 기준, 최근 4개 분기(TTM) 기반", "가격/시총은 yfinance 기반(소스 컬럼 참조)"],
        },
    }
    
    nlg = make_narrative(payload)
    payload["summary"]["narrative"] = nlg["narrative"]
    payload["summary"]["highlights"] = nlg["highlights"]
    payload["summary"]["warnings"] = nlg["warnings"]

    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")

if __name__ == "__main__":
    main()