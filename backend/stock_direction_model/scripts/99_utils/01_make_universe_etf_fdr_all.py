# scripts/99_utils/01_make_universe_etf_fdr_all.py
from __future__ import annotations

from pathlib import Path
import pandas as pd
import FinanceDataReader as fdr


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    FDR 버전/리턴 스키마 차이를 흡수해서 최소 컬럼(ticker,name,market)을 맞춘다.
    """
    df = df.copy()

    # 1) ticker 후보 컬럼들
    ticker_candidates = ["Symbol", "Code", "Ticker", "종목코드", "단축코드"]
    name_candidates = ["Name", "종목명", "종목명(한글)", "한글종목명"]
    market_candidates = ["Market", "시장", "MarketName", "시장구분"]

    def pick_first(cols):
        for c in cols:
            if c in df.columns:
                return c
        return None

    tc = pick_first(ticker_candidates)
    nc = pick_first(name_candidates)
    mc = pick_first(market_candidates)

    if tc is None:
        raise KeyError(f"[ERR] Cannot find ticker column. Available columns={list(df.columns)}")

    df = df.rename(columns={tc: "ticker"})
    if nc is not None:
        df = df.rename(columns={nc: "name"})
    else:
        df["name"] = ""

    if mc is not None:
        df = df.rename(columns={mc: "market"})
    else:
        df["market"] = "ETF"

    # ticker 6자리 보정
    df["ticker"] = df["ticker"].astype(str).str.strip().str.zfill(6)

    # 최소 컬럼만 보장
    keep = ["ticker", "name", "market"]
    # 혹시 있으면 같이 보관할만한 컬럼(있으면 유지)
    extra_keep = []
    for c in ["ISIN", "isin", "ETF구분", "기초지수", "운용사", "상장좌수", "상장일"]:
        if c in df.columns:
            extra_keep.append(c)

    return df[keep + extra_keep]


def main():
    out_path = Path("universe/etf_krx_all.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # (A) FDR이 제공하는 ETF 전용 listing 시도
    df = None
    tried = []
    for listing in ["ETF/KR", "ETFKR", "KRX-ETF", "KRX_ETF"]:
        try:
            df = fdr.StockListing(listing)
            tried.append(f"{listing}:OK")
            if df is not None and len(df) > 0:
                break
        except Exception as e:
            tried.append(f"{listing}:FAIL({type(e).__name__})")

    # (B) 위가 안되면 KRX 전체에서 ETF만 필터(버전에 따라 market 컬럼이 다를 수 있음)
    if df is None or len(df) == 0:
        tried.append("KRX:FALLBACK")
        df_all = fdr.StockListing("KRX")
        # 가능한 경우의 수를 다 커버
        candidates = []
        for col in ["Market", "시장", "MarketName", "시장구분"]:
            if col in df_all.columns:
                candidates.append(col)

        if not candidates:
            raise RuntimeError(
                "[ERR] Cannot fallback-filter ETF from KRX listing: no market column.\n"
                f"Available columns={list(df_all.columns)}"
            )

        mcol = candidates[0]
        # ETF 라벨이 버전마다 다를 수 있어서 넓게 잡음
        mask = df_all[mcol].astype(str).str.contains("ETF|ETN", case=False, na=False)
        df = df_all.loc[mask].copy()

    df_u = _norm_cols(df)

    # 중복 제거 및 정렬
    df_u = df_u.drop_duplicates(subset=["ticker"]).sort_values("ticker").reset_index(drop=True)

    df_u.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[OK] Tried listings: {', '.join(tried)}")
    print(f"[OK] Saved ETF universe: {out_path} | n={len(df_u):,}")
    print(df_u.head(15).to_string(index=False))


if __name__ == "__main__":
    main()