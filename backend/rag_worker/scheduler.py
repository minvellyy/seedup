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
_RUN_MARKER_DIR = _BACKEND_DIR / "portfolio_cache"  # 실행 마커 파일 저장 디렉터리

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ── 당일 실행 여부 체크 ────────────────────────────────────────────────────────

def _already_ran_today(job_name: str) -> bool:
    """오늘 날짜 마커 파일이 있으면 True (이미 실행됨)."""
    _RUN_MARKER_DIR.mkdir(parents=True, exist_ok=True)
    marker = _RUN_MARKER_DIR / f".{job_name}_{datetime.now():%Y%m%d}.done"
    return marker.exists()


def _mark_ran_today(job_name: str) -> None:
    """오늘 날짜 마커 파일 생성 + 전날 마커 파일 삭제."""
    _RUN_MARKER_DIR.mkdir(parents=True, exist_ok=True)
    today_marker = _RUN_MARKER_DIR / f".{job_name}_{datetime.now():%Y%m%d}.done"
    today_marker.touch()
    # 7일 이상 된 마커 파일 정리
    for old in _RUN_MARKER_DIR.glob(f".{job_name}_*.done"):
        if old != today_marker:
            try:
                old.unlink()
            except Exception:
                pass


# ── 뉴스 ─────────────────────────────────────────────────────────────────────

def _get_news_days_back() -> int:
    """news_raw 테이블의 마지막 published_at 기준으로 오늘까지 몇 일치를 가져올지 계산."""
    try:
        from news_model.pipeline_news_analysis_mvp import get_mysql
        conn = get_mysql()
        cur = conn.cursor()
        cur.execute("SELECT MAX(published_at) FROM news_raw")
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            last_date = row[0] if isinstance(row[0], datetime) else datetime.strptime(str(row[0]), "%Y-%m-%d %H:%M:%S")
            days_back = (datetime.now() - last_date).days + 1  # 마지막 날 포함
            return max(days_back, 1)
    except Exception as e:
        print(f"[WARN] DB 마지막 날짜 조회 실패, 기본값 1일 사용: {e}")
    return 1


def run_news_daily_batch() -> None:
    """마지막 DB 날짜 이후 ~ 오늘까지 뉴스 수집 → LLM 분석 → 90일 초과 항목 삭제."""
    if _already_ran_today("news"):
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 뉴스 daily_batch — 오늘 이미 실행됨, 건너뜀")
        return
    from news_model.pipeline_news_analysis_mvp import daily_batch

    days_back = _get_news_days_back()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 뉴스 daily_batch 시작 (최근 {days_back}일치)")
    daily_batch(days_back=days_back, retention_days=90)
    _mark_ran_today("news")
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
    if _already_ran_today("reports"):
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 리포트 ETL — 오늘 이미 실행됨, 건너뜀")
        return
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 리포트 ETL 시작 (최근 {days}일)")
    try:
        crawler, parser, embedder = _load_reports_modules()
        crawler.download_all_naver_reports(
            base_dir=str(_BACKEND_DIR / "reports"), days_to_fetch=days
        )
        parser.run_parser()
        embedder.run_embedding()
        _mark_ran_today("reports")
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 리포트 ETL 완료")
    except Exception as exc:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 리포트 ETL 실패: {exc}")


def run_reports_init() -> None:
    """30일치 리포트 초기 수집 (최초 1회)."""
    run_reports_etl(days=30)
