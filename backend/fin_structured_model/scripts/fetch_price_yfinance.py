import argparse
from pathlib import Path
import pandas as pd
import yfinance as yf

def resolve_symbol(ticker6: str) -> str | None:
    # 먼저 KS 시도, 실패하면 KQ
    for sym in (f"{ticker6}.KS", f"{ticker6}.KQ"):
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="5d")
            if hist is not None and len(hist) > 0:
                return sym
        except Exception:
            pass
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_scores", required=True)
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--out_path", default="data/processed/price_daily_yf.parquet")
    args = ap.parse_args()

    scores = pd.read_parquet(args.in_scores)
    tickers = sorted(scores["ticker"].astype(str).str.zfill(6).unique().tolist())

    rows = []
    for tk in tickers:
        sym = resolve_symbol(tk)
        if sym is None:
            # 심볼 못 찾으면 스킵(나중에 missing 처리)
            continue
        try:
            df = yf.download(sym, start=args.start, progress=False, auto_adjust=False)
            if df is None or df.empty:
                continue
            df = df.reset_index()
            # 컬럼명 정리
            df.rename(columns={"Date": "date"}, inplace=True)
            df["date"] = pd.to_datetime(df["date"]).dt.normalize()
            df["ticker"] = tk
            df["symbol"] = sym
            # Close만 쓰면 됨
            rows.append(df[["ticker", "symbol", "date", "Close"]].rename(columns={"Close": "close"}))
        except Exception:
            continue

    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["ticker","symbol","date","close"])
    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    print(f"[OK] saved daily prices: {out_path} rows={len(out)} tickers={out['ticker'].nunique() if len(out) else 0}")

if __name__ == "__main__":
    main()