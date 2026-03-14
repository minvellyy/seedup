"""
rag_worker/worker.py

세 가지 RAG 모델(ESG · 뉴스 · 증권사 리포트)을 통합한 CrewAI 워커 에이전트.
매니저 에이전트에서 임포트해 사용한다.

    from rag_worker.worker import rag_worker, run_rag_worker
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from crewai import Agent, Crew, Task

from rag_worker.tools.esg_tool import esg_analysis
from rag_worker.tools.news_tool import news_rag_search
from rag_worker.tools.reports_tool import reports_rag_search


def make_rag_worker(llm=None) -> Agent:
    """RAG 워커 에이전트 인스턴스를 생성한다."""
    kwargs: dict = dict(
        role="SeedUp RAG 비정형 데이터 워커",
        goal=(
            "ESG 보고서, 최신 뉴스, 증권사 리포트 세 가지 RAG 저장소에서 "
            "관련 근거 데이터를 검색하고 구조화된 형태로 제공한다."
        ),
        backstory=(
            "너는 SeedUp의 비정형 데이터 전담 RAG 워커 에이전트다. "
            "ESG 리스크·기대요인, 최신 뉴스 시장 센티멘트, 증권사 리포트 인사이트를 "
            "검색하여 매니저 에이전트가 종목·포트폴리오 추천 근거와 기업·산업 분석을 "
            "자연어로 제공할 수 있도록 돕는다. "
            "투자 판단이나 종목 추천은 직접 하지 않는다."
        ),
        tools=[esg_analysis, news_rag_search, reports_rag_search],
        verbose=True,
    )
    if llm is not None:
        kwargs["llm"] = llm
    return Agent(**kwargs)


# 기본 싱글턴 인스턴스 (manager_agent crew.py 에서 직접 참조)
rag_worker: Agent = make_rag_worker()


def run_rag_worker(query: str, ticker: str | None = None, llm=None) -> str:
    """
    RAG 워커를 실행하여 비정형 분석 근거를 반환한다.

    Args:
        query:  자연어 질의 (예: '삼성전자 HBM 수요 전망과 ESG 리스크')
        ticker: 종목코드. ESG 분석이 필요한 경우 전달 (예: '005930')
        llm:    CrewAI LLM 객체. None 이면 환경변수 기반 기본 모델 사용.
    """
    agent = make_rag_worker(llm)
    ticker_line = f"\n종목코드: {str(ticker).zfill(6)}" if ticker else ""

    task = Task(
        description=(
            f"다음 질문과 관련된 비정형 데이터 근거를 검색하고 정리하라: {query}{ticker_line}\n\n"
            "사용 가능한 도구:\n"
            "- esg_analysis      : 종목 ESG 리스크·기대요인 조회 (ticker 필요)\n"
            "- news_rag_search   : 최신 뉴스 시장 센티멘트 검색\n"
            "- reports_rag_search: 증권사 리포트 인사이트 검색\n\n"
            "아래 형식으로 반드시 정리하라:\n"
            "1. ESG 분석 (ticker 제공 시): 리스크 요인, 기대 요인\n"
            "2. 뉴스 브리프: 핵심 뉴스 3~5건, 반복 리스크, 반복 기회, 전체 톤\n"
            "3. 리포트 브리프: 관련 증권사 리포트 핵심 인사이트\n"
            "4. 매니저 에이전트용 종합 브리프"
        ),
        expected_output="ESG 분석, 뉴스 브리프, 리포트 브리프, 종합 브리프가 포함된 한국어 텍스트",
        agent=agent,
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    return str(crew.kickoff())
