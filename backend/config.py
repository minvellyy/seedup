"""
backend/config.py — CrewAI 에이전트 경로 설정

fin_structured_model, stock_direction_model 이 backend/ 하위에 위치합니다.

경로 우선순위:
  1. 환경변수 (backend/.env 또는 OS 환경변수)
  2. 자동 감지 기본값 (상대 경로 기반)

이동 시 backend/.env 의 FIN_MODEL_DIR, SIGNAL_PACK_PATH 만 수정하면 됩니다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── .env 자동 로드 ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve().parent   # backend/
    # backend/.env 우선, 없으면 루트 .env
    for _dotenv in (_here / ".env", _here.parent / ".env"):
        if _dotenv.exists():
            load_dotenv(_dotenv, override=False)
            break
except ImportError:
    pass

# ── 서브모델 루트 = backend/ ──────────────────────────────────────────────────
_DEFAULT_CREWAI_ROOT = Path(__file__).resolve().parent  # backend/

CREWAI_ROOT: Path = Path(
    os.getenv("CREWAI_ROOT", str(_DEFAULT_CREWAI_ROOT))
)

# ── 서브모델 경로 ─────────────────────────────────────────────────────────────
FIN_MODEL_DIR: Path = Path(
    os.getenv("FIN_MODEL_DIR", str(CREWAI_ROOT / "fin_structured_model"))
)

SIGNAL_PACK_PATH: Path = Path(
    os.getenv(
        "SIGNAL_PACK_PATH",
        str(
            CREWAI_ROOT
            / "stock_direction_model"
            / "data"
            / "outputs"
            / "signal_pack"
            / "signal_pack_latest.csv"
        ),
    )
)

UNSTRUCTURED_MODEL_DIR: Path = Path(
    os.getenv("UNSTRUCTURED_MODEL_DIR", str(CREWAI_ROOT / "unstructured_model"))
)

NEWS_MODEL_DIR: Path = Path(
    os.getenv("NEWS_MODEL_DIR", str(CREWAI_ROOT / "news_model"))
)

# WORKSPACE_ROOT: 하위 호환성 (manager_agent 내부에서 참조)
WORKSPACE_ROOT: Path = CREWAI_ROOT
