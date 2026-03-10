from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from src.config import SETTINGS
from src.dart_client import fetch_core_financials, REPRT
from src.utils import ensure_dir


def call_with_retry(fn, retries: int, sleep_sec: float = 0.5):
    last = None
    for _ in range(max(1, retries)):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(sleep_sec)
    raise last


def main(
    year: int,
    reprt_key: str = "FY",
    universe_path: str = "data/processed/universe.parquet",
    start_idx: int = 0,
    end_idx: int = -1,
    sleep: float = 0.15,
    retries: int = 3,
    smoke: bool = False,
    out_path: str | None = None,
):
    base = Path(SETTINGS.data_dir)
    raw = ensure_dir(base / "raw")

    # 1) universe 로드
    uni_path = Path(universe_path)
    if not uni_path.exists():
        raise FileNotFoundError(f"universe not found: {uni_path}")

    uni = pd.read_parquet(uni_path).copy()
    if "ticker" not in uni.columns or "corp_code" not in uni.columns:
        raise ValueError("universe must include columns: ticker, corp_code")

    uni["ticker"] = uni["ticker"].astype(str).str.zfill(6)

    # 2) smoke 옵션(테스트)
    if smoke:
        SMOKE_TICKERS = ["005930", "000660", "035420", "051910", "068270"]
        uni = uni[uni["ticker"].isin(SMOKE_TICKERS)].copy()
        print("SMOKE tickers:", uni["ticker"].tolist(), "rows=", len(uni))

    # 3) 배치 슬라이싱
    n = len(uni)
    s = max(0, int(start_idx))
    e = n if end_idx is None or int(end_idx) < 0 else min(int(end_idx), n)
    if s >= e:
        raise ValueError(f"invalid range: start_idx={s}, end_idx={e}, n={n}")
    uni = uni.iloc[s:e].reset_index(drop=True)
    print(f"[INFO] universe={universe_path} total={n} batch_range={s}:{e} batch_rows={len(uni)}")

    # 4) DART 호출
    reprt_code = REPRT[reprt_key]
    out_rows = []

    for _, row in tqdm(uni.iterrows(), total=len(uni)):
        corp_code = row["corp_code"]
        ticker = row["ticker"]

        try:
            df = call_with_retry(
                lambda: fetch_core_financials(corp_code, year, reprt_code),
                retries=retries
            )
        except Exception as ex:
            # 실패는 스킵(필요하면 실패로그 저장으로 확장 가능)
            # print(f"[WARN] fail ticker={ticker} corp_code={corp_code}: {ex}")
            time.sleep(sleep)
            continue

        if df is None or df.empty:
            time.sleep(sleep)
            continue

        df["ticker"] = ticker
        out_rows.append(df)

        time.sleep(sleep)

    if not out_rows:
        print("[WARN] No data fetched for this batch.")
        return

    out = pd.concat(out_rows, ignore_index=True)

    # 5) 저장 파일명 (배치면 range를 이름에 넣어 충돌 방지)
    if out_path:
        out_p = Path(out_path)
    else:
        out_p = raw / f"dart_core_{year}_{reprt_key}_{SETTINGS.fs_div}_{s}_{e}.parquet"

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_p, index=False)
    print(f"[OK] Saved raw core financials: {out_p} rows={len(out)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--reprt_key", type=str, default="FY", choices=["Q1", "H1", "Q3", "FY"])
    ap.add_argument("--universe_path", type=str, default="data/processed/universe.parquet")
    ap.add_argument("--start_idx", type=int, default=0)
    ap.add_argument("--end_idx", type=int, default=-1)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out_path", type=str, default=None)
    args = ap.parse_args()

    main(
        year=args.year,
        reprt_key=args.reprt_key,
        universe_path=args.universe_path,
        start_idx=args.start_idx,
        end_idx=args.end_idx,
        sleep=args.sleep,
        retries=args.retries,
        smoke=args.smoke,
        out_path=args.out_path,
    )