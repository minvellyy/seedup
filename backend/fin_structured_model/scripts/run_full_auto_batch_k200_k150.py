# scripts/run_full_auto_batch_k200_k150.py
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
import pandas as pd

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

def load_universe(path_prefer: Path, path_fallback: Path) -> list[str]:
    p = path_prefer if path_prefer.exists() else path_fallback
    u = pd.read_parquet(p)
    if "ticker" not in u.columns:
        raise ValueError(f"universe parquet must include 'ticker' column: {p}")
    tickers = u["ticker"].astype(str).str.zfill(6).unique().tolist()
    return tickers

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as_of", default="latest", help="YYYY-MM-DD or latest")
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--base_year", type=int, default=2023)
    ap.add_argument("--fs_div", default="CONSOL")
    ap.add_argument("--price_start", default="2022-01-01")
    ap.add_argument("--universe_path", default="data/processed/universe_k200_k150.parquet")
    ap.add_argument("--fallback_universe_path", default="data/processed/universe.parquet")
    ap.add_argument("--out_dir", default="data/processed/reports")
    ap.add_argument("--jsonl_path", default="data/processed/reports_batch.jsonl")
    ap.add_argument("--fail_csv", default="data/processed/reports_failed.csv")
    args = ap.parse_args()

    py = sys.executable
    processed = Path("data/processed")
    out_dir = Path(args.out_dir) / (args.as_of if args.as_of != "latest" else "latest")
    out_dir.mkdir(parents=True, exist_ok=True)

    # scores 파일 경로( build_scores.py 규칙 )
    base_scores = processed / f"fin_scores_v2_{args.target_year}_{args.fs_div}.parquet"
    with_mc_scores = processed / f"fin_scores_v2_{args.target_year}_{args.fs_div}_with_mc.parquet"
    final_scores = processed / f"fin_scores_v2_{args.target_year}_{args.fs_div}_with_mc_with_price.parquet"

    market_cap_path = processed / "market_cap.parquet"
    price_daily_path = processed / "price_daily_yf.parquet"
    price_feat_path = processed / "price_features_asof.parquet"

    # 0) 유니버스 로드(350개)
    tickers = load_universe(Path(args.universe_path), Path(args.fallback_universe_path))
    print(f"[INFO] universe tickers={len(tickers)} (from {args.universe_path if Path(args.universe_path).exists() else args.fallback_universe_path})")

    # 1) 재무 scores 생성
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year)], allow_fail=False)

    # 2) market cap 생성(실패해도 진행)
    run([py, "-m", "scripts.fetch_market_cap_yfinance",
         "--scores_path", str(base_scores),
         "--out_path", str(market_cap_path)], allow_fail=True)

    # 3) market cap 반영 scores 생성
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year),
         "--with_market_cap"], allow_fail=False)

    # 4) 가격 수집 + 피처 생성(실패해도 진행)
    run([py, "-m", "scripts.fetch_price_yfinance",
         "--in_scores", str(with_mc_scores),
         "--start", args.price_start,
         "--out_path", str(price_daily_path)], allow_fail=True)

    run([py, "-m", "scripts.build_price_features",
         "--in_scores", str(with_mc_scores),
         "--price_daily", str(price_daily_path),
         "--out_path", str(price_feat_path)], allow_fail=True)

    # 5) 최종 scores 생성(시총+가격)
    run([py, "-m", "scripts.build_scores",
         "--target_year", str(args.target_year),
         "--base_year", str(args.base_year),
         "--with_market_cap",
         "--with_price"], allow_fail=False)

    # 6) 350개 리포트 생성
    #    - in_path는 final_scores가 있으면 그것, 아니면 with_mc_scores로 degrade
    in_path = final_scores if final_scores.exists() else with_mc_scores
    print(f"[INFO] report in_path={in_path}")

    # JSONL 준비
    jsonl = Path(args.jsonl_path)
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    if jsonl.exists():
        jsonl.unlink()  # 이번 배치 새로 생성

    failed = []

    for i, tk in enumerate(tickers, 1):
        out_json = out_dir / f"{tk}.json"
        cmd = [py, "-m", "scripts.export_structured_report",
               "--ticker", tk,
               "--as_of", args.as_of,
               "--in_path", str(in_path),
               "--out_path", str(out_json)]

        code, _, _ = run(cmd, allow_fail=True)
        if code != 0:
            failed.append({"ticker": tk, "as_of": args.as_of, "reason": "export_failed"})
            continue

        # jsonl append
        try:
            obj = json.loads(out_json.read_text(encoding="utf-8"))
            with jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception as e:
            failed.append({"ticker": tk, "as_of": args.as_of, "reason": f"jsonl_append_failed:{e}"})

        if i % 25 == 0:
            print(f"[PROGRESS] {i}/{len(tickers)} reports done")

    # 실패 저장
    if failed:
        fail_path = Path(args.fail_csv)
        pd.DataFrame(failed).to_csv(fail_path, index=False, encoding="utf-8-sig")
        print(f"[WARN] failed reports: {len(failed)} saved to {fail_path}")
    else:
        print("[OK] all reports generated")

    print(f"[OK] DONE. reports_dir={out_dir} jsonl={jsonl}")

if __name__ == "__main__":
    main()