# scripts/build_scores.py
from __future__ import annotations
import argparse
import pandas as pd
from pathlib import Path

from src.config import SETTINGS
from src.utils import ensure_dir
from src.features import add_as_of, build_ttm, compute_features
from src.scoring import percentile_scores, pillar_and_overall
from src.ytd import ytd_to_quarter

def load_year(processed: Path, year: int) -> pd.DataFrame:
    parts = []
    for k in ["Q1", "H1", "Q3", "FY"]:
        p = processed / f"fin_core_norm_{year}_{k}_{SETTINGS.fs_div}.parquet"
        if not p.exists():
            raise FileNotFoundError(f"Missing normalized file: {p}")
        parts.append(pd.read_parquet(p))
    return pd.concat(parts, ignore_index=True)

def load_fy_only(processed: Path, year: int) -> pd.DataFrame:
    """FY(연간) 파일만 로드. 현금흐름 롤링 윈도우 확장 용도."""
    p = processed / f"fin_core_norm_{year}_FY_{SETTINGS.fs_div}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Missing FY normalized file: {p}")
    return pd.read_parquet(p)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--base_year", type=int, default=2023, help="TTM 계산을 위해 함께 로드할 이전 연도")
    ap.add_argument("--backfill_year", type=int, default=None,
                    help="현금흐름 롤링 윈도우 확장용 추가 연도(FY만 로드). 예: --backfill_year 2022")
    ap.add_argument("--with_market_cap", action="store_true", help="merge market cap (data/processed/market_cap.parquet)")
    ap.add_argument("--with_price", action="store_true", help="merge price features (data/processed/price_features_asof.parquet)")
    ap.add_argument("--out_tag", default="", help="output tag suffix, e.g. with_mc_with_price")
    args = ap.parse_args()

    base = Path(SETTINGS.data_dir)
    processed = ensure_dir(base / "processed")

    # 1) 캐시된 normalized 재무만 로드
    parts = []
    if args.backfill_year is not None:
        print(f"[INFO] backfill_year={args.backfill_year}: FY 데이터만 로드 (현금흐름 윈도우 확장)")
        parts.append(load_fy_only(processed, args.backfill_year))
    parts.append(load_year(processed, args.base_year))
    parts.append(load_year(processed, args.target_year))
    core = pd.concat(parts, ignore_index=True)

    # 2) as_of 생성 + YTD->분기 변환 + TTM
    core = add_as_of(core)
    core = ytd_to_quarter(core)
    ttm = build_ttm(core)

    # 3) (옵션) market cap 로드
    market_cap_df = None
    if args.with_market_cap:
        mc_path = processed / "market_cap.parquet"
        if mc_path.exists():
            market_cap_df = pd.read_parquet(mc_path)
        else:
            print(f"[WARN] market_cap not found: {mc_path} (continue without market cap)")
            market_cap_df = None

    # 4) 지표 계산 + 점수화
    feats = compute_features(ttm, market_cap_df=market_cap_df)
    scored = percentile_scores(feats, group_col=None)
    final = pillar_and_overall(scored)

    # 5) (옵션) 가격 피처 merge
    if args.with_price:
        pf_path = processed / "price_features_asof.parquet"
        if pf_path.exists():
            price_feats = pd.read_parquet(pf_path)
            # 키 정규화
            final["ticker"] = final["ticker"].astype(str).str.zfill(6)
            final["as_of"] = pd.to_datetime(final["as_of"]).dt.normalize()
            price_feats["ticker"] = price_feats["ticker"].astype(str).str.zfill(6)
            price_feats["as_of"] = pd.to_datetime(price_feats["as_of"]).dt.normalize()
            final = final.merge(price_feats, on=["ticker", "as_of"], how="left")
        else:
            print(f"[WARN] price_features not found: {pf_path} (continue without price features)")

    # 6) 저장
    tag = args.out_tag.strip()
    if not tag:
        tag_parts = []
        if args.with_market_cap: tag_parts.append("with_mc")
        if args.with_price: tag_parts.append("with_price")
        tag = "_".join(tag_parts)

    name = f"fin_scores_v2_{args.target_year}_{SETTINGS.fs_div}"
    if tag:
        name += f"_{tag}"
    out_path = processed / f"{name}.parquet"

    final.to_parquet(out_path, index=False)
    print(f"[OK] saved scores: {out_path} rows={len(final)}")
    print(final.sort_values("as_of").tail(10))

if __name__ == "__main__":
    main()