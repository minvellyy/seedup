from __future__ import annotations
from pathlib import Path
import re
import pandas as pd
import FinanceDataReader as fdr

OUT_PATH = Path("universe/stock_krx_all.csv")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

def _norm_code(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    # 6자리 숫자만 남기기
    m = re.search(r"(\d{6})", s)
    return m.group(1) if m else ""

def main():
    # KRX 전체 상장 목록
    listing = fdr.StockListing("KRX")

    # 컬럼 이름은 FDR 버전에 따라 조금 다를 수 있어 안전하게 처리
    # 흔히: Code, Name, Market, Sector, Industry, ListingDate ...
    code_col = "Code" if "Code" in listing.columns else ("Symbol" if "Symbol" in listing.columns else None)
    name_col = "Name" if "Name" in listing.columns else ("Company" if "Company" in listing.columns else None)
    mkt_col  = "Market" if "Market" in listing.columns else ("MarketId" if "MarketId" in listing.columns else None)

    if code_col is None or name_col is None:
        raise RuntimeError(f"[ERR] Unexpected listing columns: {listing.columns.tolist()}")

    df = listing.copy()
    df["ticker"] = df[code_col].apply(_norm_code)
    df["name"] = df[name_col].astype(str)

    if mkt_col is not None:
        df["market"] = df[mkt_col].astype(str)
    else:
        df["market"] = ""

    # 티커가 비었거나 6자리가 아니면 제거
    df = df[df["ticker"].str.match(r"^\d{6}$", na=False)].copy()

    # (선택) 너무 잡주/우선주/스팩까지 다 포함될 수 있음
    # "전체 종목" 원하면 아래 필터는 꺼도 됨.
    # 최소한의 품질 필터를 넣고 싶으면 아래를 ON:
    # - 종목명에 '스팩', 'SPAC' 등 포함 제거
    # - 우선주(종목명 끝 '우', '우B' 등) 제거
    # 하지만 사용자 요청이 "전체"라 기본은 OFF.

    out = df[["ticker", "name", "market"]].drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[OK] Saved universe: {OUT_PATH} | n={len(out):,}")
    print(out.head(10).to_string(index=False))

if __name__ == "__main__":
    main()