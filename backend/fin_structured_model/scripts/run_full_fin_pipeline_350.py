# scripts/run_full_fin_pipeline_350.py
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
    ap.add_argument("--universe_path", default="data/processed/universe_k200_k150_fixed.parquet")
    ap.add_argument("--base_year", type=int, default=2023)
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--fs_div", default="CONSOL")
    ap.add_argument("--batch_size", type=int, default=100)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--price_start", default="2022-01-01")
    ap.add_argument("--build_marketcap", action="store_true")
    ap.add_argument("--build_price", action="store_true")
    ap.add_argument("--export_reports", action="store_true")
    ap.add_argument("--as_of", default="latest")
    args = ap.parse_args()

    py = sys.executable

    # 0) 분기 키
    reprt_keys = ["Q1", "H1", "Q3", "FY"]

    # 1) 2023/2024 재무 수집+merge+normalize (총 8회)
    for y in [args.base_year, args.target_year]:
        for k in reprt_keys:
            print(f"\n===== [STEP] FETCH+MERGE+NORM year={y} reprt_key={k} =====")

            # (1) fetch batches + merge
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

            # (2) normalize
            run([
                py, "-m", "scripts.normalize_core",
                "--year", str(y),
                "--reprt_key", k
            ], allow_fail=False)

    # 2) 스코어 생성(재무 기반)
    print("\n===== [STEP] BUILD SCORES (financial only) =====")
    run([
        py, "-m", "scripts.build_scores",
        "--target_year", str(args.target_year),
        "--base_year", str(args.base_year),
    ], allow_fail=False)

    # 3) (옵션) 시총 붙이기 + 스코어 재생성
    if args.build_marketcap:
        print("\n===== [STEP] MARKET CAP + REBUILD SCORES =====")
        base_scores = Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}.parquet")
        run([
            py, "-m", "scripts.fetch_market_cap_yfinance",
            "--scores_path", str(base_scores),
            "--out_path", "data/processed/market_cap.parquet"
        ], allow_fail=True)

        run([
            py, "-m", "scripts.build_scores",
            "--target_year", str(args.target_year),
            "--base_year", str(args.base_year),
            "--with_market_cap"
        ], allow_fail=False)

    # 4) (옵션) 가격 붙이기 + 스코어 최종 재생성
    if args.build_price:
        print("\n===== [STEP] PRICE + REBUILD SCORES =====")
        with_mc_scores = Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}_with_mc.parquet")
        # market_cap이 없으면 build_scores가 만들어둔 with_mc가 없을 수 있으니 fallback
        if not with_mc_scores.exists():
            with_mc_scores = Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}.parquet")

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

        # 최종 scores
        cmd = [
            py, "-m", "scripts.build_scores",
            "--target_year", str(args.target_year),
            "--base_year", str(args.base_year),
        ]
        if args.build_marketcap:
            cmd.append("--with_market_cap")
        cmd.append("--with_price")
        run(cmd, allow_fail=False)

    # 5) (옵션) 350 리포트 배치 생성
    if args.export_reports:
        print("\n===== [STEP] EXPORT REPORTS (batch) =====")
        # final scores 파일 선택
        cand = [
            Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}_with_mc_with_price.parquet"),
            Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}_with_price.parquet"),
            Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}_with_mc.parquet"),
            Path(f"data/processed/fin_scores_v2_{args.target_year}_{args.fs_div}.parquet"),
        ]
        in_path = next((p for p in cand if p.exists()), cand[-1])

        run([
            py, "-m", "scripts.run_full_auto_batch_k200_k150",
            "--as_of", args.as_of,
            "--target_year", str(args.target_year),
            "--base_year", str(args.base_year),
            "--fs_div", args.fs_div,
            "--universe_path", args.universe_path,
            "--out_dir", "data/processed/reports",
            "--jsonl_path", "data/processed/reports_batch.jsonl",
            "--fail_csv", "data/processed/reports_failed.csv",
        ], allow_fail=False)

    print("\n[OK] FULL PIPELINE DONE.")

if __name__ == "__main__":
    main()