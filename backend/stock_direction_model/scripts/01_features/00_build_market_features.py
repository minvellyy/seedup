from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

from src.common.io import load_parquet, save_parquet


def add_market_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").copy()

    # returns
    df["ret_1"] = df["close"].pct_change()
    df["ret_5"] = df["close"].pct_change(5)

    # vol (5d only)
    df["vol_5"] = df["ret_1"].rolling(5).std()

    # moving averages
    df["ma_5"] = df["close"].rolling(5).mean()
    df["ma_gap_5"] = df["close"] / df["ma_5"] - 1

    df["ma_20"] = df["close"].rolling(20).mean()
    df["ma_gap_20"] = df["close"] / df["ma_20"] - 1

    # volume changes
    df["volm_chg_5"] = df["volume"].pct_change(5)
    df["volm_chg_20"] = df["volume"].pct_change(20)

    return df


def add_label_binary(df: pd.DataFrame, horizon: int, neutral_band: float = 0.002) -> pd.DataFrame:
    """
    Binary label with neutral drop:
      y=1 if ret_fwd > +neutral_band
      y=0 if ret_fwd < -neutral_band
      y=NaN otherwise (neutral zone) -> removed from training
    """
    df = df.copy()
    df[f"ret_fwd_{horizon}"] = df["close"].shift(-horizon) / df["close"] - 1
    r = df[f"ret_fwd_{horizon}"]

    df[f"y_{horizon}"] = np.where(r > neutral_band, 1,
                          np.where(r < -neutral_band, 0, np.nan))
    return df


def main():
    path = Path("data/raw/market/kospi_ohlcv.parquet")
    df = load_parquet(path)

    df = add_market_features(df)

    # ✅ y_5만 생성 (10일 레짐/라벨 완전 제거)
    df = add_label_binary(df, horizon=5, neutral_band=0.002)

    # ✅ 혹시 남아있을 수 있는 y_10/ret_fwd_10 같은 컬럼 방어적으로 제거
    drop_cols = [c for c in df.columns if c in ("y_10", "ret_fwd_10", "ret_10", "vol_10")]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    # rolling/shift 결측 + 중립 제거
    df = df.dropna(subset=["y_5"]).dropna().reset_index(drop=True)

    out_path = Path("data/processed/market/kospi_features.parquet")
    save_parquet(df, out_path)

    print("[OK] Market features saved:", len(df), "->", out_path)
    vc = df["y_5"].value_counts().sort_index()
    print("[INFO] y_5 counts:", vc.to_dict())


if __name__ == "__main__":
    main()