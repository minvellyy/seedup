# scripts/merge_raw_batches.py
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

from src.config import SETTINGS
from src.utils import ensure_dir


def main(year: int, reprt_key: str, fs_div: str | None = None, delete_parts: bool = False):
    fs_div = fs_div or SETTINGS.fs_div
    base = Path(SETTINGS.data_dir)
    raw_dir = ensure_dir(base / "raw")

    pattern = f"dart_core_{year}_{reprt_key}_{fs_div}_*.parquet"
    parts = sorted(raw_dir.glob(pattern))

    if not parts:
        raise SystemExit(f"[ERR] no batch files found: {raw_dir}/{pattern}")

    print(f"[INFO] found parts={len(parts)} pattern={pattern}")

    dfs = []
    for p in parts:
        df = pd.read_parquet(p)
        df["__part__"] = p.name
        dfs.append(df)

    all_df = pd.concat(dfs, ignore_index=True)

    # dedup 키(가능한 컬럼만 사용)
    # DART core가 보통 포함하는 컬럼들: corp_code, bsns_year, reprt_code, fs_div, sj_div, account_id/account_nm, thstrm_amount 등
    cand_keys = [
        "corp_code", "bsns_year", "reprt_code", "fs_div",
        "sj_div", "account_id", "account_nm",
        "thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount",
        "ticker",
    ]
    keys = [c for c in cand_keys if c in all_df.columns]
    if keys:
        before = len(all_df)
        all_df = all_df.drop_duplicates(subset=keys, keep="last").copy()
        print(f"[INFO] dedup rows: {before} -> {len(all_df)} (keys={keys})")
    else:
        print("[WARN] no dedup keys found; saving as-is")

    # 저장(기본 파일명으로)
    out_path = raw_dir / f"dart_core_{year}_{reprt_key}_{fs_div}.parquet"
    all_df.drop(columns=["__part__"], errors="ignore").to_parquet(out_path, index=False)
    print(f"[OK] merged raw saved: {out_path} rows={len(all_df)}")

    # 선택: part 파일 삭제
    if delete_parts:
        for p in parts:
            try:
                p.unlink()
            except Exception:
                pass
        print(f"[OK] deleted part files: {len(parts)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--reprt_key", type=str, required=True, choices=["Q1", "H1", "Q3", "FY"])
    ap.add_argument("--fs_div", type=str, default=None)
    ap.add_argument("--delete_parts", action="store_true", help="merge 후 part 파일 삭제")
    args = ap.parse_args()

    main(year=args.year, reprt_key=args.reprt_key, fs_div=args.fs_div, delete_parts=args.delete_parts)