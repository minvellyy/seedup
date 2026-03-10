# scripts/refresh_single_ticker.py
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.config import SETTINGS
from src.features import add_as_of, build_ttm, compute_features
from src.ytd import ytd_to_quarter


def run(cmd: list[str], allow_fail: bool = False) -> int:
    print("[RUN]", " ".join(cmd))
    p = subprocess.run(cmd, text=True)
    if p.returncode != 0:
        print("[ERR]", " ".join(cmd), "code=", p.returncode)
        if not allow_fail:
            raise SystemExit(p.returncode)
    return p.returncode


def load_year_norm(processed: Path, year: int) -> pd.DataFrame:
    parts = []
    for k in ["Q1", "H1", "Q3", "FY"]:
        p = processed / f"fin_core_norm_{year}_{k}_{SETTINGS.fs_div}.parquet"
        if not p.exists():
            raise FileNotFoundError(f"missing normalized file: {p}")
        df = pd.read_parquet(p)
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def pick_target_row(df: pd.DataFrame, ticker: str, as_of: str) -> pd.Series:
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["as_of"] = pd.to_datetime(df["as_of"])

    sub = df[df["ticker"] == ticker].copy()
    if sub.empty:
        raise SystemExit(f"[ERR] ticker not found in scores: {ticker}")

    if as_of == "latest":
        return sub.sort_values("as_of").iloc[-1]
    else:
        target = pd.to_datetime(as_of)
        sub2 = sub[sub["as_of"] == target]
        if sub2.empty:
            raise SystemExit(f"[ERR] as_of not found for {ticker}: {as_of}")
        return sub2.iloc[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--as_of", default="latest")
    ap.add_argument("--base_year", type=int, default=2023)
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--scores_path", default=f"data/processed/fin_scores_v2_2024_{SETTINGS.fs_div}_with_mc_with_price.parquet")
    ap.add_argument("--price_start", default="2022-01-01")
    ap.add_argument("--out_report", default="")
    args = ap.parse_args()

    ticker = str(args.ticker).zfill(6)
    scores_path = Path(args.scores_path)
    if not scores_path.exists():
        raise FileNotFoundError(f"scores_path not found: {scores_path}")

    processed = Path(SETTINGS.data_dir) / "processed"
    tmp_dir = processed / "tmp_single_refresh"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1) 기존 full scores에서 대상 row 선택
    full_scores = pd.read_parquet(scores_path)
    target_row = pick_target_row(full_scores, ticker, args.as_of)
    target_as_of = pd.to_datetime(target_row["as_of"]).normalize()

    single_scores = pd.DataFrame([target_row])
    single_scores["ticker"] = single_scores["ticker"].astype(str).str.zfill(6)
    single_scores["as_of"] = pd.to_datetime(single_scores["as_of"]).dt.normalize()

    tmp_scores_path = tmp_dir / f"{ticker}_{target_as_of.date()}_scores.parquet"
    single_scores.to_parquet(tmp_scores_path, index=False)

    py = sys.executable

    # 2) 시장가치 최신화 (단건)
    tmp_mc = tmp_dir / f"{ticker}_{target_as_of.date()}_market_cap.parquet"
    run([
        py, "-m", "scripts.fetch_market_cap_yfinance",
        "--scores_path", str(tmp_scores_path),
        "--out_path", str(tmp_mc)
    ], allow_fail=True)

    # 3) 가격 최신화 (단건)
    tmp_daily = tmp_dir / f"{ticker}_{target_as_of.date()}_price_daily.parquet"
    tmp_price_feat = tmp_dir / f"{ticker}_{target_as_of.date()}_price_features.parquet"

    run([
        py, "-m", "scripts.fetch_price_yfinance",
        "--in_scores", str(tmp_scores_path),
        "--start", args.price_start,
        "--out_path", str(tmp_daily)
    ], allow_fail=True)

    run([
        py, "-m", "scripts.build_price_features",
        "--in_scores", str(tmp_scores_path),
        "--price_daily", str(tmp_daily),
        "--out_path", str(tmp_price_feat)
    ], allow_fail=True)

    # 4) 재무 캐시로부터 해당 ticker의 raw metric 재계산
    core = pd.concat(
        [load_year_norm(processed, args.base_year), load_year_norm(processed, args.target_year)],
        ignore_index=True
    )
    core["ticker"] = core["ticker"].astype(str).str.zfill(6)
    core = core[core["ticker"] == ticker].copy()

    core = add_as_of(core)
    core = ytd_to_quarter(core)
    ttm = build_ttm(core)

    mc_df = pd.read_parquet(tmp_mc) if tmp_mc.exists() else pd.DataFrame(columns=["ticker", "as_of", "market_cap"])
    if not mc_df.empty:
        mc_df["ticker"] = mc_df["ticker"].astype(str).str.zfill(6)
        mc_df["as_of"] = pd.to_datetime(mc_df["as_of"]).dt.normalize()

    fresh_metrics = compute_features(ttm, market_cap_df=mc_df)
    fresh_metrics["ticker"] = fresh_metrics["ticker"].astype(str).str.zfill(6)
    fresh_metrics["as_of"] = pd.to_datetime(fresh_metrics["as_of"]).dt.normalize()

    fresh_row = fresh_metrics[
        (fresh_metrics["ticker"] == ticker) &
        (fresh_metrics["as_of"] == target_as_of)
    ]

    if fresh_row.empty:
        # 혹시 latest일 때 TTM row 매칭이 안 되면 기존 row 유지
        merged = single_scores.copy()
    else:
        merged = single_scores.copy()
        fr = fresh_row.iloc[0].to_dict()

        metric_cols = [
            "opm", "roa", "sales_yoy", "op_income_yoy",
            "debt_equity", "current_ratio", "cfo_margin", "fcf_margin",
            "per", "pbr", "market_cap", "ttm_net_income_proxy"
        ]
        for c in metric_cols:
            if c in fr:
                merged[c] = fr[c]

    # 5) 가격 피처 단건 merge
    if tmp_price_feat.exists():
        pf = pd.read_parquet(tmp_price_feat)
        if not pf.empty:
            pf["ticker"] = pf["ticker"].astype(str).str.zfill(6)
            pf["as_of"] = pd.to_datetime(pf["as_of"]).dt.normalize()
            merged["ticker"] = merged["ticker"].astype(str).str.zfill(6)
            merged["as_of"] = pd.to_datetime(merged["as_of"]).dt.normalize()
            merged = merged.drop(columns=[c for c in [
                "close_asof", "ret_3m", "ret_6m", "ret_12m",
                "vol_3m", "vol_6m", "dd_52w", "price_source", "price_missing"
            ] if c in merged.columns], errors="ignore")
            merged = merged.merge(pf, on=["ticker", "as_of"], how="left")

    # 6) flag 보정
    if "market_cap" in merged.columns:
        merged["has_market_cap"] = ~merged["market_cap"].isna()
    if "price_missing" in merged.columns:
        merged["has_price"] = ~merged["price_missing"].fillna(True)
    if "cfo_margin" in merged.columns and "fcf_margin" in merged.columns:
        merged["has_cashflow"] = ~(merged["cfo_margin"].isna() & merged["fcf_margin"].isna())
    if "per" in merged.columns and "pbr" in merged.columns:
        merged["has_valuation"] = ~(merged["per"].isna() & merged["pbr"].isna())

    # 7) exporter 입력용 single-row parquet 저장
    merged_scores = tmp_dir / f"{ticker}_{target_as_of.date()}_merged_scores.parquet"
    merged.to_parquet(merged_scores, index=False)

    # 8) JSON 리포트 생성
    out_report = Path(args.out_report) if args.out_report else Path(f"data/processed/reports/latest/{ticker}.json")
    out_report.parent.mkdir(parents=True, exist_ok=True)

    run([
        py, "-m", "scripts.export_structured_report",
        "--ticker", ticker,
        "--as_of", str(target_as_of.date()),
        "--in_path", str(merged_scores),
        "--out_path", str(out_report)
    ], allow_fail=False)

    # 9) 메타 추가
    payload = json.loads(out_report.read_text(encoding="utf-8"))
    payload.setdefault("meta", {})
    payload["meta"]["generated_at"] = datetime.now().isoformat(timespec="seconds")
    payload["meta"]["refresh_mode"] = "single_ticker_on_demand"
    payload["meta"]["scores_base_path"] = str(scores_path)
    payload["meta"]["price_fetched"] = bool(tmp_price_feat.exists())
    payload["meta"]["market_cap_fetched"] = bool(tmp_mc.exists())
    out_report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] refreshed report: {out_report}")


if __name__ == "__main__":
    main()