"""
rag_worker — ESG · 뉴스 · 증권사 리포트 통합 RAG 워커 패키지
esg_model, news_model, reports_model 이 모두 backend/ 안에 있으므로
backend/ 만 sys.path 에 추가하면 된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
