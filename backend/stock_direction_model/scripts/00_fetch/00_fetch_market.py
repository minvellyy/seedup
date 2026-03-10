from __future__ import annotations
from pathlib import Path
import pandas as pd
from datetime import datetime

import FinanceDataReader as fdr

from src.common.io import save_parquet

# KOSPI/KOSDAQ 지수 (FDR 심볼)
MARKET_SYMBOLS = {
    "KOSPI": "KS11",
    "KOSDAQ": "KQ11",
}

def fetch_index(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    df = fdr.DataReader(symbol, start, end)
    # FDR index df: Open High Low Close Volume Change
    df = df.reset_index().rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[["date", "open", "high", "low", "close", "volume"]]
    return df

def main():
    start = "2010-01-01"
    end = None

    out_dir = Path("data/raw/market")
    for name, sym in MARKET_SYMBOLS.items():
        df = fetch_index(sym, start, end)
        df["ticker"] = name  # KOSPI, KOSDAQ
        # 표준 스키마로: date,ticker,open,high,low,close,volume
        df = df[["date", "ticker", "open", "high", "low", "close", "volume"]]
        save_parquet(df, out_dir / f"{name.lower()}_ohlcv.parquet")
        print(f"[OK] Saved {name}: rows={len(df)}")

if __name__ == "__main__":
    main()