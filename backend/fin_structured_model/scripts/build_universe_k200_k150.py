from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta

from pykrx import stock as pkstock

def _yyyymmdd_today_fallback() -> str:
    # 주말/휴장 대응: 오늘부터 최대 10일 전까지 뒤로 가며 시도
    d = datetime.now()
    for _ in range(10):
        ymd = d.strftime("%Y%m%d")
        try:
            # 이 호출이 깨지면 해당 날짜는 안되는 것
            _ = pkstock.get_index_ticker_list(date=ymd)
            return ymd
        except Exception:
            d = d - timedelta(days=1)
    # 최후 fallback(최근 연말)
    return "20241231"

def get_index_constituents_by_name(index_name: str, date: str) -> list[str]:
    """
    market 파라미터를 쓰지 않고 전체 지수 목록(date 기준)에서 이름 매칭 후 구성종목 반환
    """
    tickers = pkstock.get_index_ticker_list(date=date)
    target_code = None
    for code in tickers:
        name = pkstock.get_index_ticker_name(code)
        if name == index_name:
            target_code = code
            break

    if target_code is None:
        # 완전 일치 실패 시, contains로 한 번 더(환경에 따라 공백/표기 차이 대비)
        for code in tickers:
            name = pkstock.get_index_ticker_name(code)
            if index_name.replace(" ", "") in str(name).replace(" ", ""):
                target_code = code
                break

    if target_code is None:
        raise RuntimeError(f"Index not found by name='{index_name}' at date={date}")

    # 구성종목
    cons = pkstock.get_index_portfolio_deposit_file(target_code)
    return [str(x).zfill(6) for x in cons]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_path", default="data/processed/universe_k200_k150.parquet")
    ap.add_argument("--base_universe", default="data/processed/universe.parquet",
                    help="ticker->corp_code 매핑용(있으면 merge)")
    ap.add_argument("--date", default="", help="YYYYMMDD (비우면 자동 fallback)")
    args = ap.parse_args()

    date = args.date.strip() or _yyyymmdd_today_fallback()
    print(f"[INFO] using date={date} for index constituents")

    k200 = get_index_constituents_by_name("코스피 200", date=date)
    k150 = get_index_constituents_by_name("코스닥 150", date=date)

    tickers = sorted(set(k200 + k150))
    df = pd.DataFrame({"ticker": tickers})

    # base universe가 있으면 corp_code/corp_name 등을 merge
    base_p = Path(args.base_universe)
    if base_p.exists():
        base = pd.read_parquet(base_p).copy()
        if "ticker" in base.columns:
            base["ticker"] = base["ticker"].astype(str).str.zfill(6)
            cols = [c for c in ["ticker", "corp_code", "corp_name"] if c in base.columns]
            base = base[cols].drop_duplicates("ticker")
            df = df.merge(base, on="ticker", how="left")

    out_p = Path(args.out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_p, index=False)

    print(f"[OK] saved universe: {out_p} rows={len(df)}")
    print(df.head(10).to_string(index=False))
    if "corp_code" in df.columns:
        print("[INFO] corp_code missing rate:", float(df["corp_code"].isna().mean()))

if __name__ == "__main__":
    main()