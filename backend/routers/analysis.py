"""FastAPI 라우터 — CrewAI 매니저 에이전트 분석 엔드포인트.

main.py에서 include_router() 로 등록:

    from routers.analysis import router as analysis_router
    app.include_router(analysis_router, prefix="/api/v1")

엔드포인트:
    POST /analysis/report          : 단일 종목 통합 투자 리포트 (full/signal/fin/summary/stock_detail)
    GET  /analysis/report/{ticker} : 빠른 방향성 시그널 (signal 모드)
    GET  /analysis/top-signals     : 상위 방향성 종목 리스트
"""
from __future__ import annotations

import json
import os
import sys

# ── backend/ 를 sys.path에 추가 (config, manager_agent import용) ────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# ── CrewAI 관련 import (패키지 없으면 graceful degradation) ─────────────────
try:
    from manager_agent.crew import run_manager_analysis
    _CREW_AVAILABLE = True
except Exception as _e:
    _CREW_AVAILABLE = False
    _CREW_ERR = str(_e)

router = APIRouter(prefix="/analysis", tags=["analysis"])


# ─────────────────────────────────────────────────────────────────────────────
# 요청 / 응답 스키마
# ─────────────────────────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    ticker: str = Field(..., description="종목코드 (예: 005930)")
    as_of: Optional[str] = Field(None, description="기준일 YYYY-MM-DD. 없으면 최신 데이터 사용.")
    mode: Literal["full", "signal", "fin", "summary", "stock_detail"] = Field(
        "full",
        description=(
            "full=전체분석, signal=방향성만, fin=재무만, "
            "summary=재요약, stock_detail=투자원칙적합도 포함 상세"
        ),
    )
    lang: Literal["ko", "en"] = Field("ko", description="리포트 언어")
    style: Literal["formal", "friendly"] = Field("formal", description="리포트 문체")
    context_description: Optional[str] = Field(None, description="이 분석이 사용될 화면 설명")
    user_profile_json: Optional[str] = Field(None, description="[stock_detail 전용] UserProfileSummary JSON 문자열")
    stock_item_json: Optional[str] = Field(None, description="[stock_detail 전용] StockItem JSON 문자열")


class AnalysisResponse(BaseModel):
    ticker: str
    mode: str
    report: str                          # LLM 생성 투자 리포트 (JSON 문자열 또는 자연어)
    generated_at: str


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _get_llm():
    """MANAGER_LLM_MODEL 환경변수 기반 LLM 객체 생성."""
    model = os.getenv("MANAGER_LLM_MODEL", "openai/gpt-4o-mini")
    try:
        from crewai import LLM
        return LLM(model=model)
    except (ImportError, AttributeError):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model.replace("openai/", ""))


def _check_crew():
    if not _CREW_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"CrewAI 에이전트를 로드할 수 없습니다: {_CREW_ERR}. "
                   "lc_env 환경 및 manager_agent 패키지를 확인하세요.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/report",
    response_model=AnalysisResponse,
    summary="종목 통합 투자 리포트 생성",
    description="CrewAI 매니저 에이전트가 재무·방향성·비정형 데이터를 종합하여 투자 리포트를 생성합니다.",
)
def create_analysis_report(req: AnalysisRequest) -> AnalysisResponse:
    _check_crew()
    from datetime import datetime

    # stock_detail 모드에서 user_profile_json 미제공 시 샘플 사용
    user_profile_json = req.user_profile_json
    if req.mode == "stock_detail" and not user_profile_json:
        user_profile_json = json.dumps({
            "risk_tier": "위험중립형",
            "grade": "3등급",
            "horizon_years": 3,
            "goal": "자산증식",
            "deployment": "분산투자",
            "monthly_contribution_krw": 500000,
            "total_assets_krw": 30000000,
            "dividend_pref_1to5": 3,
            "account_type": "일반",
        }, ensure_ascii=False)

    try:
        llm = _get_llm()
        result = run_manager_analysis(
            llm=llm,
            ticker=req.ticker,
            as_of=req.as_of,
            explain_lang=req.lang,
            explain_style=req.style,
            mode=req.mode,
            context_description=req.context_description,
            user_profile_json=user_profile_json,
            stock_item_json=req.stock_item_json,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 실행 오류: {e}")

    return AnalysisResponse(
        ticker=req.ticker,
        mode=req.mode,
        report=result,
        generated_at=datetime.now().isoformat(),
    )


@router.get(
    "/report/{ticker}",
    response_model=AnalysisResponse,
    summary="빠른 방향성 시그널 조회",
    description="signal 모드로 특정 종목의 방향성 예측 신호를 빠르게 반환합니다.",
)
def get_signal_report(
    ticker: str,
    lang: str = Query("ko"),
    style: str = Query("formal"),
) -> AnalysisResponse:
    _check_crew()
    from datetime import datetime

    try:
        llm = _get_llm()
        result = run_manager_analysis(
            llm=llm,
            ticker=ticker,
            mode="signal",
            explain_lang=lang,
            explain_style=style,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 실행 오류: {e}")

    return AnalysisResponse(
        ticker=ticker,
        mode="signal",
        report=result,
        generated_at=datetime.now().isoformat(),
    )


@router.get(
    "/top-signals",
    summary="상위 방향성 종목 리스트",
    description="signal_pack_latest.csv에서 p_adj 기준 상위 종목을 반환합니다. LLM 호출 없이 빠르게 응답합니다.",
)
def get_top_signals(
    asset_type: str = Query("stock", description="'stock' | 'etf' | 'all'"),
    top_n: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    try:
        from manager_agent.tools.stock_direction_tool import get_top_direction_signals
        raw = get_top_direction_signals.run(asset_type, top_n)
        return json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시그널 조회 오류: {e}")
