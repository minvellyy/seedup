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

def piotroski_fscore(df: pd.DataFrame) -> pd.DataFrame:
    """
    Piotroski F-Score (Piotroski 2000) — 9개 이진 신호, 0~9 합산 후 0~100 정규화.

    수익성 (4):
      F1  ROA > 0
      F2  CFO/총자산 > 0
      F3  ΔROA > 0  (전년비 개선)
      F4  이익품질: CFO/총자산 > ROA  (현금이익 > 발생이익)
    재무안정성 (3):
      F5  부채비율 감소 (ΔD/E < 0)
      F6  유동비율 개선 (ΔCR > 0)
      F7  신주미발행  — shares 데이터 미확보로 제외 (NaN)
    경영효율성 (2):
      F8  영업이익률 개선 (ΔOPM > 0, Gross Margin 대체)
      F9  자산회전율 개선 (ΔAsset Turnover > 0)

    반환: df에 f_* 신호 컬럼, piotroski_raw (0~9), piotroski_score (0~100) 추가.
    유효 신호가 4개 미만이면 piotroski_score = NaN.
    """
    d = df.copy()

    def col(c: str) -> pd.Series:
        return d[c] if c in d.columns else pd.Series(np.nan, index=d.index)

    def bsig(cond: pd.Series, mask: pd.Series) -> pd.Series:
        """mask가 True인 곳만 0/1, 나머지는 NaN."""
        return np.where(mask, cond.astype(float), np.nan)

    roa   = col("roa");            roa_lag  = col("roa_lag4")
    cfa   = col("cfo_to_assets")
    de    = col("debt_equity");    de_lag   = col("debt_equity_lag4")
    cr    = col("current_ratio");  cr_lag   = col("current_ratio_lag4")
    opm   = col("opm");            opm_lag  = col("opm_lag4")
    at_   = col("asset_turnover"); at_lag   = col("asset_turnover_lag4")

    # ── 수익성 ────────────────────────────────────────────────────────
    d["f_roa_pos"]   = bsig(roa > 0,    roa.notna())
    d["f_cfo_pos"]   = bsig(cfa > 0,    cfa.notna())
    d["f_roa_delta"] = bsig(roa > roa_lag, roa.notna() & roa_lag.notna())
    d["f_accrual"]   = bsig(cfa > roa,  cfa.notna() & roa.notna())

    # ── 재무안정성 ────────────────────────────────────────────────────
    d["f_lev_down"]  = bsig(de < de_lag,  de.notna()  & de_lag.notna())
    d["f_cr_up"]     = bsig(cr > cr_lag,  cr.notna()  & cr_lag.notna())
    d["f_no_dilution"] = np.nan   # shares 데이터 미확보

    # ── 경영효율성 ────────────────────────────────────────────────────
    d["f_margin_up"] = bsig(opm > opm_lag, opm.notna() & opm_lag.notna())
    d["f_at_up"]     = bsig(at_ > at_lag,  at_.notna() & at_lag.notna())

    signals = [
        "f_roa_pos", "f_cfo_pos", "f_roa_delta", "f_accrual",
        "f_lev_down", "f_cr_up",  "f_no_dilution",
        "f_margin_up", "f_at_up",
    ]
    sig_df = d[signals]
    d["piotroski_raw"]   = sig_df.sum(axis=1, skipna=True).astype(float)   # 0~9
    d["piotroski_avail"] = sig_df.notna().sum(axis=1)                       # 유효 신호 수
    d["piotroski_score"] = np.where(
        d["piotroski_avail"] >= 4,
        d["piotroski_raw"] / d["piotroski_avail"] * 100,
        np.nan,
    )
    return d


def pillar_and_overall(d: pd.DataFrame) -> pd.DataFrame:
    out = d.copy()

    # ── 레이더 차트용 필라 점수 (기존 유지) ───────────────────────────
    out["profitability_score"] = 0.6*out["opm_score"] + 0.4*out["roa_score"]
    out["growth_score"]        = 0.5*out["sales_yoy_score"] + 0.5*out["op_income_yoy_score"]
    out["stability_score"]     = 0.6*out["debt_equity_score"] + 0.4*out["current_ratio_score"]

    # cashflow: fcf 없으면 cfo만
    out["cashflow_score"] = np.where(
        out["fcf_margin_score"].isna(),
        out["cfo_margin_score"],
        0.6*out["cfo_margin_score"] + 0.4*out["fcf_margin_score"]
    )

    # valuation: per 없으면 pbr만
    out["valuation_score"] = np.where(
        out["per_score"].isna(),
        out["pbr_score"],
        0.6*out["per_score"] + 0.4*out["pbr_score"]
    )

    # ── Piotroski F-Score → overall_score ────────────────────────────
    out = piotroski_fscore(out)

    # Piotroski가 없는 종목은 기존 필라 가중합으로 fallback
    weights = {
        "profitability_score": 0.25,
        "growth_score":        0.20,
        "stability_score":     0.20,
        "cashflow_score":      0.20,
        "valuation_score":     0.15,
    }
    wsum = pd.Series(0.0, index=out.index)
    ssum = pd.Series(0.0, index=out.index)
    for k, w in weights.items():
        valid = ~out[k].isna()
        wsum[valid] += w
        ssum[valid] += out.loc[valid, k] * w
    pillar_fallback = np.where(wsum == 0, np.nan, ssum / wsum)

    out["overall_score"] = np.where(
        out["piotroski_score"].notna(),
        out["piotroski_score"],
        pillar_fallback,
    )

    def grade(x):
        if pd.isna(x): return None
        if x < 20: return "취약"
        if x < 40: return "보통"
        if x < 60: return "양호"
        if x < 80: return "우수"
        return "탁월"

    out["overall_grade"] = out["overall_score"].apply(grade)
    return out