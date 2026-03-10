from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException

app = FastAPI(title="Structured Report API")

REPORT_DIR = Path("data/processed/reports/latest")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

PY = sys.executable
TTL_HOURS = 24


def report_path(ticker: str) -> Path:
    return REPORT_DIR / f"{str(ticker).zfill(6)}.json"


def is_stale(p: Path, ttl_hours: int = TTL_HOURS) -> bool:
    if not p.exists():
        return True
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    return datetime.now() - mtime > timedelta(hours=ttl_hours)


def run_refresh(ticker: str):
    subprocess.run([
        PY, "-m", "scripts.refresh_single_ticker",
        "--ticker", str(ticker).zfill(6),
        "--as_of", "latest",
        "--scores_path", "data/processed/fin_scores_v2_2024_CONSOL_with_mc_with_price.parquet",
        "--out_report", str(report_path(ticker))
    ], check=False)


@app.get("/report/{ticker}")
def get_report(ticker: str, background_tasks: BackgroundTasks):
    ticker = str(ticker).zfill(6)
    p = report_path(ticker)

    # 캐시 없으면 동기 생성
    if not p.exists():
        run_refresh(ticker)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"report not available for {ticker}")

    # 캐시 반환
    data = json.loads(p.read_text(encoding="utf-8"))

    # stale이면 백그라운드 refresh
    if is_stale(p):
        background_tasks.add_task(run_refresh, ticker)
        data.setdefault("meta", {})
        data["meta"]["stale"] = True
        data["meta"]["refresh_scheduled"] = True
    else:
        data.setdefault("meta", {})
        data["meta"]["stale"] = False

    return data


@app.post("/report/{ticker}/refresh")
def refresh_report(ticker: str):
    ticker = str(ticker).zfill(6)
    run_refresh(ticker)
    p = report_path(ticker)
    if not p.exists():
        raise HTTPException(status_code=500, detail=f"refresh failed for {ticker}")
    return json.loads(p.read_text(encoding="utf-8"))