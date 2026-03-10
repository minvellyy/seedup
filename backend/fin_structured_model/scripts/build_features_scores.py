from pathlib import Path
import pandas as pd
from src.config import SETTINGS
from src.features import add_as_of, build_ttm, compute_features
from src.scoring import percentile_scores, pillar_and_overall
from src.utils import ensure_dir

def main(year: int):
    base = Path(SETTINGS.data_dir)
    processed = ensure_dir(base / "processed")

    # FY만으로는 TTM이 어렵고, 원칙적으로는 Q1/Q3 등 분기 데이터가 필요함.
    # v1 MVP는: 최근 4분기(11013/11012/11014/11011)를 모두 수집해 합쳐야 함.
    # 여기서는 예시로 processed에 이미 합쳐진 분기 norm 파일(fin_core_norm_allq.parquet)이 있다고 가정.
    norm_path = processed / f"fin_core_norm_allq_{SETTINGS.fs_div}.parquet"
    df = pd.read_parquet(norm_path)

    # as_of 부여
    df = add_as_of(df)

    # TTM/지표
    ttm = build_ttm(df)
    feats = compute_features(ttm, market_cap_df=None)  # market_cap 붙이면 PER/PBR 활성화

    # 점수
    scored = percentile_scores(feats, group_col=None)
    final = pillar_and_overall(scored)

    out_path = processed / f"fin_scores_v1_{SETTINGS.fs_div}.parquet"
    final.to_parquet(out_path, index=False)
    print(f"Saved scores: {out_path} rows={len(final)}")

if __name__ == "__main__":
    main(year=2025)