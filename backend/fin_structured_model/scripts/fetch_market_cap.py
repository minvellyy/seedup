import argparse
from pathlib import Path
import pandas as pd

from pykrx import stock

DEFAULT_SCORES_PATH = Path("data/processed/fin_scores_v2_smoke_2024_CONSOL.parquet")
DEFAULT_OUT_PATH = Path("data/processed/market_cap.parquet")

def to_yyyymmdd(dt) -> str:
    return pd.to_datetime(dt).strftime("%Y%m%d")

def nearest_prev_bday(yyyymmdd: str) -> str:
    # 주 단위 내 가장 가까운 영업일을 찾는 함수(휴일/주말 보정)
    # prev=True면 직전 영업일
    return stock.get_nearest_business_day_in_a_week(yyyymmdd, prev=True)

def fetch_market_cap_on(date_yyyymmdd: str, tickers: list[str]) -> pd.DataFrame:
    """
    Returns df: columns ['ticker','market_cap'] for given KRX date.
    """
    # pykrx는 종종 6자리 tickers가 string이어야 매칭이 잘 됨
    df = stock.get_market_cap_by_ticker(date_yyyymmdd)
    # df index = ticker, columns include '시가총액'
    df = df.reset_index().rename(columns={"티커": "ticker", "시가총액": "market_cap"})
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df = df[df["ticker"].isin(tickers)][["ticker", "market_cap"]].copy()
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_scores", default=str(DEFAULT_SCORES_PATH))
    ap.add_argument("--out_path", default=str(DEFAULT_OUT_PATH))
    ap.add_argument("--mode", choices=["from_scores", "custom"], default="from_scores")
    ap.add_argument("--tickers", default="", help="comma-separated tickers (custom mode)")
    ap.add_argument("--dates", default="", help="comma-separated YYYY-MM-DD (custom mode)")
    args = ap.parse_args()

    in_scores = Path(args.in_scores)
    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "from_scores":
        scores = pd.read_parquet(in_scores)
        scores["as_of"] = pd.to_datetime(scores["as_of"])
        tickers = sorted(scores["ticker"].astype(str).str.zfill(6).unique().tolist())
        as_of_list = sorted(scores["as_of"].dropna().unique().tolist())
    else:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]
        as_of_list = [pd.to_datetime(x.strip()) for x in args.dates.split(",") if x.strip()]
        if not tickers or not as_of_list:
            raise SystemExit("[ERR] custom mode requires --tickers and --dates")

    rows = []
    for as_of in as_of_list:
        d0 = to_yyyymmdd(as_of)
        d = nearest_prev_bday(d0)

        mc = fetch_market_cap_on(d, tickers)
        mc["as_of"] = pd.to_datetime(as_of).normalize()
        mc["queried_date"] = d  # 실제 조회된 영업일(디버깅/설명용)
        rows.append(mc)

    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["ticker","as_of","market_cap","queried_date"])
    # 중복 방지
    out = out.drop_duplicates(subset=["ticker", "as_of"], keep="last").sort_values(["as_of","ticker"]).reset_index(drop=True)

    out.to_parquet(out_path, index=False)
    print(f"[OK] saved market cap: {out_path} rows={len(out)}")
    print(out.head(10).to_string(index=False))

if __name__ == "__main__":
    main()