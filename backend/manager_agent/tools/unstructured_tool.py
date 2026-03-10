# manager_agent/tools/unstructured_tool.py
#
# 비정형 데이터 분석 모델 연동 툴.
# 현재 팀원이 개발 중이므로 PENDING placeholder를 반환합니다.
# 모델 완성 후: _UNSTRUCTURED_MODEL_DIR 아래에 아래 경로 중 하나에 결과 파일을 위치시키면
# 자동으로 실제 데이터를 읽어 반환합니다.
#
#   <UNSTRUCTURED_MODEL_DIR>/data/outputs/<ticker>_sentiment.json
#   <UNSTRUCTURED_MODEL_DIR>/data/outputs/unstructured_report.json  (리스트 형태)
#   <UNSTRUCTURED_MODEL_DIR>/data/processed/unstructured_report.json (리스트 형태)
#
from __future__ import annotations

import json
from pathlib import Path

from crewai.tools import tool

from config import UNSTRUCTURED_MODEL_DIR as _UNSTRUCTURED_MODEL_DIR


def _load_unstructured(ticker: str) -> dict | None:
    """비정형 모델 출력 파일에서 해당 종목 데이터를 읽어 반환합니다."""
    t = str(ticker).zfill(6)
    candidates = [
        _UNSTRUCTURED_MODEL_DIR / "data" / "outputs" / f"{t}_sentiment.json",
        _UNSTRUCTURED_MODEL_DIR / "data" / "outputs" / "unstructured_report.json",
        _UNSTRUCTURED_MODEL_DIR / "data" / "processed" / "unstructured_report.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if isinstance(data, dict) and str(data.get("ticker", "")).zfill(6) == t:
            return data
        if isinstance(data, list):
            matches = [r for r in data if str(r.get("ticker", "")).zfill(6) == t]
            if matches:
                return matches[-1]
    return None


@tool("read_unstructured_analysis")
def read_unstructured_analysis(ticker: str) -> str:
    """비정형 데이터 분석 모델의 결과를 조회합니다.
    뉴스·공시·텍스트 기반 센티멘트 점수와 주요 이슈를 반환합니다.
    해당 모듈이 아직 개발 완료되지 않은 경우 status='PENDING'을 반환합니다.
    Args:
        ticker: 종목코드 (예: '005930')
    """
    result = _load_unstructured(ticker)
    if result:
        result.setdefault("status", "AVAILABLE")
        return json.dumps(result, ensure_ascii=False, indent=2)

    return json.dumps({
        "ticker": str(ticker).zfill(6),
        "status": "PENDING",
        "message": (
            "비정형 데이터 분석 모듈은 현재 개발 중입니다. "
            "향후 뉴스·공시·SNS 텍스트 기반 센티멘트 분석이 제공될 예정입니다."
        ),
        "sentiment_score": None,
        "key_issues": [],
        "last_updated": None,
    }, ensure_ascii=False, indent=2)
