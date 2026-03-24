from __future__ import annotations
import pandas as pd
import numpy as np

# reprt_code -> 분기말(as_of) 매핑(단순)
REPRT_TO_QEND = {
    "11013": "-03-31",
    "11012": "-06-30",
    "11014": "-09-30",
    "11011": "-12-31",
}

def add_as_of(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["as_of"] = d.apply(lambda r: f"{int(r['bsns_year'])}{REPRT_TO_QEND.get(r['reprt_code'], '-12-31')}", axis=1)
    d["as_of"] = pd.to_datetime(d["as_of"])
    return d

def build_ttm(df_q: pd.DataFrame) -> pd.DataFrame:
    """
    df_q: normalized quarterly-like rows per ticker/as_of with core accounts.
    Computes TTM for flow items and latest for stock items.
    """
    d = df_q.sort_values(["ticker", "as_of"]).copy()
    
    # --- robust schema: proxy flag (missing -> False, NaN -> False, bool cast) ---
    if "net_income_proxy" not in d.columns:
        d["net_income_proxy"] = False
    d["net_income_proxy"] = d["net_income_proxy"].fillna(False).astype(bool)

    flow_cols = ["revenue", "op_income", "net_income", "cfo", "capex"]
    stock_cols = ["total_assets", "total_liab", "total_equity", "current_assets", "current_liab"]

    # rolling sum for flow
    # cfo/capex는 DART 분기 보고서에 없고 연간(FY)만 존재하므로 min_periods=1로 연간값 활용
    # 이후 ffill로 cfo 없는 최신 FY 행(연간보고서 제출됐으나 CF 미포함)도 이전 값 승계
    for c in flow_cols:
        if c in d.columns:
            mp = 1 if c in ("cfo", "capex") else 4
            d[f"{c}_ttm"] = d.groupby("ticker")[c].rolling(4, min_periods=mp).sum().reset_index(level=0, drop=True)
    for c in ("cfo", "capex"):
        col = f"{c}_ttm"
        if col in d.columns:
            d[col] = d.groupby("ticker")[col].ffill()
    
    # --- explainability flag: propagate proxy usage into TTM window ---
    if "net_income_proxy" in d.columns:
        d["ttm_net_income_proxy"] = (
            d.groupby("ticker")["net_income_proxy"]
             .rolling(4, min_periods=4)
             .max()
             .reset_index(level=0, drop=True)
             .astype(bool)
        )

    # if TTM net income is not available yet, proxy flag should be False (avoid confusion)
    if "net_income_ttm" in d.columns and "ttm_net_income_proxy" in d.columns:
        d.loc[d["net_income_ttm"].isna(), "ttm_net_income_proxy"] = False

    # latest for stock (use current quarter)
    for c in stock_cols:
        if c in d.columns:
            d[f"{c}_curr"] = d[c]

    # average assets for ROA denominator (avg of last 4 quarters)
    if "total_assets" in d.columns:
        d["avg_assets_4q"] = d.groupby("ticker")["total_assets"].rolling(4, min_periods=4).mean().reset_index(level=0, drop=True)

    return d

def compute_features(ttm_df: pd.DataFrame, market_cap_df: pd.DataFrame | None = None) -> pd.DataFrame:
    d = ttm_df.copy()
    
    # --- key normalization (merge 안정화) ---
    d["ticker"] = d["ticker"].astype(str).str.zfill(6)
    d["as_of"] = pd.to_datetime(d["as_of"]).dt.normalize()

    # attach market cap if provided: columns ['ticker','as_of','market_cap']
    if market_cap_df is not None and not market_cap_df.empty:
        m = market_cap_df.copy()
        m["ticker"] = m["ticker"].astype(str).str.zfill(6)
        m["as_of"] = pd.to_datetime(m["as_of"]).dt.normalize()
        d = d.merge(m[["ticker", "as_of", "market_cap"]], on=["ticker", "as_of"], how="left")
    else:
        d["market_cap"] = np.nan
    
    def safe_div(a, b):
        return np.where((b == 0) | pd.isna(b) | pd.isna(a), np.nan, a / b)

    # profitability
    d["opm"] = safe_div(d.get("op_income_ttm"), d.get("revenue_ttm"))
    d["roa"] = safe_div(d.get("net_income_ttm"), d.get("avg_assets_4q"))

    # growth (TTM YoY: compare to 4 quarters ago)
    d["revenue_ttm_lag4"] = d.groupby("ticker")["revenue_ttm"].shift(4)
    d["op_income_ttm_lag4"] = d.groupby("ticker")["op_income_ttm"].shift(4)
    d["sales_yoy"] = safe_div(d.get("revenue_ttm"), d["revenue_ttm_lag4"]) - 1
    d["op_income_yoy"] = safe_div(d.get("op_income_ttm"), d["op_income_ttm_lag4"]) - 1

    # stability
    d["debt_equity"] = safe_div(d.get("total_liab_curr"), d.get("total_equity_curr"))
    d["current_ratio"] = safe_div(d.get("current_assets_curr"), d.get("current_liab_curr"))

    # cashflow
    d["cfo_margin"] = safe_div(d.get("cfo_ttm"), d.get("revenue_ttm"))
    d["fcf_margin"] = safe_div((d.get("cfo_ttm") - d.get("capex_ttm")), d.get("revenue_ttm"))

    # valuation
    d["pbr"] = safe_div(d.get("market_cap"), d.get("total_equity_curr"))
    d["per"] = safe_div(d.get("market_cap"), d.get("net_income_ttm"))
    # negative earnings -> PER invalid
    d.loc[d.get("net_income_ttm") <= 0, "per"] = np.nan

    cols = [
        "ticker", "as_of",
        "opm","roa","sales_yoy","op_income_yoy",
        "debt_equity","current_ratio","cfo_margin","fcf_margin","per","pbr",
        "market_cap","ttm_net_income_proxy"
    ]
    return d[cols].copy()