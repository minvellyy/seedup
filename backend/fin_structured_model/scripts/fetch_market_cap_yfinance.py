import argparse
from pathlib import Path
import pandas as pd
import yfinance as yf

def fetch_market_cap_one(ticker6: str) -> tuple[float | None, str]:
    """
    returns (market_cap, symbol_used)
    """
    for sym in (f"{ticker6}.KS", f"{ticker6}.KQ"):
        # 1) fast_info 시도
        try:
            fi = yf.Ticker(sym).fast_info
            mc = getattr(fi, "market_cap", None)
            if mc is not None and mc > 0:
                return float(mc), sym
        except Exception:
            pass

        # 2) info 시도(느리지만 커버리지 보완)
        try:
            info = yf.Ticker(sym).info
            mc2 = info.get("marketCap")
            if mc2 is not None and mc2 > 0:
                return float(mc2), sym
        except Exception:
            pass

    return None, "NA"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores_path", default="data/processed/fin_scores_v2_smoke_2024_CONSOL.parquet")
    ap.add_argument("--out_path", default="data/processed/market_cap.parquet")
    args = ap.parse_args()

    scores = pd.read_parquet(args.scores_path)
    scores["ticker"] = scores["ticker"].astype(str).str.zfill(6)
    scores["as_of"] = pd.to_datetime(scores["as_of"]).dt.normalize()

    tickers = sorted(scores["ticker"].unique().tolist())

    rows = []
    for t in tickers:
        mc, sym = fetch_market_cap_one(t)
        rows.append({
            "ticker": t,
            "market_cap": mc,
            "market_cap_symbol": sym,
            "market_cap_source": "yfinance",
        })

    mcdf = pd.DataFrame(rows)
    out = scores[["ticker","as_of"]].drop_duplicates().merge(mcdf, on="ticker", how="left")

    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    print(f"[OK] saved market cap: {out_path} rows={len(out)}")
    print(out.head(10).to_string(index=False))
    print("[INFO] missing market_cap rate:", float(out["market_cap"].isna().mean()))

if __name__ == "__main__":
    main()