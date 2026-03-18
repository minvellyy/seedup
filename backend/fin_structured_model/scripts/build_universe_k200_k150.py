from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import FinanceDataReader as fdr


def get_index_constituents(index_key: str) -> list[str]:
    """
    KOSPI200 / KOSDAQ150 구성종목 티커 리스트 반환.
    FinanceDataReader StockListing + 시가총액 상위 N 종목으로 근사.
    """
    if index_key == "KOSPI200":
        df = fdr.StockListing("KOSPI")
        market_col = "Code" if "Code" in df.columns else "Symbol"
        cap_col    = "Marcap" if "Marcap" in df.columns else None
        if cap_col:
            df = df.sort_values(cap_col, ascending=False).head(200)
        else:
            df = df.head(200)
        return df[market_col].astype(str).str.zfill(6).tolist()

    elif index_key == "KOSDAQ150":
        df = fdr.StockListing("KOSDAQ")
        market_col = "Code" if "Code" in df.columns else "Symbol"
        cap_col    = "Marcap" if "Marcap" in df.columns else None
        if cap_col:
            df = df.sort_values(cap_col, ascending=False).head(150)
        else:
            df = df.head(150)
        return df[market_col].astype(str).str.zfill(6).tolist()

    else:
        raise ValueError(f"지원하지 않는 index_key: {index_key}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_path", default="data/processed/universe_k200_k150.parquet")
    ap.add_argument("--base_universe", default="data/processed/universe.parquet",
                    help="ticker->corp_code 매핑용(있으면 merge)")
    args = ap.parse_args()

    k200 = get_index_constituents("KOSPI200")
    k150 = get_index_constituents("KOSDAQ150")

    print(f"[INFO] KOSPI200: {len(k200)}개, KOSDAQ150: {len(k150)}개")

    tickers = sorted(set(k200 + k150))

    print(f"[INFO] KOSPI200: {len(k200)}개, KOSDAQ150: {len(k150)}개")

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