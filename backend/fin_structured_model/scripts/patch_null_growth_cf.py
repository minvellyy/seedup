"""
성장성(sales_yoy, op_income_yoy) 및 현금흐름(cfo_margin, fcf_margin) 지표가
null인 종목에 FY 연간 데이터 기반 대체값을 채우는 패치 스크립트.

동작:
  1. 대상 연도의 FY norm 파일(fin_core_norm_{year}_FY_CONSOL.parquet)에서
     연간 매출·영업이익·CFO·Capex 로드 (reprt_code=11011, ytd_to_quarter 이전 원본)
  2. 직전 연도 FY 파일로 전년 매출·영업이익 로드
  3. 스코어 파케이(fin_scores_v2_{year}_CONSOL_with_mc_with_price.parquet)에서
     각 티커의 최신 as_of 행을 찾아, null인 지표만 FY 대체값으로 채움
  4. 전체 데이터셋을 대상으로 percentile_scores + pillar_and_overall 재계산
     (분포가 바뀌므로 전체 재계산 필요)
  5. 원본 파일에 덮어씀 + 패치 로그 CSV 내보냄

Usage (fin_structured_model 디렉토리에서 실행):
    python -m scripts.patch_null_growth_cf
    python -m scripts.patch_null_growth_cf --target_year 2025 --prior_year 2024
    python -m scripts.patch_null_growth_cf --dry_run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_BASE_DIR = _SCRIPT_DIR.parent       # fin_structured_model/
sys.path.insert(0, str(_BASE_DIR))

from src.config import SETTINGS
from src.scoring import percentile_scores, pillar_and_overall


# ── 상수 ─────────────────────────────────────────────────────────────────────
PROCESSED = _BASE_DIR / "data" / "processed"
FS_DIV = SETTINGS.fs_div   # "CONSOL"


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return np.where((b == 0) | b.isna() | a.isna(), np.nan, a / b)


def _load_fy_norm(year: int) -> pd.DataFrame:
    """FY norm 파케이를 로드하고 reprt_code=11011(연간) 행만 반환."""
    path = PROCESSED / f"fin_core_norm_{year}_FY_{FS_DIV}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"FY norm 파일을 찾을 수 없습니다: {path}")
    df = pd.read_parquet(path)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    # reprt_code는 문자열 "11011" 또는 정수 11011 혼용 가능
    df["reprt_code"] = df["reprt_code"].astype(str).str.strip()
    fy = df[df["reprt_code"] == "11011"].copy()
    if fy.empty:
        raise ValueError(f"{year} FY norm 파일에 reprt_code=11011 행이 없습니다.")
    return fy


def _build_fy_fallback(target_year: int, prior_year: int) -> pd.DataFrame:
    """
    target_year FY + prior_year FY 데이터를 이용해 티커별 대체 지표 계산.
    cfo/capex는 target_year에 없으면 prior_year 값으로 추가 폴백.
    반환 컬럼: ticker, sales_yoy_fy, op_income_yoy_fy, cfo_margin_fy, fcf_margin_fy
    """
    fy_cur = _load_fy_norm(target_year)
    fy_prv = _load_fy_norm(prior_year)

    # 여러 fs_div 행이 섞여 있을 경우 연결 재무(CONSOL) 우선, 없으면 별도(OFS)
    def _pick_best(df: pd.DataFrame) -> pd.DataFrame:
        """ticker당 fs_div 우선순위: CONSOL > OFS, 중복이면 첫 행만."""
        priority = {"CONSOL": 0, "OFS": 1}
        df = df.copy()
        df["_rank"] = df["fs_div"].map(priority).fillna(9)
        return (
            df.sort_values(["ticker", "_rank"])
              .groupby("ticker", as_index=False)
              .first()
              .drop(columns="_rank")
        )

    cur = _pick_best(fy_cur)[["ticker", "revenue", "op_income", "cfo", "capex"]]
    prv = _pick_best(fy_prv)[["ticker", "revenue", "op_income", "cfo", "capex"]]

    # 컬럼 이름 구분
    cur = cur.rename(columns={"revenue": "rev_cur", "op_income": "op_cur",
                               "cfo": "cfo_cur", "capex": "capex_cur"})
    prv = prv.rename(columns={"revenue": "rev_prv", "op_income": "op_prv",
                               "cfo": "cfo_prv", "capex": "capex_prv"})

    # OUTER JOIN: target_year FY가 없는 종목도 prior_year 데이터로 커버
    merged = cur.merge(prv, on="ticker", how="outer")

    # YoY 성장률 플래그: target_year 원본 매출/영업이익이 있을 때만 계산
    has_cur_rev = merged["rev_cur"].notna()
    has_cur_op  = merged["op_cur"].notna()

    # cfo/capex: target_year에 없으면 prior_year 값으로 폴백
    merged["cfo_cur"]   = merged["cfo_cur"].where(merged["cfo_cur"].notna(),   merged["cfo_prv"])
    merged["capex_cur"] = merged["capex_cur"].where(merged["capex_cur"].notna(), merged["capex_prv"])
    # 매출 폴백 (cfo_margin 계산 분모용) — target_year 매출 없으면 prior_year 사용
    merged["rev_cur"]   = merged["rev_cur"].where(merged["rev_cur"].notna(),   merged["rev_prv"])

    # 성장률: (cur - prv) / |prv|  — 전년이 음수여도 방향 유지
    # target_year 원본 데이터가 없으면 YoY = NaN (폴백 매출값으로 0 나오는 것 방지)
    def _yoy(cur_s: pd.Series, prv_s: pd.Series, valid_mask: pd.Series) -> pd.Series:
        denom = prv_s.abs()
        result = np.where(
            (~valid_mask) | (denom == 0) | denom.isna() | cur_s.isna(),
            np.nan,
            (cur_s - prv_s) / denom,
        )
        return pd.Series(result, index=merged.index)

    merged["sales_yoy_fy"]      = _yoy(merged["rev_cur"], merged["rev_prv"], has_cur_rev)
    merged["op_income_yoy_fy"]  = _yoy(merged["op_cur"],  merged["op_prv"],  has_cur_op)
    merged["cfo_margin_fy"]     = _safe_div(merged["cfo_cur"], merged["rev_cur"])
    merged["fcf_margin_fy"]     = _safe_div(
        merged["cfo_cur"] - merged["capex_cur"].fillna(0),
        merged["rev_cur"],
    )
    # capex가 완전 NaN인 경우 fcf_margin도 NaN 처리
    merged.loc[merged["capex_cur"].isna(), "fcf_margin_fy"] = np.nan

    fb_cols = ["ticker", "sales_yoy_fy", "op_income_yoy_fy",
               "cfo_margin_fy", "fcf_margin_fy"]
    return merged[fb_cols].copy()


def _scores_path(target_year: int) -> Path:
    return PROCESSED / f"fin_scores_v2_{target_year}_{FS_DIV}_with_mc_with_price.parquet"


def main(target_year: int, prior_year: int, dry_run: bool) -> None:
    scores_file = _scores_path(target_year)
    if not scores_file.exists():
        raise FileNotFoundError(f"스코어 파케이를 찾을 수 없습니다: {scores_file}")

    print(f"[INFO] 스코어 파케이 로드: {scores_file}")
    scores = pd.read_parquet(scores_file)
    scores["ticker"] = scores["ticker"].astype(str).str.zfill(6)
    print(f"       행 수: {len(scores):,}  /  종목 수: {scores['ticker'].nunique():,}")

    # ── FY 대체값 계산 ──────────────────────────────────────────────────────
    print(f"[INFO] FY 대체값 계산 ({prior_year} → {target_year})")
    fallback = _build_fy_fallback(target_year, prior_year)
    print(f"       대체값 보유 종목: {len(fallback):,}")

    # ── 패치 대상 식별: NULL인 ALL rows ──────────────────────────────────────
    # 2025 파케이처럼 분기 행(Q1/Q3)이 최신 행이 되는 경우
    # rolling TTM 계산에 필요한 2024 데이터가 없어 최신 행이 null이 됨.
    # 따라서 "최신 행만" 이 아닌 "해당 ticker의 모든 null 행"을 FY 기반 값으로 채움.
    scores["as_of"] = pd.to_datetime(scores["as_of"])

    METRIC_MAP = {
        "sales_yoy":     "sales_yoy_fy",
        "op_income_yoy": "op_income_yoy_fy",
        "cfo_margin":    "cfo_margin_fy",
        "fcf_margin":    "fcf_margin_fy",
    }

    fb_by_ticker = fallback.set_index("ticker")

    patch_log_rows = []
    for metric, fy_col in METRIC_MAP.items():
        if metric not in scores.columns:
            print(f"[WARN] '{metric}' 컬럼이 스코어 파케이에 없습니다. 건너_skip.")
            continue

        # 전체 parquet에서 metric이 null인 모든 행
        null_row_indices = scores.index[scores[metric].isna()].tolist()

        patched_count = 0
        logged_tickers: set = set()   # 로그는 ticker당 1번만 기록 (중복 방지)
        for idx in null_row_indices:
            ticker = scores.at[idx, "ticker"]
            if ticker not in fb_by_ticker.index:
                continue
            fb_val = fb_by_ticker.at[ticker, fy_col]
            if pd.isna(fb_val):
                continue

            if not dry_run:
                scores.at[idx, metric] = float(fb_val)
            if ticker not in logged_tickers:
                patch_log_rows.append({
                    "ticker": ticker,
                    "metric": metric,
                    "new_value": float(fb_val),
                    "source": f"FY_{target_year}_annual",
                })
                logged_tickers.add(ticker)
            patched_count += 1

        print(f"  {metric:20s}: 행 {patched_count:4d}개 패치 {'(dry_run — 미저장)' if dry_run else ''}")

    # ── 패치 후 percentile + 필라 재계산 ─────────────────────────────────
    if not dry_run and patch_log_rows:
        print("[INFO] percentile_scores + pillar_and_overall 재계산 중...")

        # price, market_cap 등 비스코어 컬럼 분리
        score_input_cols = [
            "ticker", "as_of",
            "opm", "roa", "sales_yoy", "op_income_yoy",
            "debt_equity", "current_ratio", "cfo_margin", "fcf_margin",
            "per", "pbr", "asset_turnover", "cfo_to_assets",
            "roa_lag4", "debt_equity_lag4", "current_ratio_lag4",
            "opm_lag4", "asset_turnover_lag4",
            "market_cap", "ttm_net_income_proxy",
        ]
        # 없는 컬럼 제외
        avail_input = [c for c in score_input_cols if c in scores.columns]

        feats = scores[avail_input].copy()
        rescored = percentile_scores(feats, group_col=None)
        rescored = pillar_and_overall(rescored)

        # 재계산된 score 컬럼만 원본에 덮어씀 (원본 컬럼 보존)
        score_derived = [c for c in rescored.columns if c not in avail_input]
        for c in score_derived:
            scores[c] = rescored[c].values

        print(f"       업데이트된 파생 컬럼 수: {len(score_derived)}")

        # ── 저장 ────────────────────────────────────────────────────────────
        scores.to_parquet(scores_file, index=False)
        print(f"[OK] 저장 완료: {scores_file}")
    elif dry_run:
        print("[DRY_RUN] 실제 저장은 수행하지 않았습니다.")
    else:
        print("[INFO] 패치 대상 없음 — 파일 변경 없이 종료합니다.")

    # ── 패치 로그 CSV 내보냄 ─────────────────────────────────────────────
    if patch_log_rows:
        log_df = pd.DataFrame(patch_log_rows)
        log_path = PROCESSED / f"patch_log_growth_cf_{target_year}.csv"
        log_df.to_csv(log_path, index=False, encoding="utf-8-sig")
        print(f"[OK] 패치 로그: {log_path}  (종목 수: {log_df['ticker'].nunique():,})")

        # 요약 출력
        print("\n[패치 요약]")
        summary = (
            log_df.groupby("metric")
            .agg(tickers=("ticker", "count"),
                 avg_new=("new_value", "mean"))
            .reset_index()
        )
        print(summary.to_string(index=False))
    else:
        print("[INFO] 패치된 데이터가 없습니다.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="null 성장성·현금흐름 지표 FY 연간 데이터로 패치")
    ap.add_argument("--target_year", type=int, default=2024,
                    help="패치 대상 연도 (기본값: 2024)")
    ap.add_argument("--prior_year",  type=int, default=None,
                    help="직전 연도 (기본값: target_year - 1)")
    ap.add_argument("--dry_run", action="store_true",
                    help="지정 시 실제 저장 없이 패치 예상 결과만 출력")
    args = ap.parse_args()

    prior = args.prior_year if args.prior_year is not None else args.target_year - 1
    main(target_year=args.target_year, prior_year=prior, dry_run=args.dry_run)
