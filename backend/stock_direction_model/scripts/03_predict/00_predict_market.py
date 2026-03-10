from __future__ import annotations
from pathlib import Path
import pandas as pd
import joblib
import json

from src.common.io import load_parquet, save_parquet


def regime_from_p(p: float, up_th: float = 0.55, down_th: float = 0.45) -> str:
    if p >= up_th:
        return "UP"
    if p <= down_th:
        return "DOWN"
    return "NEUTRAL"


def main():
    # ✅ 입력 피처 로드
    df = load_parquet(Path("data/processed/market/kospi_features.parquet")).sort_values("date").copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # ✅ 모델/메타 로드 (방금 학습한 결과 기준)
    model_path = Path("data/outputs/models/market_bin_y_5.joblib")
    meta_path = Path("data/outputs/models/market_bin_y_5.meta.json")

    model = joblib.load(model_path)

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    feat_cols = meta["features"]

    # ✅ 방어: y_*, ret_fwd_* 같은 라벨/미래정보 계열이 섞이면 제거
    feat_cols = [c for c in feat_cols if not c.startswith("y_") and not c.startswith("ret_fwd_")]

    # ✅ 예측
    p_up = model.predict_proba(df[feat_cols])[:, 1]

    out = df[["date"]].copy()
    out["ticker"] = "KOSPI"
    out["asset_type"] = "market"
    out["horizon"] = 5
    out["p_market_up"] = p_up
    out["regime"] = [regime_from_p(p) for p in p_up]

    save_parquet(out, Path("data/outputs/predictions/market.parquet"))
    print(f"[OK] Saved market predictions(BIN): rows={len(out)} -> data/outputs/predictions/market.parquet")


if __name__ == "__main__":
    main()