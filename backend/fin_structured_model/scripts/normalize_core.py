from pathlib import Path
import argparse
import pandas as pd

from src.config import SETTINGS
from src.normalize import normalize_core_accounts
from src.utils import ensure_dir


def main(year: int, reprt_key: str = "FY") -> None:
    base = Path(SETTINGS.data_dir)
    raw = ensure_dir(base / "raw")
    processed = ensure_dir(base / "processed")

    raw_path = raw / f"dart_core_{year}_{reprt_key}_{SETTINGS.fs_div}.parquet"
    df_raw = pd.read_parquet(raw_path)

    # 오류 row(status!=000) 제거 (에러 요약행 제거)
    if "status" in df_raw.columns:
        df_raw = df_raw[df_raw["status"].isna()].copy()

    norm = normalize_core_accounts(df_raw)

    out_path = processed / f"fin_core_norm_{year}_{reprt_key}_{SETTINGS.fs_div}.parquet"
    norm.to_parquet(out_path, index=False)
    print(f"Saved normalized core: {out_path} rows={len(norm)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--reprt_key", type=str, default="FY", choices=["Q1", "H1", "Q3", "FY"])
    args = ap.parse_args()
    main(year=args.year, reprt_key=args.reprt_key)