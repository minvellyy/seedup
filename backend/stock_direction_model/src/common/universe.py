from __future__ import annotations
from pathlib import Path
import pandas as pd

def load_universe_csv(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Universe file not found: {p.resolve()}")
    df = pd.read_csv(p)
    # required: ticker
    if "ticker" not in df.columns:
        raise ValueError("Universe CSV must contain 'ticker' column.")
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df