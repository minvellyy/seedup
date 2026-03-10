from __future__ import annotations
from pathlib import Path
import pandas as pd

def ensure_dir(p: Path) -> None:
    """Create directory if not exists."""
    p.mkdir(parents=True, exist_ok=True)

def save_parquet(df: pd.DataFrame, path: Path) -> None:
    """Save dataframe to parquet (requires pyarrow or fastparquet)."""
    ensure_dir(path.parent)
    df.to_parquet(path, index=False)

def load_parquet(path: Path) -> pd.DataFrame:
    """Load dataframe from parquet."""
    return pd.read_parquet(path)