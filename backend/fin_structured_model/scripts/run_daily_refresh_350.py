# scripts/run_daily_refresh_350.py
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

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
    ap.add_argument("--base_year", type=int, default=2023)
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--fs_div", default="CONSOL")
    ap.add_argument("--price_start", default="2022-01-01")
    ap.add_argument("--export_reports", action="store_true")
    ap.add_argument("--as_of", default="latest")
    args = ap.parse_args()

    py = sys.executable

    # 1) 재무 기반 scores 생성(재무 캐시를 읽음: fin_core_norm_* 필요)
    run([
        py, "-m", "scripts.build_scores",
        "--target_year", str(args.target_year),
        "--base_year", str(args.base_year),
    ], allow_fail=False)

    base_scores = Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}.parquet")

    # 2) 시총 갱신(실패해도 계속)
    run([
        py, "-m", "scripts.fetch_market_cap_yfinance",
        "--scores_path", str(base_scores),
        "--out_path", "data/processed/market_cap.parquet"
    ], allow_fail=True)

    # 3) 시총 반영 scores
    run([
        py, "-m", "scripts.build_scores",
        "--target_year", str(args.target_year),
        "--base_year", str(args.base_year),
        "--with_market_cap"
    ], allow_fail=False)

    with_mc_scores = Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}_with_mc.parquet")
    if not with_mc_scores.exists():
        with_mc_scores = base_scores

    # 4) 가격 갱신(실패해도 계속)
    run([
        py, "-m", "scripts.fetch_price_yfinance",
        "--in_scores", str(with_mc_scores),
        "--start", args.price_start,
        "--out_path", "data/processed/price_daily_yf.parquet"
    ], allow_fail=True)

    run([
        py, "-m", "scripts.build_price_features",
        "--in_scores", str(with_mc_scores),
        "--price_daily", "data/processed/price_daily_yf.parquet",
        "--out_path", "data/processed/price_features_asof.parquet"
    ], allow_fail=True)

    # 5) 최종 scores (시총+가격)
    run([
        py, "-m", "scripts.build_scores",
        "--target_year", str(args.target_year),
        "--base_year", str(args.base_year),
        "--with_market_cap",
        "--with_price"
    ], allow_fail=False)

    # 6) (선택) 리포트 재생성
    if args.export_reports:
        run([
            py, "-m", "scripts.run_full_auto_batch_k200_k150",
            "--as_of", args.as_of,
            "--target_year", str(args.target_year),
            "--base_year", str(args.base_year),
            "--fs_div", args.fs_div,
            "--universe_path", "data/processed/universe_k200_k150_fixed.parquet",
            "--out_dir", "data/processed/reports",
            "--jsonl_path", "data/processed/reports_batch.jsonl",
            "--fail_csv", "data/processed/reports_failed.csv",
        ], allow_fail=False)

    print("\n[OK] DAILY REFRESH DONE.")

if __name__ == "__main__":
    main()