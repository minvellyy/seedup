import argparse
from pathlib import Path
import numpy as np
import pandas as pd

def safe_div(a, b):
    return np.where((b == 0) | pd.isna(b) | pd.isna(a), np.nan, a / b)

def annualized_vol(ret_series: pd.Series) -> float:
    # 일수익률 표준편차 * sqrt(252)
    if ret_series is None or ret_series.dropna().shape[0] < 20:
        return np.nan
    return float(ret_series.dropna().std() * np.sqrt(252))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_scores", required=True)
    ap.add_argument("--price_daily", default="data/processed/price_daily_yf.parquet")
    ap.add_argument("--out_path", default="data/processed/price_features_asof.parquet")
    args = ap.parse_args()

    scores = pd.read_parquet(args.in_scores).copy()
    scores["ticker"] = scores["ticker"].astype(str).str.zfill(6)
    scores["as_of"] = pd.to_datetime(scores["as_of"]).dt.normalize()

    px = pd.read_parquet(args.price_daily).copy()
    if px.empty:
        raise SystemExit("[ERR] price_daily is empty. Run fetch_price_yfinance first.")
   
    # --- normalize wide price schema -> long(ticker, symbol, date, close) ---
    cols = list(px.columns)

    # case: columns are strings like "('ticker', '')", "('close', '000660.KS')"
    if "('ticker', '')" in cols and "('date', '')" in cols:
        # base columns
        base = px[["('ticker', '')", "('symbol', '')", "('date', '')"]].copy()
        base.rename(columns={
            "('ticker', '')": "ticker",
            "('symbol', '')": "symbol",
            "('date', '')": "date",
        }, inplace=True)

    # find close columns
    close_cols = [c for c in cols if c.startswith("('close',")]
    if not close_cols:
        raise KeyError(f"No close columns found. columns={cols}")

    long_parts = []
    for c in close_cols:
        # parse symbol inside: "('close', '000660.KS')" -> 000660.KS
        sym = c.split(",")[1].strip().strip(")").strip().strip("'").strip('"')
        tmp = base.copy()
        tmp["symbol"] = sym
        tmp["ticker"] = sym.split(".")[0].zfill(6)
        tmp["close"] = px[c].astype(float)
        long_parts.append(tmp)

    px = pd.concat(long_parts, ignore_index=True)
    # drop rows where close is NaN (because wide form has NaNs for other symbols)
    px = px.dropna(subset=["close"]).copy()

# else: keep original (already long) and continue below
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["date"] = pd.to_datetime(px["date"]).dt.normalize()
    px = px.sort_values(["ticker","date"])

    # 일수익률
    px["ret_1d"] = px.groupby("ticker")["close"].pct_change()

    # 각 as_of에 대해: 직전 거래일 close를 선택 + lookback 산출
    out_rows = []
    for t, g_asof in scores[["ticker","as_of"]].drop_duplicates().groupby("ticker"):
        g_px = px[px["ticker"] == t].copy()
        if g_px.empty:
            for _, r in g_asof.iterrows():
                out_rows.append({
                    "ticker": t, "as_of": r["as_of"],
                    "close_asof": np.nan,
                    "ret_3m": np.nan, "ret_6m": np.nan, "ret_12m": np.nan,
                    "vol_3m": np.nan, "vol_6m": np.nan,
                    "dd_52w": np.nan,
                    "price_source": "yfinance",
                    "price_missing": True
                })
            continue

        g_px = g_px.set_index("date")

        for _, r in g_asof.iterrows():
            asof = r["as_of"]

            # 직전 거래일
            hist_until = g_px.loc[g_px.index <= asof]
            if hist_until.empty:
                out_rows.append({
                    "ticker": t, "as_of": asof,
                    "close_asof": np.nan,
                    "ret_3m": np.nan, "ret_6m": np.nan, "ret_12m": np.nan,
                    "vol_3m": np.nan, "vol_6m": np.nan,
                    "dd_52w": np.nan,
                    "price_source": "yfinance",
                    "price_missing": True
                })
                continue

            close_asof = float(hist_until["close"].iloc[-1])

            # 기준일로부터 lookback (거래일 기준 대략치)
            # 3m≈63d, 6m≈126d, 12m≈252d
            idx = hist_until.index
            pos = len(hist_until) - 1

            def close_lag(n):
                p = pos - n
                if p < 0:
                    return np.nan
                return float(hist_until["close"].iloc[p])

            c_3m = close_lag(63)
            c_6m = close_lag(126)
            c_12m = close_lag(252)

            ret_3m = safe_div(close_asof, c_3m) - 1 if not np.isnan(c_3m) else np.nan
            ret_6m = safe_div(close_asof, c_6m) - 1 if not np.isnan(c_6m) else np.nan
            ret_12m = safe_div(close_asof, c_12m) - 1 if not np.isnan(c_12m) else np.nan

            # 변동성: 최근 63/126 거래일의 일수익률
            win_3m = hist_until["ret_1d"].iloc[max(0, pos-63):pos+1]
            win_6m = hist_until["ret_1d"].iloc[max(0, pos-126):pos+1]
            vol_3m = annualized_vol(win_3m)
            vol_6m = annualized_vol(win_6m)

            # 52주 낙폭: 최근 252 거래일 고점 대비
            win_52w = hist_until["close"].iloc[max(0, pos-252):pos+1]
            peak_52w = float(win_52w.max()) if len(win_52w) else np.nan
            dd_52w = (close_asof / peak_52w - 1) if (peak_52w and not np.isnan(peak_52w)) else np.nan

            out_rows.append({
                "ticker": t, "as_of": asof,
                "close_asof": close_asof,
                "ret_3m": float(ret_3m) if not np.isnan(ret_3m) else np.nan,
                "ret_6m": float(ret_6m) if not np.isnan(ret_6m) else np.nan,
                "ret_12m": float(ret_12m) if not np.isnan(ret_12m) else np.nan,
                "vol_3m": vol_3m,
                "vol_6m": vol_6m,
                "dd_52w": float(dd_52w) if not np.isnan(dd_52w) else np.nan,
                "price_source": "yfinance",
                "price_missing": False
            })

    out = pd.DataFrame(out_rows)
    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    print(f"[OK] saved price features: {out_path} rows={len(out)}")
    print(out.head(10).to_string(index=False))

if __name__ == "__main__":
    main()