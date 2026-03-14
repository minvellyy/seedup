"""
현금흐름표(CF) 데이터 수집 및 기존 norm 파일 패칭 스크립트

Usage:
    python -m scripts.fetch_and_patch_cf --target_year 2024 --base_year 2023

동작:
1. universe 에서 모든 ticker/corp_code 읽기
2. fnlttSinglAcntAll.json 으로 CF 데이터 수집 (FY 연간만)
3. 영업활동현금흐름(cfo), 유형자산의 취득(capex) 추출
4. 기존 fin_core_norm_{year}_FY_{fs_div}.parquet 에 cfo/capex 컬럼 채움
5. 재저장 → 이후 build_scores.py 실행시 cashflow_score 자동 계산
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.config import SETTINGS
from src.dart_client import fetch_cashflow_financials, REPRT
from src.utils import ensure_dir

# CF에서 추출할 계정명 패턴 (normalize.py MAP과 동일)
CFO_PATTERNS = ["영업활동현금흐름", "영업활동 현금흐름", "영업활동으로인한현금흐름", "영업활동으로 인한 현금흐름"]
CAPEX_PATTERNS = ["유형자산의취득", "유형자산 취득", "유형자산의 취득"]


def _to_number(x) -> float:
    if x is None:
        return np.nan
    s = str(x).replace(",", "").strip()
    if s in ("", "-", "NaN", "nan"):
        return np.nan
    try:
        return float(s)
    except Exception:
        return np.nan


def extract_cf_from_all_df(df: pd.DataFrame) -> dict:
    """finstate_all response DataFrame에서 CFO, Capex 추출."""
    if df is None or df.empty or "account_nm" not in df.columns:
        return {}

    cf = df[df["sj_div"] == "CF"] if "sj_div" in df.columns else df
    if cf.empty or "account_nm" not in cf.columns:
        return {}

    def find_amount(patterns):
        for p in patterns:
            mask = cf["account_nm"].str.contains(p, regex=False, na=False)
            rows = cf[mask]
            if not rows.empty:
                val = _to_number(rows.iloc[0]["thstrm_amount"])
                if not np.isnan(val):
                    return val
        return np.nan

    return {
        "cfo": find_amount(CFO_PATTERNS),
        "capex": find_amount(CAPEX_PATTERNS),
    }


def call_with_retry(fn, retries: int = 3, sleep_sec: float = 0.5):
    last = None
    for _ in range(max(1, retries)):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(sleep_sec)
    raise last


def main(
    target_year: int,
    base_year: int,
    universe_path: str = "data/processed/universe_k200_k150_fixed.parquet",
    sleep: float = 0.3,
    retries: int = 3,
    smoke: bool = False,
):
    base = Path(SETTINGS.data_dir)
    processed = ensure_dir(base / "processed")

    # 1) universe 로드
    uni_path = Path(universe_path)
    if not uni_path.exists():
        # fallback to alternatives
        for alt in ["data/processed/universe.parquet", "data/processed/universe_k200_k150.parquet"]:
            alt_p = Path(alt)
            if alt_p.exists():
                uni_path = alt_p
                break
    if not uni_path.exists():
        raise FileNotFoundError(f"universe not found: {universe_path}")

    uni = pd.read_parquet(uni_path).copy()
    uni["ticker"] = uni["ticker"].astype(str).str.zfill(6)
    print(f"[INFO] universe: {len(uni)} tickers from {uni_path}")

    if smoke:
        SMOKE = ["005930", "000660", "035420", "051910", "068270"]
        uni = uni[uni["ticker"].isin(SMOKE)].copy()
        print(f"[SMOKE] tickers: {uni['ticker'].tolist()}")

    # 2) 연도별 CF 데이터 수집 (FY 연간만)
    reprt_code = REPRT["FY"]
    years = sorted(set([base_year, target_year]))

    # {(ticker, year): {cfo, capex}}
    cf_lookup: dict[tuple, dict] = {}

    print(f"\n[STEP 1] Fetching CF data for years={years}, n={len(uni)} tickers...")
    for _, row in tqdm(uni.iterrows(), total=len(uni)):
        corp_code = row["corp_code"]
        ticker = row["ticker"]

        for year in years:
            try:
                df_all = call_with_retry(
                    lambda: fetch_cashflow_financials(corp_code, year, reprt_code),
                    retries=retries,
                )
            except Exception as ex:
                print(f"[WARN] ticker={ticker} year={year}: {ex}")
                time.sleep(sleep)
                continue

            if df_all is None or df_all.empty:
                time.sleep(sleep)
                continue

            cf_vals = extract_cf_from_all_df(df_all)
            if not np.isnan(cf_vals.get("cfo", np.nan)) or not np.isnan(cf_vals.get("capex", np.nan)):
                cf_lookup[(ticker, year)] = cf_vals

            time.sleep(sleep)

    print(f"[INFO] CF data collected for {len(cf_lookup)} (ticker, year) pairs")
    if not cf_lookup:
        print("[WARN] No CF data found. Check DART API key and account names.")
        return

    # 3) 기존 norm FY 파일에 cfo/capex 패칭
    print(f"\n[STEP 2] Patching existing norm files with CF data...")
    for year in years:
        norm_path = processed / f"fin_core_norm_{year}_FY_{SETTINGS.fs_div}.parquet"
        if not norm_path.exists():
            print(f"[SKIP] norm file not found: {norm_path}")
            continue

        norm = pd.read_parquet(norm_path)
        norm["ticker"] = norm["ticker"].astype(str).str.zfill(6)

        if "cfo" not in norm.columns:
            norm["cfo"] = np.nan
        if "capex" not in norm.columns:
            norm["capex"] = np.nan

        patched = 0
        for idx, row in norm.iterrows():
            key = (row["ticker"], year)
            if key in cf_lookup:
                vals = cf_lookup[key]
                if not np.isnan(vals.get("cfo", np.nan)):
                    norm.at[idx, "cfo"] = vals["cfo"]
                    patched += 1
                if not np.isnan(vals.get("capex", np.nan)):
                    norm.at[idx, "capex"] = vals["capex"]

        norm.to_parquet(norm_path, index=False)
        print(f"[OK] Patched {norm_path.name} - updated cfo/capex for {patched}/{len(norm)} rows")

    print("\n[DONE] CF data patched. Run build_scores.py to rebuild cashflow_score.")
    print("       python -m scripts.build_scores --target_year 2024 --base_year 2023 --with_market_cap --with_price --out_tag with_mc_with_price")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--base_year", type=int, default=2023)
    ap.add_argument("--universe_path", type=str, default="data/processed/universe_k200_k150_fixed.parquet")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--smoke", action="store_true", help="삼성전자 등 5개만 테스트")
    args = ap.parse_args()

    main(
        target_year=args.target_year,
        base_year=args.base_year,
        universe_path=args.universe_path,
        sleep=args.sleep,
        retries=args.retries,
        smoke=args.smoke,
    )
