from __future__ import annotations

from pathlib import Path
import pandas as pd
from tqdm import tqdm
import FinanceDataReader as fdr

from src.common.io import save_parquet


def fetch_one(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    df = fdr.DataReader(ticker, start, end)
    df = df.reset_index().rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = str(ticker).zfill(6)
    return df[["date", "ticker", "open", "high", "low", "close", "volume"]]


def main():
    universe_path = Path("universe/etf_krx_all.csv")
    if not universe_path.exists():
        raise FileNotFoundError("[ERR] ETF universe not found. 먼저 01_make_universe_etf_fdr_all 실행하세요.")

    u = pd.read_csv(universe_path)
    tickers = u["ticker"].astype(str).str.zfill(6).tolist()

    print(f"[OK] Loaded ETF universe | n_tickers={len(tickers):,}")

    start = "2010-01-01"
    end = None

    frames = []
    failed = 0

    for t in tqdm(tickers, desc="Fetching ETF"):
        try:
            df_one = fetch_one(t, start, end)
            if len(df_one) > 0:
                frames.append(df_one)
        except Exception as e:
            failed += 1
            print(f"[WARN] failed ticker={t} err={type(e).__name__}")

    if len(frames) == 0:
        raise RuntimeError("[ERR] No ETF data collected.")

    df_all = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["date", "ticker"])
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )

    out_path = Path("data/raw/etf/ohlcv.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_parquet(df_all, out_path)

    print(f"[OK] Saved ETF OHLCV: {out_path}")
    print(f"[INFO] rows={len(df_all):,} tickers={df_all['ticker'].nunique():,} failed={failed}")


if __name__ == "__main__":
    main()