# scripts/02_train/00_train_market.py
from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib


# =========================
# Paths
# =========================
PROCESSED_CANDIDATES = [
    Path("data/processed/market/kospi_features.parquet"),   # ✅ feature 생성 코드 저장 경로
    Path("data/processed/market_features.parquet"),         # (구버전 경로 fallback)
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


def load_market_features() -> pd.DataFrame:
    path = _find_first_existing(PROCESSED_CANDIDATES)
    if not path.exists():
        raise FileNotFoundError(
            f"[ERR] Market feature parquet not found.\n"
            f"Checked: {', '.join(str(p) for p in PROCESSED_CANDIDATES)}\n"
            f"Hint: 먼저 market feature 생성 스크립트를 실행해서 parquet를 만들어야 합니다."
        )
    df = pd.read_parquet(path)
    print(f"[OK] Loaded market features: {path} | rows={len(df):,} cols={len(df.columns):,}")
    return df


def build_feature_matrix(
    df: pd.DataFrame,
    label_col: str,
    drop_cols_extra: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series, dict]:
    """
    - label_col(y_5) 기준으로 학습 데이터 구성
    - ✅ 라벨(y_*)/미래수익률(ret_fwd_*) 전부 feature에서 제외 (누수/피처 mismatch 방지)
    - 결측/상수열 제거
    - feature list / 제거 내역 리턴
    """
    drop_cols_extra = drop_cols_extra or []

    if label_col not in df.columns:
        raise KeyError(f"[ERR] label_col={label_col} not found in df.columns")

    # ✅ 날짜 정렬
    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)

    # ✅ 학습에 쓰면 안 되는 컬럼들
    auto_drop = set()
    auto_drop.add(label_col)

    for c in df.columns:
        # 미래수익률/라벨 계열은 전부 제외
        if c.startswith("ret_fwd_"):
            auto_drop.add(c)
        if c.startswith("y_"):          # ✅ 여기 추가: y_10 같은 라벨이 피처에 끼는 것 방지
            auto_drop.add(c)

    if "date" in df.columns:
        auto_drop.add("date")

    for c in drop_cols_extra:
        auto_drop.add(c)

    # ✅ 숫자형만 feature 후보로
    feature_candidates = []
    for c in df.columns:
        if c in auto_drop:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            feature_candidates.append(c)

    X = df[feature_candidates].copy()
    y = df[label_col].copy()

    # ✅ 라벨 결측 제거
    keep = y.notna()
    X = X.loc[keep].reset_index(drop=True)
    y = y.loc[keep].astype(int).reset_index(drop=True)

    # ✅ 결측/상수열 제거
    removed = {"missing_cols": [], "constant_cols": []}

    # 결측이 하나라도 있는 컬럼 제거
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


def train_one(df: pd.DataFrame, label_col: str, model_path: str) -> dict:
    """
    - y_5만 학습 (main에서 통제)
    - time-series split AUC 출력
    """
    X, y, info = build_feature_matrix(df, label_col=label_col)

    if len(X) < 500:
        print(f"[WARN] Rows are small: {len(X)} (학습은 되지만 성능 안정성 낮을 수 있음)")

    pipe = Pipeline([
        ("scaler", StandardScaler(with_mean=True, with_std=True)),
        ("clf", LogisticRegression(
            max_iter=500,
            solver="lbfgs",
            n_jobs=None,
            class_weight="balanced",
        )),
    ])

    tscv = TimeSeriesSplit(n_splits=5)
    aucs = []
    for fold, (tr_idx, va_idx) in enumerate(tscv.split(X), 1):
        X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
        y_tr, y_va = y.iloc[tr_idx], y.iloc[va_idx]

        pipe.fit(X_tr, y_tr)
        p = pipe.predict_proba(X_va)[:, 1]
        auc = roc_auc_score(y_va, p)
        aucs.append(float(auc))
        print(f"[CV] fold={fold} AUC={auc:.4f} | train={len(tr_idx):,} valid={len(va_idx):,}")

    mean_auc = float(np.mean(aucs)) if aucs else float("nan")
    print(f"[INFO] CV mean AUC={mean_auc:.4f} | label={label_col} | features={X.shape[1]}")

    # 전체 학습 후 저장
    pipe.fit(X, y)
    joblib.dump(pipe, model_path)
    print(f"[OK] Saved model -> {model_path}")

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
    print(f"[OK] Saved meta  -> {meta_path}")

    return meta


def main():
    # ✅ market 모델은 '약한 레짐 필터(5일)'로만 쓰기: y_5만 학습
    target_labels = ["y_5"]

    df = load_market_features()

    for label_col in target_labels:
        model_path = str(MODEL_DIR / f"market_bin_{label_col}.joblib")
        _ = train_one(df, label_col, model_path=model_path)


if __name__ == "__main__":
    main()