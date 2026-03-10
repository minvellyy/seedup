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
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(
            f"[ERR] Missing columns at {where}: {missing}\n"
            f"Available columns: {list(df.columns)[:60]}"
        )


def _restore_group_key_if_missing(df_after: pd.DataFrame, key: str) -> pd.DataFrame:
    """
    groupby.apply 이후 pandas 버전에 따라 key 컬럼이 사라질 수 있어 안전 복구.
    - 결과 index가 MultiIndex(ticker, row_index) 형태면 level로부터 복구 가능
    """
    if key in df_after.columns:
        return df_after

    idx = df_after.index
    if isinstance(idx, pd.MultiIndex) and key in idx.names:
        df_after = df_after.reset_index(level=key).reset_index(drop=True)
        return df_after

    # 여기까지 오면 복구 불가 -> 원인 진단용 에러
    raise KeyError(
        f"[ERR] '{key}' disappeared after groupby.apply and cannot be restored.\n"
        f"index type={type(idx)}, index names={getattr(idx, 'names', None)}\n"
        f"columns={list(df_after.columns)[:60]}"
    )


def _add_labels_binary(df: pd.DataFrame, horizon: int = 5, neutral_band: float = 0.002) -> pd.DataFrame:
    df = df.copy()
    df[f"ret_fwd_{horizon}"] = df["close"].shift(-horizon) / df["close"] - 1
    r = df[f"ret_fwd_{horizon}"]
    df[f"y_{horizon}"] = np.where(r > neutral_band, 1, np.where(r < -neutral_band, 0, np.nan))
    return df


def _add_basic_features_one_ticker(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("date").copy()

    g["ret_1"] = g["close"].pct_change()
    g["ret_5"] = g["close"].pct_change(5)
    g["ret_10"] = g["close"].pct_change(10)

    g["vol_5"] = g["ret_1"].rolling(5).std()
    g["vol_10"] = g["ret_1"].rolling(10).std()

    g["ma_5"] = g["close"].rolling(5).mean()
    g["ma_gap_5"] = g["close"] / g["ma_5"] - 1

    g["ma_20"] = g["close"].rolling(20).mean()
    g["ma_gap_20"] = g["close"] / g["ma_20"] - 1

    g["volm_chg_5"] = g["volume"].pct_change(5)
    g["volm_chg_20"] = g["volume"].pct_change(20)

    return g


def _add_cross_section_ranks(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        df[f"{c}_rk"] = df.groupby("date")[c].rank(pct=True)
    return df


def _load_market_lag1(market_pred_path: Path) -> pd.DataFrame:
    if not market_pred_path.exists():
        raise FileNotFoundError(
            f"[ERR] Market predictions not found: {market_pred_path}\n"
            "Hint: 먼저 python -m scripts.03_predict.00_predict_market 실행해서 생성하세요."
        )

    mkt = load_parquet(market_pred_path).copy()
    _must_have(mkt, ["date", "p_market_up"], "market parquet load")

    mkt["date"] = _to_ymd(mkt["date"])
    if "horizon" in mkt.columns:
        mkt = mkt[mkt["horizon"] == 5].copy()

    mkt = (
        mkt[["date", "p_market_up"]]
        .drop_duplicates("date")
        .sort_values("date")
        .reset_index(drop=True)
    )

    mkt["p_market_up_lag1"] = mkt["p_market_up"].shift(1)
    mkt["p_market_up_lag1"] = mkt["p_market_up_lag1"].ffill().fillna(0.5)

    return mkt[["date", "p_market_up_lag1"]]


# =========================
# MAIN
# =========================
def main():
    raw_path = Path("data/raw/stock/ohlcv.parquet")
    if not raw_path.exists():
        raise FileNotFoundError(f"[ERR] Raw stock file not found: {raw_path}")

    df = load_parquet(raw_path)
    print(f"[OK] Loaded raw stock: rows={len(df):,} cols={len(df.columns):,}")
    _must_have(df, ["date", "ticker", "open", "high", "low", "close", "volume"], "raw parquet load")

    # normalize
    df["date"] = _to_ymd(df["date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)

    # (A) per-ticker time-series features
    _must_have(df, ["ticker"], "before per-ticker feature groupby")
    df = df.groupby("ticker", group_keys=False).apply(_add_basic_features_one_ticker)
    df = _restore_group_key_if_missing(df, "ticker")
    # (apply 후 인덱스/정렬 정리)
    df = df.reset_index(drop=True)

    # (B) label: horizon=5 only
    _must_have(df, ["ticker"], "before label groupby")
    df = df.groupby("ticker", group_keys=False).apply(lambda g: _add_labels_binary(g, horizon=5, neutral_band=0.002))
    df = _restore_group_key_if_missing(df, "ticker")
    df = df.reset_index(drop=True)

    # (C) drop neutral + rolling/shift NaNs
    df = df.dropna(subset=["y_5"]).dropna().reset_index(drop=True)

    # (D) cross-sectional ranks
    rank_cols = [
        "ret_1", "ret_5", "ret_10",
        "vol_5", "vol_10",
        "ma_gap_5", "ma_gap_20",
        "volm_chg_5", "volm_chg_20",
    ]
    df = _add_cross_section_ranks(df, rank_cols)

    # === MARKET REGIME MERGE (lag1) ===
    mkt_lag1 = _load_market_lag1(Path("data/outputs/predictions/market.parquet"))
    df = df.merge(mkt_lag1, on="date", how="left")

    miss = df["p_market_up_lag1"].isna().mean()
    if miss > 0:
        print(f"[WARN] p_market_up_lag1 missing ratio={miss:.4%} -> fill 0.5 (neutral)")
        df["p_market_up_lag1"] = df["p_market_up_lag1"].fillna(0.5)

    # interaction
    df["ret_5_x_mkt_lag1"] = df["ret_5"] * df["p_market_up_lag1"]

    out_path = Path("data/processed/stock/stock_features.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_parquet(df, out_path)

    print(f"[OK] Saved stock features: {len(df):,} -> {out_path}")
    print("[INFO] y_5 distribution:", df["y_5"].value_counts().sort_index().to_dict())
    print("[INFO] tickers:", df["ticker"].nunique())


if __name__ == "__main__":
    main()