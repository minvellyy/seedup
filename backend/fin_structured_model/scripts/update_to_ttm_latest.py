"""
최신 TTM 데이터로 fin_scores parquet을 갱신하는 스크립트.

사용법 (fin_structured_model/ 디렉터리에서 실행):
    python -m scripts.update_to_ttm_latest
    python -m scripts.update_to_ttm_latest --target_year 2025 --latest_reprt_key Q3
    python -m scripts.update_to_ttm_latest --skip_fetch  # DART 수집 건너뜀 (이미 원시 데이터 있을 때)

TTM 계산 원리:
    target_year=2025, latest_reprt_key=Q3 기준:
        2024 Q4 + 2025 Q1 + 2025 Q2 + 2025 Q3 = TTM as of 2025-09-30

결과 파일:
    data/processed/fin_scores_v2_2025_CONSOL_with_mc_with_price.parquet
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPRT_ORDER = ["Q1", "H1", "Q3", "FY"]


def run(cmd: list[str], allow_fail: bool = False) -> int:
    print("[RUN]", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=False, text=True)
    if p.returncode != 0:
        print(f"[ERR] 실패 (returncode={p.returncode}): {' '.join(cmd)}")
        if not allow_fail:
            raise SystemExit(p.returncode)
    return p.returncode


def main():
    ap = argparse.ArgumentParser(description="최신 TTM fin_scores 갱신 파이프라인")
    ap.add_argument("--target_year", type=int, default=2025,
                    help="갱신할 연도 (기본값: 2025)")
    ap.add_argument("--base_year", type=int, default=None,
                    help="TTM 계산용 이전 연도 (기본값: target_year - 1)")
    ap.add_argument("--latest_reprt_key", default="Q3", choices=REPRT_ORDER,
                    help="target_year에서 사용할 가장 최신 분기 (기본값: Q3)")
    ap.add_argument("--skip_fetch", action="store_true",
                    help="DART 수집·정규화 건너뜀 (원시 데이터가 이미 있을 때)")
    ap.add_argument("--price_start", default="2023-01-01",
                    help="가격 데이터 수집 시작일 (기본값: 2023-01-01)")
    args = ap.parse_args()

    if args.base_year is None:
        args.base_year = args.target_year - 1

    py = sys.executable
    processed = Path("data/processed")

    # target_year에서 수집할 분기 목록 (latest_reprt_key까지)
    fetch_reprt_keys = REPRT_ORDER[: REPRT_ORDER.index(args.latest_reprt_key) + 1]

    print("=" * 60)
    print(f"[설정] target_year={args.target_year}  base_year={args.base_year}")
    print(f"[설정] 수집 분기: {fetch_reprt_keys}")
    print(f"[설정] TTM 기준: {args.target_year}-{args.latest_reprt_key}")
    print("=" * 60)

    # ── 1. DART 수집 & 정규화 ────────────────────────────────────────────────
    if not args.skip_fetch:
        for rk in fetch_reprt_keys:
            print(f"\n[단계 1-{rk}] DART 수집: {args.target_year} {rk}")
            run([py, "-m", "scripts.fetch_dart_core",
                 "--year", str(args.target_year),
                 "--reprt_key", rk])

        for rk in fetch_reprt_keys:
            print(f"\n[단계 2-{rk}] 정규화: {args.target_year} {rk}")
            run([py, "-m", "scripts.normalize_core",
                 "--year", str(args.target_year),
                 "--reprt_key", rk])
    else:
        print("\n[단계 1-2] DART 수집·정규화 건너뜀 (--skip_fetch)")

    # ── 2. 재무 점수 생성 (market_cap·price 없이) ────────────────────────────
    print(f"\n[단계 3] 재무 점수 계산 (target={args.target_year}, base={args.base_year})")
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year),
         "--allow_partial_target"])

    base_scores = processed / f"fin_scores_v2_{args.target_year}_CONSOL.parquet"

    # ── 3. 시가총액 수집 ────────────────────────────────────────────────────
    print("\n[단계 4] 시가총액 수집")
    market_cap_path = processed / "market_cap.parquet"
    run([py, "-m", "scripts.fetch_market_cap_yfinance",
         "--scores_path", str(base_scores),
         "--out_path", str(market_cap_path)], allow_fail=True)

    # ── 4. 시가총액 반영 점수 재계산 ─────────────────────────────────────────
    print("\n[단계 5] 시가총액 반영 점수 재계산")
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year),
         "--allow_partial_target",
         "--with_market_cap"])

    with_mc_scores = processed / f"fin_scores_v2_{args.target_year}_CONSOL_with_mc.parquet"

    # ── 5. 가격 데이터 수집 ────────────────────────────────────────────────
    print("\n[단계 6] 가격 데이터 수집")
    price_daily_path = processed / "price_daily_yf.parquet"
    price_feat_path = processed / "price_features_asof.parquet"

    run([py, "-m", "scripts.fetch_price_yfinance",
         "--in_scores", str(with_mc_scores),
         "--start", args.price_start,
         "--out_path", str(price_daily_path)], allow_fail=True)

    run([py, "-m", "scripts.build_price_features",
         "--in_scores", str(with_mc_scores),
         "--price_daily", str(price_daily_path),
         "--out_path", str(price_feat_path)], allow_fail=True)

    # ── 6. 최종 점수 파일 생성 ────────────────────────────────────────────
    print("\n[단계 7] 최종 점수 파일 생성 (시가총액 + 가격 포함)")
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year),
         "--allow_partial_target",
         "--with_market_cap",
         "--with_price"])

    final = processed / f"fin_scores_v2_{args.target_year}_CONSOL_with_mc_with_price.parquet"
    print("\n" + "=" * 60)
    print(f"[완료] 최종 파일: {final}")
    print(f"[완료] TTM 기준: {args.target_year}-{args.latest_reprt_key} (as of {args.target_year}-{'09-30' if args.latest_reprt_key == 'Q3' else '06-30' if args.latest_reprt_key == 'H1' else '03-31' if args.latest_reprt_key == 'Q1' else '12-31'})")
    print("=" * 60)


if __name__ == "__main__":
    main()
