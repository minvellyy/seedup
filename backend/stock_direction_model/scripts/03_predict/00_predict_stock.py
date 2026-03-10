from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from src.common.io import load_parquet, save_parquet


# =========================
# Config (너가 선택한 정책)
# =========================
HORIZON = 5
ALPHA = 0.3  # “약한 레짐 필터” 강도 (0.2~0.4 권장)


# =========================
# Paths
# =========================
# ✅ 최신 파이프라인 기준: stock_features.parquet 를 1순위로!
PANEL_CANDIDATES = [
    Path("data/processed/stock/stock_features.parquet"),   # ✅ NEW (정답)
    # (레거시 후보들 - 혹시 남아있으면 fallback)
    Path("data/processed/panel_features_labels.parquet"),
    Path("data/processed/panel_features.parquet"),
    Path("data/processed/stocks/panel_features_labels.parquet"),
    Path("data/processed/panel.parquet"),
]

MODEL_PATH = Path("data/outputs/models/stock_lgbm_bin_y_5.joblib")
MARKET_PRED_PATH = Path("data/outputs/predictions/market.parquet")
OUT_PATH = Path("data/outputs/predictions/stock.parquet")


def _find_first_existing(paths: list[Path]) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def soft_gate_choice2(p_stock_up: np.ndarray, p_market_up: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """
    ✅ 선택지2 (Soft Gate)
    p_adj = 0.5 + (p_stock-0.5) * (1 + alpha * m)
    m = 2*(p_market-0.5) in [-1, +1]
    """
    s = p_stock_up - 0.5
    m = 2.0 * (p_market_up - 0.5)
    p_adj = 0.5 + s * (1.0 + alpha * m)
    return np.clip(p_adj, 0.001, 0.999)


def main():
    # 1) 패널(=stock features) 로드
    panel_path = _find_first_existing(PANEL_CANDIDATES)
    if not panel_path.exists():
        raise FileNotFoundError(
            f"[ERR] Stock panel parquet not found.\n"
            f"Checked: {', '.join(str(p) for p in PANEL_CANDIDATES)}"
        )

    df = load_parquet(panel_path)
    must = {"date", "ticker"}
    missing = list(must - set(df.columns))
    if missing:
        raise KeyError(
            f"[ERR] panel missing required columns: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)

    # 2) 모델 로드 (pack 형태: {"model":..., "feature_cols":...})
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"[ERR] model not found: {MODEL_PATH}")

    pack = joblib.load(MODEL_PATH)
    model = pack["model"]
    feat_cols = pack["feature_cols"]

    # 3) feature mismatch 방지: 없는 컬럼 체크
    missing_feats = [c for c in feat_cols if c not in df.columns]
    if missing_feats:
        raise KeyError(
            f"[ERR] Missing feature columns in df: {missing_feats}\n"
            f"Hint: build_stock_features 결과 parquet와 train에 사용된 feature set이 달라졌을 가능성이 큽니다.\n"
            f"      1) 다시 build_stock_features 실행\n"
            f"      2) 다시 train_stock 실행\n"
        )

    # 4) 주식 확률 예측
    p_up = model.predict_proba(df[feat_cols])[:, 1]

    out = df[["date", "ticker"]].copy()
    out["asset_type"] = "stock"
    out["horizon"] = HORIZON
    out["p_up"] = p_up

    # 5) (옵션) market soft gate 적용 (선택지2)
    out["p_adj"] = out["p_up"]  # 기본값

    if MARKET_PRED_PATH.exists():
        mkt = load_parquet(MARKET_PRED_PATH).copy()
        if "date" not in mkt.columns:
            raise KeyError("[ERR] market.parquet must have 'date' column")

        mkt["date"] = pd.to_datetime(mkt["date"]).dt.strftime("%Y-%m-%d")

        # market pred는 horizon=5만 사용(안전)
        if "horizon" in mkt.columns:
            mkt = mkt[mkt["horizon"] == 5].copy()

        # 컬럼 호환: p_market_up 없고 p_up 있으면 대체
        if "p_market_up" not in mkt.columns:
            if "p_up" in mkt.columns:
                mkt["p_market_up"] = mkt["p_up"]
            else:
                raise KeyError("[ERR] market.parquet must have 'p_market_up' or 'p_up' column")

        mkt = mkt[["date", "p_market_up"]].drop_duplicates("date")

        out = out.merge(mkt, on="date", how="left")

        has_m = out["p_market_up"].notna().to_numpy()
        if has_m.any():
            out.loc[has_m, "p_adj"] = soft_gate_choice2(
                p_stock_up=out.loc[has_m, "p_up"].to_numpy(),
                p_market_up=out.loc[has_m, "p_market_up"].to_numpy(),
                alpha=ALPHA,
            )

        # market 없는 날짜는 그대로 p_up 유지
        out = out.drop(columns=["p_market_up"], errors="ignore")

    # 6) 저장
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_parquet(out, OUT_PATH)
    print(f"[OK] Loaded stock features: {panel_path} | rows={len(df):,} cols={len(df.columns):,}")
    print(f"[OK] Saved stock predictions: rows={len(out):,} -> {OUT_PATH}")


if __name__ == "__main__":
    main()