# src/agents/crew_structured.py
from __future__ import annotations
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool

from src.agents.tools_structured import (
    build_scores, fetch_market_cap, fetch_price_features, export_report, read_text
)

@tool("build_scores_tool")
def build_scores_tool(target_year: int, base_year: int, with_market_cap: bool, with_price: bool) -> str:
    return build_scores(target_year=target_year, base_year=base_year, with_market_cap=with_market_cap, with_price=with_price)

@tool("fetch_market_cap_tool")
def fetch_market_cap_tool(scores_path: str, out_path: str) -> str:
    return fetch_market_cap(scores_path=scores_path, out_path=out_path)

@tool("fetch_price_features_tool")
def fetch_price_features_tool(in_scores: str, start: str) -> str:
    return fetch_price_features(in_scores=in_scores, start=start)

@tool("export_report_tool")
def export_report_tool(ticker: str, as_of: str, in_path: str, out_path: str) -> str:
    return export_report(ticker=ticker, as_of=as_of, in_path=in_path, out_path=out_path)

@tool("read_report_tool")
def read_report_tool(path: str) -> str:
    return read_text(path)

def run_structured_crewai(
    llm,
    ticker: str,
    as_of: str,
    target_year: int = 2024,
    base_year: int = 2023,
    with_market_cap: bool = True,
    with_price: bool = True,
    # build_scores.py의 출력 규칙을 그대로 사용(태그)
    fs_div: str = "CONSOL",
) -> str:
    pipeline_agent = Agent(
        role="StructuredPipelineAgent",
        goal="정형 스코어 파일을 최신 상태로 생성한다(재무 캐시 기반).",
        tools=[build_scores_tool, fetch_market_cap_tool, fetch_price_features_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    report_agent = Agent(
        role="StructuredReportAgent",
        goal="ticker/as_of에 대해 JSON 리포트(+NLG narrative)를 생성하고 반환한다.",
        tools=[export_report_tool, read_report_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    # build_scores.py 출력 파일명 규칙과 맞춤
    tag = []
    if with_market_cap: tag.append("with_mc")
    if with_price: tag.append("with_price")
    tag_s = "_".join(tag)
    scores_path = f"data/processed/fin_scores_v2_{target_year}_{fs_div}{('_' + tag_s) if tag_s else ''}.parquet"

    t1 = Task(
        description=(
            f"1) (선택) market_cap/price 피처를 준비하고\n"
            f"2) build_scores_tool을 호출해 scores를 생성한다.\n"
            f"파라미터: target_year={target_year}, base_year={base_year}, with_market_cap={with_market_cap}, with_price={with_price}\n"
            f"참고 경로: market_cap.parquet / price_features_asof.parquet\n"
        ),
        expected_output="scores 생성 로그",
        agent=pipeline_agent,
    )

    t2 = Task(
        description=(
            f"export_report_tool로 리포트를 생성한다.\n"
            f"ticker={ticker}, as_of={as_of}, in_path={scores_path}, out_path=data/processed/structured_report.json\n"
            f"생성 후 read_report_tool로 JSON 텍스트를 반환한다."
        ),
        expected_output="structured_report.json 내용(JSON string)",
        agent=report_agent,
    )

    crew = Crew(
        agents=[pipeline_agent, report_agent],
        tasks=[t1, t2],
        process=Process.sequential,
        verbose=True,
    )
    return crew.kickoff()