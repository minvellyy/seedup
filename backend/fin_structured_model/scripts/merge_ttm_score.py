import pandas as pd
from pathlib import Path
import numpy as np

from src.config import SETTINGS
from src.utils import ensure_dir
from src.features import add_as_of, build_ttm, compute_features
from src.scoring import percentile_scores, pillar_and_overall
from src.ytd import ytd_to_quarter


def load_year(processed: Path, year: int) -> pd.DataFrame:
    parts = []
    for k in ["Q1", "H1", "Q3", "FY"]:
        p = processed / f"fin_core_norm_{year}_{k}_{SETTINGS.fs_div}.parquet"
        parts.append(pd.read_parquet(p))
    return pd.concat(parts, ignore_index=True)


def main(target_year: int = 2024):
    base = Path(SETTINGS.data_dir)
    processed = ensure_dir(base / "processed")

    # ✅ 1) 2023 + 2024 같이 로드 (TTM을 2024 Q1~Q3에도 만들기 위해)
    core = pd.concat(
        [load_year(processed, 2023), load_year(processed, target_year)],
        ignore_index=True
    )

    # ✅ 2) as_of 생성 후, 누적(YTD) → 분기 단독값 변환(매출/이익 같은 flow만)
    core = add_as_of(core)
    core = ytd_to_quarter(core)

    # ✅ 3) TTM 계산
    ttm = build_ttm(core)

    # ✅ market cap 로드
    market_cap_path = processed / "market_cap.parquet"
    market_cap_df = pd.read_parquet(market_cap_path) if market_cap_path.exists() else None

    # 지표 계산 (market_cap 미연결이면 valuation은 NaN이어도 OK)
    feats = compute_features(ttm, market_cap_df=market_cap_df)

    # 점수화
    scored = percentile_scores(feats, group_col=None)
    final = pillar_and_overall(scored)

    # ✅ Step 2 price features merge
    price_path = processed / "price_features_asof.parquet"
    if price_path.exists():
        price_feats = pd.read_parquet(price_path)
        price_feats["ticker"] = price_feats["ticker"].astype(str).str.zfill(6)
        price_feats["as_of"] = pd.to_datetime(price_feats["as_of"]).dt.normalize()

        final["ticker"] = final["ticker"].astype(str).str.zfill(6)
        final["as_of"] = pd.to_datetime(final["as_of"]).dt.normalize()

        final = final.merge(price_feats, on=["ticker", "as_of"], how="left")
    else:
        # price 파일이 없으면 컬럼만 만들어 두기 (파이프라인 안정)
        final["close_asof"] = np.nan
        final["ret_3m"] = np.nan
        final["ret_6m"] = np.nan
        final["ret_12m"] = np.nan
        final["vol_3m"] = np.nan
        final["vol_6m"] = np.nan
        final["dd_52w"] = np.nan
        final["price_source"] = "missing"
        final["price_missing"] = True

    # ✅ v2로 저장(구분)
    out_path = processed / f"fin_scores_v2_smoke_{target_year}_{SETTINGS.fs_div}_with_mc.parquet"
    final.to_parquet(out_path, index=False)
    print(f"[OK] saved scores: {out_path} rows={len(final)}")
    print(final.sort_values("as_of").tail(10))


if __name__ == "__main__":
    main(2024)