from __future__ import annotations
from pathlib import Path
import pandas as pd
import FinanceDataReader as fdr

from src.common.update import infer_start_date, append_dedup_save
from src.common.io import load_parquet

MARKET_SYMBOLS = {
    "KOSPI": "KS11",
    "KOSDAQ": "KQ11",
}

def fetch_index(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    df = fdr.DataReader(symbol, start, end)
    df = df.reset_index().rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[["date", "open", "high", "low", "close", "volume"]]

def main(buffer_days: int = 45):
    out_dir = Path("data/raw/market")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, sym in MARKET_SYMBOLS.items():
        path = out_dir / f"{name.lower()}_ohlcv.parquet"

        if path.exists():
            existing = load_parquet(path)
            start = infer_start_date(existing, "date", buffer_days)
        else:
            existing = pd.DataFrame()
            start = "2010-01-01"

        new_df = fetch_index(sym, start=start)
        new_df["ticker"] = name
        new_df = new_df[["date", "ticker", "open", "high", "low", "close", "volume"]]

        merged = append_dedup_save(path, new_df, key_cols=["date", "ticker"])
        print(f"[OK] {name} updated: start={start} rows={len(merged)} last={merged['date'].max()}")

if __name__ == "__main__":
    main()