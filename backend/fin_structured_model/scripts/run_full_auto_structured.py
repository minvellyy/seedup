# scripts/run_full_auto_structured.py
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

def run(cmd: list[str], allow_fail: bool = False) -> tuple[int, str, str]:
    print("[RUN]", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print("[ERR]", " ".join(cmd))
        print("STDOUT:\n", p.stdout)
        print("STDERR:\n", p.stderr)
        if not allow_fail:
            raise SystemExit(p.returncode)
    else:
        if p.stdout.strip():
            print(p.stdout.strip())
    return p.returncode, p.stdout, p.stderr

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--as_of", required=True)   # YYYY-MM-DD or latest
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--base_year", type=int, default=2023)
    ap.add_argument("--fs_div", default="CONSOL")
    ap.add_argument("--price_start", default="2022-01-01")
    ap.add_argument("--out_json", default="data/processed/structured_report.json")
    args = ap.parse_args()

    py = sys.executable
    processed = Path("data/processed")

    # build_scores 출력 규칙(너 build_scores.py 기준)
    base_scores = processed / f"fin_scores_v2_{args.target_year}_{args.fs_div}.parquet"
    with_mc_scores = processed / f"fin_scores_v2_{args.target_year}_{args.fs_div}_with_mc.parquet"
    final_scores = processed / f"fin_scores_v2_{args.target_year}_{args.fs_div}_with_mc_with_price.parquet"

    market_cap_path = processed / "market_cap.parquet"
    price_daily_path = processed / "price_daily_yf.parquet"
    price_feat_path = processed / "price_features_asof.parquet"

    # 1) (재무 캐시 기반) 재무만 scores 생성
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year)], allow_fail=False)

    # 2) (선택) market cap 생성 (실패해도 진행)
    run([py, "-m", "scripts.fetch_market_cap_yfinance",
         "--scores_path", str(base_scores),
         "--out_path", str(market_cap_path)], allow_fail=True)

    # 3) market cap 반영 scores 재생성 (market_cap 없으면 내부에서 경고 후 진행)
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year),
         "--with_market_cap"], allow_fail=False)

    # 4) (선택) 가격 수집 + 피처 생성 (실패해도 진행)
    #    가격은 with_mc_scores를 입력으로 받는 걸 권장
    run([py, "-m", "scripts.fetch_price_yfinance",
         "--in_scores", str(with_mc_scores),
         "--start", args.price_start,
         "--out_path", str(price_daily_path)], allow_fail=True)

    run([py, "-m", "scripts.build_price_features",
         "--in_scores", str(with_mc_scores),
         "--price_daily", str(price_daily_path),
         "--out_path", str(price_feat_path)], allow_fail=True)

    # 5) market cap + price 반영 scores 최종 생성
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year),
         "--with_market_cap",
         "--with_price"], allow_fail=False)

    # 6) 리포트 JSON 생성 (최종 파일이 있으면 그걸 사용, 없으면 with_mc로 fallback)
    in_path = final_scores if final_scores.exists() else with_mc_scores
    run([py, "-m", "scripts.export_structured_report",
         "--ticker", str(args.ticker),
         "--as_of", str(args.as_of),
         "--in_path", str(in_path),
         "--out_path", str(args.out_json)], allow_fail=False)

    print(f"[OK] DONE. report={args.out_json} (in_path={in_path})")

if __name__ == "__main__":
    main()