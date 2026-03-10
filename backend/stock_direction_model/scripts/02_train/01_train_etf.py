# scripts/02_train/01_train_etf.py
from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score
import joblib

# LightGBM
try:
    from lightgbm import LGBMClassifier
except ImportError as e:
    raise ImportError(
        "lightgbm 패키지가 없습니다. 아래로 설치하세요:\n"
        "  pip install lightgbm\n"
    ) from e


# =========================
# Paths
# =========================
PROCESSED_CANDIDATES = [
    Path("data/processed/etf/etf_features.parquet"),   # ✅ 너가 만든 ETF 피처
    # (혹시 과거 파일명이 달랐을 때 대비)
    Path("data/processed/etf_features.parquet"),
]

MODEL_DIR = Path("data/outputs/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# =========================
# Utils
# =========================
def _find_first_existing(paths: list[Path]) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def load_etf_panel() -> pd.DataFrame:
    path = _find_first_existing(PROCESSED_CANDIDATES)
    if not path.exists():
        raise FileNotFoundError(
            f"[ERR] ETF feature parquet not found.\n"
            f"Checked: {', '.join(str(p) for p in PROCESSED_CANDIDATES)}\n"
            f"Hint: 먼저 python -m scripts.01_features.01_build_etf_features 실행해서 parquet를 생성하세요."
        )
    df = pd.read_parquet(path)
    must = {"date", "ticker"}
    missing = list(must - set(df.columns))
    if missing:
        raise KeyError(f"[ERR] Required columns missing: {missing}")
    print(f"[OK] Loaded ETF panel: {path} | rows={len(df):,} cols={len(df.columns):,}")
    return df


def build_feature_matrix(
    df: pd.DataFrame,
    label_col: str,
    drop_cols_extra: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series, dict]:
    """
    - pooled(전체 ETF 합쳐서) LGBM 학습
    - label_col(y_5)만 사용
    - ret_fwd_* / date / ticker / label / (기타 지정) 제거
    - 결측/상수열 제거
    """
    drop_cols_extra = drop_cols_extra or []

    if label_col not in df.columns:
        raise KeyError(f"[ERR] label_col={label_col} not found in df.columns")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "ticker"]).reset_index(drop=True)

    # ✅ 누수 방지: 라벨/식별자/미래수익률/다른 y_* 제거
    auto_drop = {label_col, "date", "ticker"}
    for c in df.columns:
        if c.startswith("ret_fwd_"):
            auto_drop.add(c)
    for c in df.columns:
        if c.startswith("y_") and c != label_col:
            auto_drop.add(c)
    for c in drop_cols_extra:
        auto_drop.add(c)

    feat_candidates = []
    for c in df.columns:
        if c in auto_drop:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            feat_candidates.append(c)

    X = df[feat_candidates].copy()
    y = df[label_col].copy()

    # 라벨 결측 제거(중립 제거가 이미 들어있을 수 있음)
    keep = y.notna()
    X = X.loc[keep].reset_index(drop=True)
    y = y.loc[keep].astype(int).reset_index(drop=True)

    removed = {"missing_cols": [], "constant_cols": []}

    # 결측 포함 컬럼 제거(안전 우선)
    missing_cols = [c for c in X.columns if X[c].isna().any()]
    if missing_cols:
        removed["missing_cols"] = missing_cols
        X = X.drop(columns=missing_cols)

    # 상수열 제거
    constant_cols = [c for c in X.columns if X[c].nunique(dropna=True) <= 1]
    if constant_cols:
        removed["constant_cols"] = constant_cols
        X = X.drop(columns=constant_cols)

    info = {
        "label_col": label_col,
        "n_rows": int(len(X)),
        "n_features": int(X.shape[1]),
        "features": list(X.columns),
        "removed": removed,
    }
    return X, y, info


def _timeseries_split_by_date(df_kept: pd.DataFrame, n_splits: int = 5):
    """
    ✅ 패널 데이터에서 “날짜 단위” 시계열 CV
    - 같은 날짜의 여러 ETF 행은 함께 train/valid로 묶임
    """
    dates = pd.to_datetime(df_kept["date"]).reset_index(drop=True)
    uniq_dates = pd.Index(sorted(dates.unique()))

    tscv = TimeSeriesSplit(n_splits=n_splits)
    for tr_d_idx, va_d_idx in tscv.split(uniq_dates):
        tr_dates = set(uniq_dates[tr_d_idx])
        va_dates = set(uniq_dates[va_d_idx])

        tr_mask = dates.isin(tr_dates).to_numpy()
        va_mask = dates.isin(va_dates).to_numpy()
        yield np.where(tr_mask)[0], np.where(va_mask)[0]


def train_one_etf_lgbm(df: pd.DataFrame, label_col: str, model_path: str) -> dict:
    X, y, info = build_feature_matrix(df, label_col=label_col)

    # keep된 df(날짜 split용) 만들기
    df_kept = df.copy()
    df_kept["date"] = pd.to_datetime(df_kept["date"])
    keep = df_kept[label_col].notna()
    df_kept = df_kept.loc[keep].reset_index(drop=True)

    model = LGBMClassifier(
        n_estimators=1200,
        learning_rate=0.02,
        num_leaves=63,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
        # 로그 overhead 줄이고 싶으면 아래를 켜도 됨(선택)
        # force_col_wise=True,
    )

    aucs = []
    for fold, (tr_idx, va_idx) in enumerate(_timeseries_split_by_date(df_kept, n_splits=5), 1):
        X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
        y_tr, y_va = y.iloc[tr_idx], y.iloc[va_idx]

        model.fit(X_tr, y_tr)
        p = model.predict_proba(X_va)[:, 1]
        auc = roc_auc_score(y_va, p)
        aucs.append(float(auc))
        print(f"[CV] fold={fold} AUC={auc:.4f} | train={len(tr_idx):,} valid={len(va_idx):,}")

    mean_auc = float(np.mean(aucs)) if aucs else float("nan")
    print(f"[INFO] CV mean AUC={mean_auc:.4f} | label={label_col} | features={X.shape[1]}")

    # 전체 학습 후 저장
    model.fit(X, y)
    joblib.dump({"model": model, "feature_cols": info["features"]}, model_path)
    print(f"[OK] Saved model pack -> {model_path}")

    meta_path = str(Path(model_path).with_suffix(".meta.json"))
    meta = {
        "model_path": model_path,
        "label_col": label_col,
        "cv_auc": aucs,
        "cv_mean_auc": mean_auc,
        **info,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[OK] Saved meta       -> {meta_path}")
    return meta


def main():
    # ✅ ETF도 5일만
    target_labels = ["y_5"]

    df = load_etf_panel()
    df["date"] = pd.to_datetime(df["date"])

    for label_col in target_labels:
        model_path = str(MODEL_DIR / f"etf_lgbm_bin_{label_col}.joblib")
        _ = train_one_etf_lgbm(df, label_col=label_col, model_path=model_path)


if __name__ == "__main__":
    main()