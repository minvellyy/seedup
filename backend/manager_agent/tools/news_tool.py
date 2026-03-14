# manager_agent/tools/news_tool.py
#
# 뉴스 RAG 파이프라인 연동 툴.
# news_model.pipeline_news_analysis_mvp 의 ChromaDB 인덱스에서
# 관련 뉴스를 실시간으로 검색해 CrewAI 에이전트에 제공한다.
#
# ── 주요 공개 심볼 ─────────────────────────────────────────────────────
#   news_rag_search          : CrewAI @tool — manager_agent/crew.py 에서 사용
#   run_news_worker(query)   : 독립 실행용 함수 (테스트 / 스크립트)
#
from __future__ import annotations

import json
import sys
from pathlib import Path

from crewai import Agent, Task, Crew
from crewai.tools import tool

# backend/ 를 sys.path 에 추가 (news_model 이 backend/ 안으로 이동됨)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from news_model.pipeline_news_analysis_mvp import search_news_context


@tool("news_rag_search")
def news_rag_search(query: str) -> str:
    """
    뉴스 RAG 저장소에서 관련 뉴스를 검색한다.
    입력은 한국어 자연어 질의 문자열이다.
    예) '삼성전자 HBM 수요', '반도체 업황', '원달러 환율 상승'
    """
    results = search_news_context(query, n_results=5)

    if not results:
        return "관련 뉴스가 없습니다."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[RESULT {i}]")
        lines.append(r["doc"])
        lines.append(f"meta: {json.dumps(r['meta'], ensure_ascii=False)}")
        lines.append("-" * 60)

    return "\n".join(lines)


# ── 독립 실행용 ──────────────────────────────────────────────────────────

def _make_news_agent(llm=None) -> Agent:
    kwargs = dict(
        role="SeedUp News RAG Worker",
        goal="질문과 관련된 최신 뉴스 근거를 검색해 구조화된 형태로 제공한다",
        backstory=(
            "너는 SeedUp의 뉴스 검색 전용 워커 에이전트다. "
            "뉴스 RAG 저장소에서 관련 기사를 찾아 제목, 요약, 테마, 리스크, 기회, 감성 정보를 정리해 "
            "매니저 에이전트가 최종 설명을 만들 수 있도록 근거를 제공한다. "
            "투자 판단이나 종목 추천은 하지 않는다."
        ),
        tools=[news_rag_search],
        verbose=True,
    )
    if llm is not None:
        kwargs["llm"] = llm
    return Agent(**kwargs)


def run_news_worker(query: str, llm=None) -> str:
    """뉴스 워커를 독립 실행해 query 관련 뉴스 브리프를 반환한다."""
    agent = _make_news_agent(llm)

    task = Task(
        description=(
            f"다음 질문과 관련된 뉴스 근거를 검색하고 정리하라: {query}\n\n"
            "반드시 아래 형식으로 정리하라:\n"
            "1. 핵심 뉴스 3~5건 요약\n"
            "2. 반복적으로 등장하는 리스크\n"
            "3. 반복적으로 등장하는 기회\n"
            "4. 전체적인 뉴스 톤(positive/negative/neutral)\n"
            "5. 매니저 에이전트가 활용할 수 있는 짧은 브리프"
        ),
        expected_output=(
            "뉴스 근거 요약, 주요 리스크, 주요 기회, 전체 톤, 매니저 브리프가 포함된 한국어 텍스트"
        ),
        agent=agent,
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    result = crew.kickoff()
    return str(result)


if __name__ == "__main__":
    sample_query = "HBM 수요 증가"
    output = run_news_worker(sample_query)
    print("\n" + "=" * 100)
    print("[FINAL OUTPUT]")
    print("=" * 100)
    print(output)
