"""
rag_worker/scheduler.py

뉴스 + 리포트 일일 업데이트 작업 정의.
main.py 의 startup_event 에서 호출된다.
"""
from __future__ import annotations

import importlib
import sys
from datetime import datetime
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
_REPORTS_MODEL_DIR = str(_BACKEND_DIR / "reports_model")

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ── 뉴스 ─────────────────────────────────────────────────────────────────────

def run_news_daily_batch() -> None:
    """신규 뉴스 1일치 수집 → LLM 분석 → 90일 초과 항목 삭제."""
    from news_model.pipeline_news_analysis_mvp import smart_daily_batch

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 뉴스 daily_batch 시작")
    smart_daily_batch()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 뉴스 daily_batch 완료")


def run_news_init() -> None:
    """90일치 뉴스 초기 수집 및 DB 구축 (최초 1회)."""
    from news_model.pipeline_news_analysis_mvp import daily_batch, init_db

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 뉴스 초기 DB 구축 시작 (90일치)")
    init_db()
    daily_batch(days_back=90, retention_days=90)
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 뉴스 초기 DB 구축 완료")


# ── 증권사 리포트 ─────────────────────────────────────────────────────────────

def _load_reports_modules():
    if _REPORTS_MODEL_DIR not in sys.path:
        sys.path.insert(0, _REPORTS_MODEL_DIR)
    crawler = importlib.import_module("01_naver_report_crawler")
    parser = importlib.import_module("02_report_information_extractor")
    embedder = importlib.import_module("03_chroma_db_loader")
    return crawler, parser, embedder


def run_reports_etl(days: int = 1) -> None:
    """증권사 리포트 ETL: 크롤링 → PDF 파싱 → Chroma 임베딩."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 리포트 ETL 시작 (최근 {days}일)")
    try:
        crawler, parser, embedder = _load_reports_modules()
        crawler.download_all_naver_reports(
            base_dir=str(_BACKEND_DIR / "reports"), days_to_fetch=days
        )
        parser.run_parser()
        embedder.run_embedding()
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 리포트 ETL 완료")
    except Exception as exc:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 리포트 ETL 실패: {exc}")


def run_reports_init() -> None:
    """30일치 리포트 초기 수집 (최초 1회)."""
    run_reports_etl(days=30)
