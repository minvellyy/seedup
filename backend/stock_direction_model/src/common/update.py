from __future__ import annotations
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta

from src.common.io import load_parquet, save_parquet

def infer_start_date(existing: pd.DataFrame, date_col: str, buffer_days: int) -> str:
    if existing.empty:
        # 초기에는 넉넉히 가져오게(필요하면 바꿔)
        return "2010-01-01"
    last = pd.to_datetime(existing[date_col]).max()
    start = (last - timedelta(days=buffer_days)).strftime("%Y-%m-%d")
    return start

def append_dedup_save(existing_path: Path, new_df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    if existing_path.exists():
        old = load_parquet(existing_path)
        merged = pd.concat([old, new_df], ignore_index=True)
    else:
        merged = new_df.copy()

    merged = merged.drop_duplicates(subset=key_cols, keep="last")
    merged = merged.sort_values(key_cols)
    save_parquet(merged, existing_path)
    return merged