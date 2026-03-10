from __future__ import annotations
from pathlib import Path
import pandas as pd
from tqdm import tqdm
import FinanceDataReader as fdr

from src.common.universe import load_universe_csv
from src.common.update import infer_start_date, append_dedup_save
from src.common.io import load_parquet

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

def main(buffer_days: int = 45):
    universe_path = "universe/etf_korea_list.csv"
    out_path = Path("data/raw/etf/ohlcv.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    u = load_universe_csv(universe_path)
    tickers = u["ticker"].tolist()

    if out_path.exists():
        existing = load_parquet(out_path)
        start = infer_start_date(existing, "date", buffer_days)
    else:
        existing = pd.DataFrame()
        start = "2010-01-01"

    frames = []
    for t in tqdm(tickers, desc=f"Updating ETF from {start}"):
        try:
            frames.append(fetch_one(t, start=start))
        except Exception as e:
            print(f"[WARN] failed ticker={t} err={e}")

    new_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["date", "ticker"])
    merged = append_dedup_save(out_path, new_df, key_cols=["date", "ticker"])
    print(f"[OK] ETF updated: start={start} rows={len(merged)} tickers={merged['ticker'].nunique()} last={merged['date'].max()}")

if __name__ == "__main__":
    main()