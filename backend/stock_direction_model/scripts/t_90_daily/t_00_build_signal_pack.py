from __future__ import annotations
from pathlib import Path
import subprocess
import pandas as pd

from src.common.io import load_parquet, save_parquet

# ====== input paths (너 프로젝트 기준) ======
P_STOCK = Path("data/outputs/predictions/stock.parquet")
P_ETF   = Path("data/outputs/predictions/etf.parquet")
P_MKT   = Path("data/outputs/predictions/market.parquet")

U_STOCK = Path("universe/stock_krx_all.csv")
U_ETF   = Path("universe/etf_krx_all.csv")

OUT_DIR = Path("data/outputs/signal_pack")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "signal_pack_latest.parquet"
OUT_LATEST_CSV = OUT_DIR / "signal_pack_latest.csv"


def _run(cmd: list[str]) -> None:
    print("[RUN]", " ".join(cmd))
    subprocess.check_call(cmd)


def _maybe_build_predictions(run_pipeline: bool) -> None:
    """
    run_pipeline=False: 이미 생성된 prediction parquet를 사용
    run_pipeline=True : 필요한 예측 스크립트들을 순서대로 실행
    """
    if not run_pipeline:
        return

    # 시장 예측(레짐) → 주식/ETF 피처빌드 시 조인/lag에 영향
    _run(["python", "-m", "scripts.03_predict.00_predict_market"])

    # 주식: feature → train → predict
    _run(["python", "-m", "scripts.01_features.00_build_stock_features"])
    _run(["python", "-m", "scripts.02_train.00_train_stock"])
    _run(["python", "-m", "scripts.03_predict.00_predict_stock"])

    # ETF: feature → train → predict
    _run(["python", "-m", "scripts.01_features.01_build_etf_features"])
    _run(["python", "-m", "scripts.02_train.01_train_etf"])
    _run(["python", "-m", "scripts.03_predict.01_predict_etf"])


def _load_universe(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    u = pd.read_csv(path)
    if "ticker" in u.columns:
        u["ticker"] = u["ticker"].astype(str)
    return u


def _latest_only(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    last = df["date"].max()
    return df[df["date"] == last].copy()


def _normalize_schema(df: pd.DataFrame, asset_type: str) -> pd.DataFrame:
    """
    stock/etf prediction 스키마를 통일.
    필수 컬럼 없으면 에러로 빠져서 조기 발견.
    """
    must = {"date", "ticker", "horizon", "p_up"}
    miss = must - set(df.columns)
    if miss:
        raise KeyError(f"[ERR] {asset_type} missing columns: {sorted(miss)}")

    out = df.copy()
    out["asset_type"] = asset_type

    # p_adj 없으면 p_up로 대체
    if "p_adj" not in out.columns:
        out["p_adj"] = out["p_up"]

    # market cols optional
    if "p_market_up" not in out.columns:
        out["p_market_up"] = pd.NA
    if "regime" not in out.columns:
        out["regime"] = pd.NA

    keep = ["date","asset_type","ticker","horizon","p_up","p_adj","p_market_up","regime"]
    keep = [c for c in keep if c in out.columns]
    return out[keep]


def build_signal_pack(run_pipeline: bool = False, latest_only: bool = True) -> Path:
    # 1) (옵션) 예측 파일 생성/갱신
    _maybe_build_predictions(run_pipeline=run_pipeline)

    # 2) 로드
    if not P_STOCK.exists():
        raise FileNotFoundError(f"[ERR] missing: {P_STOCK}")
    if not P_ETF.exists():
        raise FileNotFoundError(f"[ERR] missing: {P_ETF}")
    if not P_MKT.exists():
        print(f"[WARN] market prediction missing: {P_MKT} (signal_pack에는 NA로 남음)")

    stock = load_parquet(P_STOCK)
    etf   = load_parquet(P_ETF)

    if latest_only:
        stock = _latest_only(stock)
        etf   = _latest_only(etf)

    stock = _normalize_schema(stock, "stock")
    etf   = _normalize_schema(etf, "etf")

    # 3) universe join (name)
    u_s = _load_universe(U_STOCK)
    u_e = _load_universe(U_ETF)

    if u_s is not None and "name" in u_s.columns:
        stock = stock.merge(u_s[["ticker","name"]].drop_duplicates("ticker"), on="ticker", how="left")
    else:
        stock["name"] = pd.NA

    if u_e is not None and "name" in u_e.columns:
        etf = etf.merge(u_e[["ticker","name"]].drop_duplicates("ticker"), on="ticker", how="left")
    else:
        etf["name"] = pd.NA

    # 4) concat + rank
    pack = pd.concat([stock, etf], ignore_index=True)
    pack["score"] = pack["p_adj"].fillna(pack["p_up"])

    # 날짜별 랭킹
    pack["rank_in_asset"] = pack.groupby(["date","asset_type"])["score"].rank(ascending=False, method="first").astype(int)
    pack["rank_overall"]  = pack.groupby(["date"])["score"].rank(ascending=False, method="first").astype(int)

    # 5) 저장
    save_parquet(pack, OUT_LATEST)
    pack.to_csv(OUT_LATEST_CSV, index=False, encoding="utf-8-sig")

    print(f"[OK] signal_pack saved -> {OUT_LATEST} rows={len(pack):,} latest_only={latest_only}")
    return OUT_LATEST


def main():
    # 기본: pipeline은 이미 돌려뒀다는 가정(빠르게 pack만 갱신)
    build_signal_pack(run_pipeline=False, latest_only=True)

if __name__ == "__main__":
    main()