from __future__ import annotations

from pathlib import Path
import pandas as pd
from tqdm import tqdm
import FinanceDataReader as fdr

from src.common.io import save_parquet
from src.common.universe import load_universe_csv


def fetch_one(ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
    df = fdr.DataReader(ticker, start, end)

    # FDR이 빈 DF를 주는 케이스 방어
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "volume"])

    df = df.reset_index().rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )

    # 날짜/티커 정규화
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = str(ticker).zfill(6)

    # 필요한 컬럼만
    df = df[["date", "ticker", "open", "high", "low", "close", "volume"]]

    # (선택) 데이터 품질 최소 필터: 전부 NaN이거나 행이 너무 적으면 버림
    if df[["open", "high", "low", "close"]].isna().all(axis=None):
        return pd.DataFrame(columns=df.columns)

    return df


def main():
    # ✅ FDR 전체 유니버스
    universe_path = "universe/stock_krx_all.csv"

    # ✅ 기간: FDR은 과거도 되지만, 너무 오래 잡으면 느림
    start = "2014-05-01"
    end = None

    # ✅ output
    out_path = Path("data/raw/stock/ohlcv.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ✅ universe 로드 (None/empty 체크를 먼저!)
    u = load_universe_csv(universe_path)
    if u is None or len(u) == 0:
        raise ValueError(
            f"[ERR] Universe is empty or not found: {universe_path}\n"
            f"Hint: 먼저 scripts.99_utils.00_make_universe_stock_fdr_all 실행 후 CSV가 생성되고 ticker가 채워져야 합니다."
        )

    if "ticker" not in u.columns:
        raise ValueError(f"[ERR] Universe CSV has no 'ticker' column. columns={u.columns.tolist()}")

    tickers = u["ticker"].astype(str).str.zfill(6).unique().tolist()
    print(f"[OK] Loaded universe: {universe_path} | n_tickers={len(tickers):,}")

    frames: list[pd.DataFrame] = []
    failed = 0

    for t in tqdm(tickers, desc="Fetching STOCK"):
        try:
            df1 = fetch_one(t, start, end)
            if df1 is not None and len(df1) > 0:
                frames.append(df1)
            else:
                # 빈 DF도 실패로 카운트(원하면 주석 처리 가능)
                failed += 1
        except Exception as e:
            failed += 1
            print(f"[WARN] failed ticker={t} err={e}")

    if not frames:
        raise RuntimeError(
            "[ERR] No objects to concatenate (all fetch failed or returned empty).\n"
            f"Universe n={len(tickers)} | failed={failed}\n"
            "Hint: 네트워크/FDR 제한/티커 포맷 문제 여부를 확인하세요."
        )

    df_all = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["date", "ticker"])
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )

    save_parquet(df_all, out_path)
    print(
        f"[OK] Saved STOCK OHLCV: {out_path} "
        f"rows={len(df_all):,} tickers={df_all['ticker'].nunique():,} failed={failed:,}"
    )


if __name__ == "__main__":
    main()