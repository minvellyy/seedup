from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from src.common.io import load_parquet, save_parquet


# =========================
# Helpers
# =========================
def _to_ymd(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.strftime("%Y-%m-%d")


def _must_have(df: pd.DataFrame, cols: list[str], where: str):
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise KeyError(f"[ERR] Missing columns at {where}: {miss}\nAvailable: {list(df.columns)}")


def _add_labels_binary(df: pd.DataFrame, horizon: int = 5, neutral_band: float = 0.002) -> pd.DataFrame:
    """
    y=1 if fwd_ret > +neutral_band
    y=0 if fwd_ret < -neutral_band
    y=NaN otherwise (neutral zone)
    """
    df = df.copy()
    df[f"ret_fwd_{horizon}"] = df["close"].shift(-horizon) / df["close"] - 1
    r = df[f"ret_fwd_{horizon}"]
    df[f"y_{horizon}"] = np.where(r > neutral_band, 1, np.where(r < -neutral_band, 0, np.nan))
    return df


def _add_etf_features_one_ticker(g: pd.DataFrame) -> pd.DataFrame:
    """
    ETF는 주식보다 '추세/변동성/거래대금' 성격이 중요
    """
    g = g.sort_values("date").copy()

    # returns
    g["ret_1"] = g["close"].pct_change()
    g["ret_5"] = g["close"].pct_change(5)
    g["ret_20"] = g["close"].pct_change(20)

    # volatility (rolling std of daily returns)
    g["vol_10"] = g["ret_1"].rolling(10).std()
    g["vol_20"] = g["ret_1"].rolling(20).std()

    # moving averages + gaps
    g["ma_5"] = g["close"].rolling(5).mean()
    g["ma_20"] = g["close"].rolling(20).mean()
    g["ma_60"] = g["close"].rolling(60).mean()

    g["ma_gap_5"] = g["close"] / g["ma_5"] - 1
    g["ma_gap_20"] = g["close"] / g["ma_20"] - 1
    g["ma_gap_60"] = g["close"] / g["ma_60"] - 1

    # turnover proxy: 거래량 변화율 (ETF는 거래량이 유동성 신호가 되기 쉬움)
    g["volm_chg_5"] = g["volume"].pct_change(5)
    g["volm_chg_20"] = g["volume"].pct_change(20)

    # price range features (변동폭)
    hl = (g["high"] / g["low"] - 1)
    oc = (g["close"] / g["open"] - 1)
    g["hl_range"] = hl.replace([np.inf, -np.inf], np.nan)
    g["oc_ret"] = oc.replace([np.inf, -np.inf], np.nan)

    return g


def _add_cross_section_ranks(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    날짜 단위 횡단면 랭킹 (ETF는 상대 강도/상대 모멘텀이 특히 중요)
    """
    df = df.copy()
    for c in cols:
        df[f"{c}_rk"] = df.groupby("date")[c].rank(pct=True)
    return df


# =========================
# MAIN
# =========================
def main():
    raw_path = Path("data/raw/etf/ohlcv.parquet")
    if not raw_path.exists():
        raise FileNotFoundError(f"[ERR] Raw ETF file not found: {raw_path}")

    df = load_parquet(raw_path)
    print(f"[OK] Loaded raw ETF: rows={len(df):,} cols={len(df.columns):,}")

    _must_have(df, ["date", "ticker", "open", "high", "low", "close", "volume"], "raw load")

    df = df.copy()
    df["date"] = _to_ymd(df["date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)

    # (A) per-ticker ETF features
    df = (
        df.groupby("ticker", group_keys=False)
          .apply(_add_etf_features_one_ticker)
          .reset_index(drop=True)
    )

    # (B) label: 5d only
    df = (
        df.groupby("ticker", group_keys=False)
          .apply(lambda g: _add_labels_binary(g, horizon=5, neutral_band=0.002))
          .reset_index(drop=True)
    )

    # (C) drop NaNs from rolling/shift + neutral 제거
    df = df.dropna(subset=["y_5"]).dropna().reset_index(drop=True)

    # (D) cross-sectional ranks (ETF에 특히 유효)
    rank_cols = [
        "ret_1", "ret_5", "ret_20",
        "vol_10", "vol_20",
        "ma_gap_5", "ma_gap_20", "ma_gap_60",
        "volm_chg_5", "volm_chg_20",
        "hl_range", "oc_ret",
    ]
    df = _add_cross_section_ranks(df, rank_cols)

    # (E) market regime merge (lag1)
    market_path = Path("data/outputs/predictions/market.parquet")
    if market_path.exists():
        mkt = load_parquet(market_path).copy()
        mkt["date"] = _to_ymd(mkt["date"])
        if "horizon" in mkt.columns:
            mkt = mkt[mkt["horizon"] == 5].copy()

        if "p_market_up" not in mkt.columns and "p_up" in mkt.columns:
            mkt["p_market_up"] = mkt["p_up"]

        mkt = mkt[["date", "p_market_up"]].drop_duplicates("date").sort_values("date")
        # lag1로 누수 방지 (오늘 ETF피처에 "어제" 시장확률만 넣기)
        mkt["p_market_up_lag1"] = mkt["p_market_up"].shift(1)

        df = df.merge(mkt[["date", "p_market_up_lag1"]], on="date", how="left")

        miss = df["p_market_up_lag1"].isna().mean()
        if miss > 0:
            print(f"[WARN] p_market_up_lag1 missing ratio={miss:.4%} -> fill 0.5 (neutral)")
            df["p_market_up_lag1"] = df["p_market_up_lag1"].fillna(0.5)

        # interaction (가볍게 1개만)
        df["ret_5_x_mkt"] = df["ret_5"] * df["p_market_up_lag1"]
    else:
        print(f"[WARN] market predictions not found: {market_path} (skip merge)")

    out_path = Path("data/processed/etf/etf_features.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_parquet(df, out_path)

    print(f"[OK] Saved ETF features: {len(df):,} -> {out_path}")
    print("[INFO] y_5 distribution:", df["y_5"].value_counts().sort_index().to_dict())
    print("[INFO] tickers:", df["ticker"].nunique())


if __name__ == "__main__":
    main()