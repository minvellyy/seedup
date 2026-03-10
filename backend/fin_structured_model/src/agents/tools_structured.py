# src/agents/tools_structured.py
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            f"[CMD FAIL] {' '.join(cmd)}\n--- STDOUT ---\n{p.stdout}\n--- STDERR ---\n{p.stderr}"
        )
    return p.stdout.strip()

def build_scores(target_year: int = 2024, base_year: int = 2023,
                 with_market_cap: bool = False, with_price: bool = False) -> str:
    cmd = [sys.executable, "-m", "scripts.build_scores",
           "--target_year", str(target_year),
           "--base_year", str(base_year)]
    if with_market_cap:
        cmd.append("--with_market_cap")
    if with_price:
        cmd.append("--with_price")
    return _run(cmd)

def fetch_market_cap(scores_path: str, out_path: str) -> str:
    return _run([sys.executable, "-m", "scripts.fetch_market_cap_yfinance",
                 "--scores_path", scores_path,
                 "--out_path", out_path])

def fetch_price_features(in_scores: str, start: str = "2022-01-01",
                         price_daily_out: str = "data/processed/price_daily_yf.parquet",
                         price_feat_out: str = "data/processed/price_features_asof.parquet") -> str:
    _run([sys.executable, "-m", "scripts.fetch_price_yfinance",
          "--in_scores", in_scores,
          "--start", start,
          "--out_path", price_daily_out])
    return _run([sys.executable, "-m", "scripts.build_price_features",
                 "--in_scores", in_scores,
                 "--price_daily", price_daily_out,
                 "--out_path", price_feat_out])

def export_report(ticker: str, as_of: str, in_path: str,
                  out_path: str = "data/processed/structured_report.json") -> str:
    return _run([sys.executable, "-m", "scripts.export_structured_report",
                 "--ticker", str(ticker),
                 "--as_of", str(as_of),
                 "--in_path", in_path,
                 "--out_path", out_path])

def read_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"not found: {path}")
    return p.read_text(encoding="utf-8")

def run_full_auto(ticker: str, as_of: str, target_year: int = 2024, base_year: int = 2023, fs_div: str = "CONSOL") -> str:
    return _run([sys.executable, "-m", "scripts.run_full_auto_structured",
                 "--ticker", str(ticker),
                 "--as_of", str(as_of),
                 "--target_year", str(target_year),
                 "--base_year", str(base_year),
                 "--fs_div", fs_div])