import os
import argparse
import requests
import pandas as pd
from pathlib import Path
from tqdm import tqdm

# reprt_key -> reprt_code (DART)
REPRT_KEY_TO_CODE = {
    "Q1": "11013",
    "H1": "11012",
    "Q3": "11014",
    "FY": "11011",
}

# reprt_code -> 분기말(as_of)
REPRT_TO_QEND = {
    "11013": "-03-31",
    "11012": "-06-30",
    "11014": "-09-30",
    "11011": "-12-31",
}

def to_int(x):
    if x is None:
        return None
    s = str(x).replace(",", "").strip()
    if s in ("", "-", "nan", "NaN"):
        return None
    try:
        return int(float(s))
    except:
        return None

def pick_common_shares(items: list[dict]) -> int | None:
    """
    DART stockTotqySttus 응답 list에서 보통주(또는 그에 준하는) 발행주식수를 선택.
    1) se(구분)가 보통주 계열이면 우선
    2) 없으면 istc_totqy 중 최대값 fallback
    """
    if not items:
        return None

    # 1) 보통주 우선 탐색
    common_keys = ("보통", "보통주", "의결권", "의결권 있는", "의결권있는")
    candidates = []
    for it in items:
        se = str(it.get("se", "")).strip()
        qty = to_int(it.get("istc_totqy"))
        if qty is None:
            continue
        if any(k in se for k in common_keys):
            candidates.append(qty)

    if candidates:
        return max(candidates)

    # 2) fallback: 전체 중 최대 발행주식수
    all_qty = []
    for it in items:
        qty = to_int(it.get("istc_totqy"))
        if qty is not None:
            all_qty.append(qty)
    return max(all_qty) if all_qty else None

def fetch_stock_total_qty(api_key: str, corp_code: str, bsns_year: int, reprt_code: str) -> tuple[int | None, str]:
    """
    returns: (shares, status_message)
    """
    url = "https://opendart.fss.or.kr/api/stockTotqySttus.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(bsns_year),
        "reprt_code": reprt_code,
    }
    r = requests.get(url, params=params, timeout=30)
    j = r.json()
    status = j.get("status")
    msg = j.get("message", "")
    if status != "000":
        return None, f"{status}:{msg}"
    items = j.get("list", []) or []
    shares = pick_common_shares(items)
    return shares, "000:OK"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--reprt_key", type=str, required=True, choices=["Q1","H1","Q3","FY"])
    ap.add_argument("--universe_path", default="data/processed/universe.parquet")
    ap.add_argument("--out_path", default="data/processed/shares_outstanding.parquet")
    ap.add_argument("--smoke", action="store_true", help="use only first 10 tickers for test")
    args = ap.parse_args()

    api_key = os.getenv("DART_API_KEY") or os.getenv("DART_KEY") or os.getenv("OPENDART_API_KEY")
    if not api_key:
        raise SystemExit("[ERR] Set env var DART_API_KEY (or DART_KEY / OPENDART_API_KEY)")

    reprt_code = REPRT_KEY_TO_CODE[args.reprt_key]
    as_of = pd.to_datetime(f"{args.year}{REPRT_TO_QEND[reprt_code]}").normalize()

    uni = pd.read_parquet(args.universe_path)
    uni["ticker"] = uni["ticker"].astype(str).str.zfill(6)
    uni["corp_code"] = uni["corp_code"].astype(str).str.zfill(8)

    if args.smoke:
        uni = uni.head(10).copy()

    rows = []
    for _, r in tqdm(uni.iterrows(), total=len(uni)):
        ticker = r["ticker"]
        corp_code = r["corp_code"]
        shares, status_msg = fetch_stock_total_qty(api_key, corp_code, args.year, reprt_code)
        rows.append({
            "ticker": ticker,
            "corp_code": corp_code,
            "bsns_year": args.year,
            "reprt_code": reprt_code,
            "as_of": as_of,
            "shares_outstanding": shares,
            "status": status_msg,
        })

    out = pd.DataFrame(rows)
    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    print(f"[OK] saved shares: {out_path} rows={len(out)}")
    print(out.head(10).to_string(index=False))
    print("[INFO] status counts:\n", out["status"].value_counts(dropna=False).head(10).to_string())

if __name__ == "__main__":
    main()