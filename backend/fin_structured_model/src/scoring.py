from __future__ import annotations
import pandas as pd
import numpy as np

POSITIVE = ["opm","roa","sales_yoy","op_income_yoy","current_ratio","cfo_margin","fcf_margin"]
NEGATIVE = ["debt_equity","per","pbr"]  # 낮을수록 좋음

def percentile_scores(df: pd.DataFrame, group_col: str | None = None) -> pd.DataFrame:
    """
    Convert features to 0-100 percentile scores.
    group_col: sector 같은 peer group이 있으면 넣기. 없으면 전체 비교.
    """
    d = df.copy()

    def _pct(s: pd.Series) -> pd.Series:
        # rank(pct=True) gives 0~1
        return s.rank(pct=True) * 100

    features = POSITIVE + NEGATIVE
    for f in features:
        if f not in d.columns:
            d[f"{f}_score"] = np.nan
            continue
        if group_col and group_col in d.columns:
            pct = d.groupby(group_col)[f].transform(_pct)
        else:
            pct = _pct(d[f])
        if f in NEGATIVE:
            pct = 100 - pct
        d[f"{f}_score"] = pct

    return d

def pillar_and_overall(d: pd.DataFrame) -> pd.DataFrame:
    out = d.copy()

    # pillar scores
    out["profitability_score"] = 0.6*out["opm_score"] + 0.4*out["roa_score"]
    out["growth_score"] = 0.5*out["sales_yoy_score"] + 0.5*out["op_income_yoy_score"]
    out["stability_score"] = 0.6*out["debt_equity_score"] + 0.4*out["current_ratio_score"]

    # cashflow: if fcf_margin_score missing -> use cfo only
    out["cashflow_score"] = np.where(
        out["fcf_margin_score"].isna(),
        out["cfo_margin_score"],
        0.6*out["cfo_margin_score"] + 0.4*out["fcf_margin_score"]
    )

    # valuation: if per missing -> pbr only
    out["valuation_score"] = np.where(
        out["per_score"].isna(),
        out["pbr_score"],
        0.6*out["per_score"] + 0.4*out["pbr_score"]
    )

    # overall (re-normalize if some pillars missing)
    weights = {
        "profitability_score": 0.25,
        "growth_score": 0.20,
        "stability_score": 0.20,
        "cashflow_score": 0.20,
        "valuation_score": 0.15,
    }
    wsum = pd.Series(0.0, index=out.index)
    ssum = pd.Series(0.0, index=out.index)
    for k, w in weights.items():
        valid = ~out[k].isna()
        wsum[valid] += w
        ssum[valid] += out.loc[valid, k] * w
    out["overall_score"] = np.where(wsum == 0, np.nan, ssum / wsum)

    def grade(x):
        if pd.isna(x): return None
        if x < 20: return "취약"
        if x < 40: return "보통"
        if x < 60: return "양호"
        if x < 80: return "우수"
        return "탁월"

    out["overall_grade"] = out["overall_score"].apply(grade)
    return out