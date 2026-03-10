from __future__ import annotations
import pandas as pd
import numpy as np

# v1: 계정명 룰(필요 시 확장)
MAP = {
    "revenue": ["매출액", "수익(매출액)", "영업수익", "매출"],
    "op_income": ["영업이익"],
    "net_income": ["당기순이익", "분기순이익", "반기순이익", "당기순이익(손실)"],
    "pretax_income": ["법인세차감전 순이익"],  # ✅ 추가
    "total_assets": ["자산총계", "총자산"],
    "total_liab": ["부채총계", "총부채"],
    "total_equity": ["자본총계", "총자본"],
    "current_assets": ["유동자산"],
    "current_liab": ["유동부채"],
    "cfo": ["영업활동현금흐름", "영업활동으로인한현금흐름"],
    "capex": ["유형자산의취득", "유형자산 취득"],
}

def _to_number(x) -> float:
    if x is None:
        return np.nan
    s = str(x).replace(",", "").strip()
    if s in ("", "-", "NaN", "nan"):
        return np.nan
    try:
        return float(s)
    except:
        return np.nan

def normalize_core_accounts(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    raw_df: DART fnlttSinglAcnt output rows for many tickers.
    Picks 'thstrm_amount' (당기) as default.
    """
    df = raw_df.copy()
    # 'account_nm' / 'thstrm_amount' columns exist in DART core response
    if "account_nm" not in df.columns:
        return pd.DataFrame()

    df["amount"] = df.get("thstrm_amount", "").apply(_to_number)
    df["account_nm"] = df["account_nm"].astype(str)

    # ticker, year, reprt_code 기반 pivot
    key_cols = ["ticker", "bsns_year", "reprt_code", "fs_div"]
    out = df[key_cols].drop_duplicates().copy()

    for std_key, patterns in MAP.items():
        mask = False
        for p in patterns:
            mask = mask | df["account_nm"].str.contains(p, regex=False)
        sub = df[mask].groupby(key_cols, as_index=False)["amount"].sum()  # 같은 계정 중복 합산 방어
        sub.rename(columns={"amount": std_key}, inplace=True)
        out = out.merge(sub, on=key_cols, how="left")
   
    # --- Hybrid: add columns (pretax_income + proxy flag) ---
    if "pretax_income" not in out.columns:
        out["pretax_income"] = np.nan
    if "net_income_proxy" not in out.columns:
        out["net_income_proxy"] = False

    # --- Hybrid fallback: net_income missing -> use pretax_income (flag it) ---
    if "net_income" in out.columns and "pretax_income" in out.columns:
        mask_fb = out["net_income"].isna() & out["pretax_income"].notna()
        out.loc[mask_fb, "net_income"] = out.loc[mask_fb, "pretax_income"]
        out.loc[mask_fb, "net_income_proxy"] = True

    return out