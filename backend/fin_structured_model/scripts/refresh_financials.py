# scripts/refresh_financials.py
from __future__ import annotations
import argparse
import subprocess
import sys

def run(cmd: list[str]) -> None:
    print("[RUN]", " ".join(cmd))
    p = subprocess.run(cmd, check=False)
    if p.returncode != 0:
        raise SystemExit(f"[ERR] command failed: {' '.join(cmd)} (code={p.returncode})")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--reprt_key", type=str, required=True, choices=["Q1", "H1", "Q3", "FY"])
    ap.add_argument("--smoke", action="store_true", help="smoke mode (if fetch_dart_core supports it)")
    args = ap.parse_args()

    # 1) fetch raw from DART
    fetch_cmd = [sys.executable, "-m", "scripts.fetch_dart_core", "--year", str(args.year), "--reprt_key", args.reprt_key]
    if args.smoke:
        fetch_cmd.append("--smoke")
    run(fetch_cmd)

    # 2) normalize (overwrite processed for that year/quarter)
    norm_cmd = [sys.executable, "-m", "scripts.normalize_core", "--year", str(args.year), "--reprt_key", args.reprt_key]
    run(norm_cmd)

    print("[OK] refresh complete:", args.year, args.reprt_key)

if __name__ == "__main__":
    main()