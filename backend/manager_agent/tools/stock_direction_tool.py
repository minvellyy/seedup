# manager_agent/tools/stock_direction_tool.py
from __future__ import annotations

import json
import os
from pathlib import Path

from crewai.tools import tool

from config import SIGNAL_PACK_PATH as _SIGNAL_PACK_CSV


def _load_signal_pack():
    import pandas as pd
    if not _SIGNAL_PACK_CSV.exists():
        return None
    return pd.read_csv(_SIGNAL_PACK_CSV, dtype={"ticker": str})


def _get_instruments_tickers() -> dict[str, str]:
    """DB instruments 테이블에서 {stock_code: name} 딕셔너리를 반환합니다."""
    try:
        import pymysql
        from dotenv import load_dotenv
        _here = Path(__file__).resolve().parent.parent.parent  # backend/
        for _env in (_here / ".env", _here.parent / ".env"):
            if _env.exists():
                load_dotenv(_env, override=False)
                break
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            db=os.getenv("DB_NAME", "seedup_db"),
            charset="utf8mb4",
        )
        with conn.cursor() as cur:
            cur.execute("SELECT stock_code, name FROM instruments")
            rows = cur.fetchall()
        conn.close()
        return {str(r[0]).zfill(6): r[1] for r in rows}
    except Exception:
        return {}

@tool("read_stock_direction_signal")
def read_stock_direction_signal(ticker: str) -> str:
    """stock_direction_model의 signal_pack_latest.csv에서 특정 종목의 최신 방향성 예측 신호를 반환합니다.
    p_up(상승확률 0~1), rank_overall(전체 순위), p_market_up(시장 상승확률), regime(시장 레짐) 등을 포함합니다.
    Args:
        ticker: 종목코드 (예: '005930')
    """
    import pandas as pd

    df = _load_signal_pack()
    if df is None:
        return json.dumps({
            "error": "NOT_FOUND",
            "message": f"signal_pack_latest.csv 없음: {_SIGNAL_PACK_CSV}. stock_direction_model 예측을 먼저 실행하세요.",
        })

    t = str(ticker).zfill(6)
    sub = df[df["ticker"] == t]
    if sub.empty:
        return json.dumps({"error": "TICKER_NOT_FOUND", "ticker": t, "total_tickers_in_pack": len(df)})

    row = sub.iloc[-1]
    name_val = str(row["name"]) if "name" in row.index and pd.notna(row["name"]) else None
    # name이 없으면 DB에서 보완
    if not name_val:
        instruments = _get_instruments_tickers()
        name_val = instruments.get(t)
    result = {
        "ticker": t,
        "name": name_val,
        "date": str(row.get("date", "")),
        "asset_type": str(row.get("asset_type", "")),
        "horizon": str(row["horizon"]) if "horizon" in row.index and pd.notna(row["horizon"]) else None,
        "p_up": float(row["p_up"]) if "p_up" in row.index and pd.notna(row["p_up"]) else None,
        "p_adj": float(row["p_adj"]) if "p_adj" in row.index and pd.notna(row["p_adj"]) else None,
        "p_market_up": float(row["p_market_up"]) if "p_market_up" in row.index and pd.notna(row["p_market_up"]) else None,
        "regime": str(row["regime"]) if "regime" in row.index and pd.notna(row["regime"]) else None,
        "rank_overall": int(row["rank_overall"]) if "rank_overall" in row.index and pd.notna(row["rank_overall"]) else None,
        "rank_in_asset": int(row["rank_in_asset"]) if "rank_in_asset" in row.index and pd.notna(row["rank_in_asset"]) else None,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool("get_top_direction_signals")
def get_top_direction_signals(asset_type: str = "stock", top_n: int = 10) -> str:
    """전체 종목 중 상승 확률(p_adj) 기준 상위 n개의 방향성 예측 신호를 반환합니다.
    DB instruments 테이블에 등록된 종목만 대상으로 필터링합니다.
    Args:
        asset_type: 'stock', 'etf', 'all' 중 하나 (기본: 'stock')
        top_n: 반환할 상위 종목 수 (기본: 10)
    """
    import pandas as pd

    df = _load_signal_pack()
    if df is None:
        return json.dumps({"error": "NOT_FOUND"})

    if asset_type != "all":
        df = df[df["asset_type"] == asset_type]

    # DB instruments 종목만 필터링 + 이름 보완
    instruments = _get_instruments_tickers()
    if instruments:
        df = df[df["ticker"].str.zfill(6).isin(instruments)]
        # signal_pack에 name이 없는 종목은 DB에서 가져온 이름으로 보완
        if "name" in df.columns:
            missing_mask = df["name"].isna() | (df["name"] == "")
            df = df.copy()
            df.loc[missing_mask, "name"] = df.loc[missing_mask, "ticker"].str.zfill(6).map(instruments)

    df_top = df.sort_values("rank_overall").head(int(top_n))
    cols = [c for c in ["ticker", "name", "date", "asset_type", "p_up", "p_adj", "rank_overall"] if c in df_top.columns]
    records = df_top[cols].to_dict(orient="records")

    return json.dumps({
        "asset_type": asset_type,
        "top_n": int(top_n),
        "total_filtered": len(df),
        "as_of": str(df_top["date"].max()) if not df_top.empty and "date" in df_top else None,
        "signals": records,
    }, ensure_ascii=False, indent=2)
