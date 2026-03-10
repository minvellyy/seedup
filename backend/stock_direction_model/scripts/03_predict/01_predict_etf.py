# scripts/03_predict/01_predict_etf.py
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from src.common.io import load_parquet, save_parquet


# =========================
# Config
# =========================
HORIZON = 5
ALPHA = 0.3  # "약한 레짐 필터" 강도 (0.2~0.4 권장)

ETF_FEATURE_PATH = Path("data/processed/etf/etf_features.parquet")
MODEL_PATH = Path("data/outputs/models/etf_lgbm_bin_y_5.joblib")
MARKET_PRED_PATH = Path("data/outputs/predictions/market.parquet")
OUT_PATH = Path("data/outputs/predictions/etf.parquet")


# =========================
# Soft Gate (선택지 2)
# =========================
def soft_gate_choice2(p_etf_up: np.ndarray, p_market_up: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """
    선택지2 (Soft Gate)
    p_adj = 0.5 + (p_etf-0.5) * (1 + alpha * m)
    m = 2*(p_market-0.5) in [-1, +1]
    """
    s = p_etf_up - 0.5
    m = 2.0 * (p_market_up - 0.5)
    p_adj = 0.5 + s * (1.0 + alpha * m)
    return np.clip(p_adj, 0.001, 0.999)


def _to_ymd(x: pd.Series) -> pd.Series:
    return pd.to_datetime(x).dt.strftime("%Y-%m-%d")


def main():
    # 1) ETF feature load
    if not ETF_FEATURE_PATH.exists():
        raise FileNotFoundError(
            f"[ERR] ETF features not found: {ETF_FEATURE_PATH}\n"
            f"Hint: 먼저 python -m scripts.01_features.01_build_etf_features 실행해서 parquet를 생성하세요."
        )

    df = load_parquet(ETF_FEATURE_PATH).copy()
    must = {"date", "ticker"}
    missing = sorted(list(must - set(df.columns)))
    if missing:
        raise KeyError(f"[ERR] ETF features missing required cols: {missing}")

    df["date"] = _to_ymd(df["date"])
    df["ticker"] = df["ticker"].astype(str)

    print(f"[OK] Loaded ETF features: {ETF_FEATURE_PATH} | rows={len(df):,} cols={len(df.columns):,}")

    # 2) Load model pack
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"[ERR] ETF model not found: {MODEL_PATH}")

    pack = joblib.load(MODEL_PATH)
    model = pack["model"]
    feat_cols = pack["feature_cols"]

    # 3) feature mismatch 체크
    miss_feat = [c for c in feat_cols if c not in df.columns]
    if miss_feat:
        raise KeyError(
            f"[ERR] Missing feature columns in ETF df: {miss_feat}\n"
            f"Hint: train에 쓴 etf_features.parquet와 현재 predict에 쓰는 파일이 다른 버전일 수 있습니다."
        )

    # 4) Predict p_up
    p_up = model.predict_proba(df[feat_cols])[:, 1]

    out = df[["date", "ticker"]].copy()
    out["asset_type"] = "etf"
    out["horizon"] = HORIZON
    out["p_up"] = p_up

    # 5) Market soft-gate 적용 (선택지2)
    if MARKET_PRED_PATH.exists():
        mkt = load_parquet(MARKET_PRED_PATH).copy()
        if "date" not in mkt.columns:
            raise KeyError("[ERR] market.parquet must have 'date' column")

        mkt["date"] = _to_ymd(mkt["date"])

        # market은 horizon=5만 사용
        if "horizon" in mkt.columns:
            mkt = mkt[mkt["horizon"] == 5].copy()

        # 스키마 대응: p_market_up 없으면 p_up를 사용
        if "p_market_up" not in mkt.columns and "p_up" in mkt.columns:
            mkt["p_market_up"] = mkt["p_up"]

        if "p_market_up" not in mkt.columns:
            raise KeyError("[ERR] market.parquet must have 'p_market_up' (or 'p_up') column")

        keep_cols = ["date", "p_market_up"]
        if "regime" in mkt.columns:
            keep_cols.append("regime")

        mkt = mkt[keep_cols].drop_duplicates("date")
        out = out.merge(mkt, on="date", how="left")

        # market 없는 날짜는 p_adj = p_up
        has_m = out["p_market_up"].notna().to_numpy()
        p_adj = out["p_up"].to_numpy().copy()
        if has_m.any():
            p_adj[has_m] = soft_gate_choice2(
                p_etf_up=out.loc[has_m, "p_up"].to_numpy(),
                p_market_up=out.loc[has_m, "p_market_up"].to_numpy(),
                alpha=ALPHA,
            )
        out["p_adj"] = p_adj
    else:
        out["p_adj"] = out["p_up"]

    # 6) Save
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_parquet(out, OUT_PATH)
    print(f"[OK] Saved ETF predictions: rows={len(out):,} -> {OUT_PATH}")


if __name__ == "__main__":
    main()