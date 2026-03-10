# scripts/run_fetch_batches.py
from __future__ import annotations
import argparse
import math
import subprocess
import sys
from pathlib import Path
import pandas as pd

def run(cmd: list[str], allow_fail: bool = False) -> int:
    print("[RUN]", " ".join(cmd))
    p = subprocess.run(cmd, text=True)
    if p.returncode != 0:
        print("[ERR]", " ".join(cmd), "code=", p.returncode)
        if not allow_fail:
            raise SystemExit(p.returncode)
    return p.returncode

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--reprt_key", type=str, required=True, choices=["Q1", "H1", "Q3", "FY"])
    ap.add_argument("--universe_path", type=str, default="data/processed/universe.parquet")
    ap.add_argument("--batch_size", type=int, default=200)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--merge_after", action="store_true", help="끝나고 merge_raw_batches 실행")
    ap.add_argument("--fs_div", type=str, default="CONSOL")
    ap.add_argument("--fail_csv", type=str, default="data/processed/fetch_failed_batches.csv")
    args = ap.parse_args()

    uni = pd.read_parquet(args.universe_path)
    if "ticker" not in uni.columns:
        raise SystemExit("[ERR] universe must include ticker")
    n = int(uni["ticker"].nunique())
    if n <= 0:
        raise SystemExit("[ERR] empty universe")

    bs = max(1, int(args.batch_size))
    num_batches = int(math.ceil(n / bs))
    print(f"[INFO] universe={args.universe_path} tickers={n} batch_size={bs} batches={num_batches}")

    py = sys.executable
    failed = []

    for i in range(num_batches):
        s = i * bs
        e = min((i + 1) * bs, n)

        cmd = [
            py, "-m", "scripts.fetch_dart_core",
            "--year", str(args.year),
            "--reprt_key", args.reprt_key,
            "--universe_path", args.universe_path,
            "--start_idx", str(s),
            "--end_idx", str(e),
            "--sleep", str(args.sleep),
            "--retries", str(args.retries),
        ]

        code = run(cmd, allow_fail=True)
        if code != 0:
            failed.append({"year": args.year, "reprt_key": args.reprt_key, "start_idx": s, "end_idx": e, "code": code})

        if (i + 1) % 5 == 0:
            print(f"[PROGRESS] {i+1}/{num_batches} batches done")

    if failed:
        Path(args.fail_csv).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(failed).to_csv(args.fail_csv, index=False, encoding="utf-8-sig")
        print(f"[WARN] failed batches={len(failed)} saved: {args.fail_csv}")
    else:
        print("[OK] all batches succeeded")

    if args.merge_after:
        run([py, "-m", "scripts.merge_raw_batches",
             "--year", str(args.year),
             "--reprt_key", args.reprt_key,
             "--fs_div", args.fs_div], allow_fail=False)

        print("[OK] merged raw completed")

if __name__ == "__main__":
    main()