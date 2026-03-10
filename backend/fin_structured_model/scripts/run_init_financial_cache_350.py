# scripts/run_init_financial_cache_350.py
from __future__ import annotations
import argparse
import subprocess
import sys

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
    ap.add_argument("--universe_path", default="data/processed/universe_k200_k150_fixed.parquet")
    ap.add_argument("--base_year", type=int, default=2023)
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--fs_div", default="CONSOL")
    ap.add_argument("--batch_size", type=int, default=100)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()

    py = sys.executable
    reprt_keys = ["Q1", "H1", "Q3", "FY"]

    for y in [args.base_year, args.target_year]:
        for k in reprt_keys:
            print(f"\n===== [INIT] FETCH+MERGE+NORM year={y} reprt_key={k} =====")

            run([
                py, "-m", "scripts.run_fetch_batches",
                "--year", str(y),
                "--reprt_key", k,
                "--universe_path", args.universe_path,
                "--batch_size", str(args.batch_size),
                "--sleep", str(args.sleep),
                "--retries", str(args.retries),
                "--merge_after",
                "--fs_div", args.fs_div,
            ], allow_fail=False)

            run([
                py, "-m", "scripts.normalize_core",
                "--year", str(y),
                "--reprt_key", k
            ], allow_fail=False)

    print("\n[OK] INIT FINANCIAL CACHE DONE.")

if __name__ == "__main__":
    main()