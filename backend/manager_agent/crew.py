# manager_agent/crew.py
#
# 세 가지 분석 모델(정형 재무 / 주가 방향성 / 비정형)의 결과를 종합하는
# CrewAI 매니저 에이전트 크루.
#
# mode별 실행 흐름:
#   full    : 4개 에이전트 전부 (종목 상세 화면용)
#   signal  : 방향성 에이전트만 (종목 리스트/빠른 시그널용)
#   fin     : 재무 에이전트만 (포트폴리오 재무 요약용)
#   summary : 매니저 에이전트만 — 이미 생성된 결과를 JSON으로 받아 요약 (재요약/공유용)
#
from __future__ import annotations

from typing import Any, Literal

from crewai import Agent, Task, Crew, Process

from manager_agent.tools.fin_structured_tool import (
    read_fin_structured_report,
    generate_fin_structured_report,
)
from manager_agent.tools.stock_direction_tool import (
    read_stock_direction_signal,
    get_top_direction_signals,
)
from manager_agent.tools.unstructured_tool import read_unstructured_analysis
from manager_agent.tools.investment_fit_tool import read_investment_fit_data
from manager_agent.tools.news_tool import news_rag_search
from rag_worker.tools.esg_tool import esg_analysis
from rag_worker.tools.reports_tool import reports_rag_search

AnalysisMode = Literal["full", "signal", "fin", "summary", "stock_detail"]


def run_manager_analysis(
    llm: Any,
    ticker: str,
    as_of: str | None = None,
    explain_lang: str = "ko",
    explain_style: str = "formal",
    mode: AnalysisMode = "full",
    summary_input: str | None = None,
    context_description: str | None = None,
    user_profile_json: str | None = None,
    stock_item_json: str | None = None,
) -> str:
    """세 모델의 분석 결과를 종합하여 LLM 기반 투자 리포트를 생성합니다.

    Parameters
    ----------
    llm                 : CrewAI Agent에 전달할 LLM 객체
    ticker              : 종목코드 (예: '005930')
    as_of               : 기준일 YYYY-MM-DD. None이면 최신 데이터를 사용합니다.
    explain_lang        : 'ko' (한국어) | 'en' (English)
    explain_style       : 'formal' (공식) | 'friendly' (친근)
    mode                : 실행 모드
                          'full'    — 4개 에이전트 전부 실행 (종목 상세 화면)
                          'signal'  — 방향성 에이전트만 (종목 리스트, 빠른 시그널)
                          'fin'     — 재무 에이전트만 (포트폴리오 재무 요약)
                          'summary' — 매니저만 실행, summary_input을 받아 재요약
    summary_input       : mode='summary'일 때 요약할 기존 분석 결과 텍스트
    context_description : 이 분석이 사용될 화면/목적 설명.
                          예) '종목 상세 페이지 — 개인 투자자에게 해당 종목의 투자 가치를 설명'
                              '포트폴리오 추천 화면 — 투자 성향 분석 후 종목 적합성 판단'
                              '주간 리포트 — 이번 주 주목할 종목을 뽑아 간략히 소개'
    user_profile_json   : mode='stock_detail'일 때 필요. UserProfileSummary JSON 문자열.
                          FastAPI 레이어에서 api_models.stock_model.get_stock_recommendations() 호출 후 전달.
    stock_item_json     : mode='stock_detail'일 때 선택적. 해당 ticker의 StockItem JSON 문자열.
                          Top5에 없으면 빈 JSON '{}' 또는 None 전달.

    Returns
    -------
    str
        투자 리포트 (JSON 형태 문자열)
    """
    ticker = str(ticker).zfill(6)
    as_of_label = as_of or "최신"
    lang_label = "한국어" if explain_lang == "ko" else "English"
    style_label = "공식적이고 전문적인" if explain_style == "formal" else "친근하고 쉬운"
    context_label = (
        f"\n\n[사용 화면/목적]\n{context_description}"
        if context_description
        else ""
    )

    # ── 에이전트 ───────────────────────────────────────────────────────────────

    fin_analyst = Agent(
        role="정형 재무 데이터 분석가",
        goal=(
            "기업의 DART 재무제표와 시장 데이터를 분석하여 "
            "수익성·성장성·안정성·현금흐름·밸류에이션 관점의 핵심 인사이트를 도출한다."
        ),
        backstory=(
            "CFA 자격증을 보유한 10년 경력의 기업 재무 분석 전문가. "
            "DART 공시 데이터와 시가총액 기반 밸류에이션에 정통하며, "
            "정량 지표를 실용적인 투자 판단으로 전환하는 데 특화되어 있다."
        ),
        tools=[read_fin_structured_report],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=8,
    )

    direction_analyst = Agent(
        role="주가 방향성 예측 분석가",
        goal=(
            "LightGBM 모델의 단기 주가 방향성 예측 결과(p_up, rank, regime)를 해석하여 "
            "종목별 투자 시그널 강도와 시장 맥락을 분석한다."
        ),
        backstory=(
            "퀀트 펀드 출신 5년 경력 퀀트 애널리스트. "
            "머신러닝 모델 출력값을 시장 레짐 맥락에서 해석하고 "
            "단기 방향성 신호를 제공하는 데 전문성을 가지고 있다."
        ),
        tools=[read_stock_direction_signal, get_top_direction_signals],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=8,
    )

    unstructured_analyst = Agent(
        role="비정형 데이터 분석가",
        goal=(
            "뉴스·공시·텍스트 데이터에서 투자 관련 센티멘트와 이슈를 추출하여 "
            "정형·기술적 분석을 보완하는 비정형 신호를 제공한다."
        ),
        backstory=(
            "NLP와 텍스트 마이닝 전문가. 비정형 데이터에서 시장 센티멘트와 "
            "기업별 주요 이벤트를 파악하여 투자 의사결정 보조 정보를 제공한다. "
            "사전 분석 파일이 없으면 뉴스 RAG 검색으로 실시간 시장 맥락을 직접 수집한다."
        ),
        tools=[read_unstructured_analysis, news_rag_search],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=8,
    )

    manager = Agent(
        role="투자 분석 총괄 매니저",
        goal=(
            "세 분석가(정형 재무, 방향성 예측, 비정형)의 결과를 종합하여 "
            "투자 입문자도 이해할 수 있는 종합 투자 리포트를 생성한다."
        ),
        backstory=(
            "글로벌 운용사 출신 30년 경력 포트폴리오 매니저이자 투자 교육 전문가. "
            "전문 용어를 쉬운 말로 풀어 설명하는 데 특화되어 있으며, "
            "복잡한 데이터를 초보 투자자도 바로 행동으로 옮길 수 있는 "
            "명확한 투자 의견으로 전환하는 것을 최우선으로 한다."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )

    # ── 태스크 ─────────────────────────────────────────────────────────────────

    t_fin = Task(
        description=(
            f"종목 {ticker}의 정형 재무 데이터를 분석하라. 기준일: {as_of_label}.\n\n"
            f"[절대 규칙] 분석 대상은 반드시 {ticker}이어야 한다. "
            "조회 결과에 alternatives 필드가 있더라도 그 종목을 현재 분석 대상으로 대체하지 말 것.\n\n"
            "절차:\n"
            "1) read_fin_structured_report 툴로 데이터를 먼저 조회하라.\n"
            "2) NOT_FOUND이면 재무 데이터 없이 '재무 데이터 미확보 종목'으로 표시하고 분석 가능한 항목만 작성하라.\n"
            "3) 조회된 데이터를 기반으로 다음 항목을 각각 분석하라:\n"
            "   - overall_score와 overall_grade\n"
            "   - 수익성: OPM, ROA\n"
            "   - 성장성: 매출 YoY, 영업이익 YoY\n"
            "   - 안정성: 부채비율(debt_equity), 유동비율(current_ratio)\n"
            "   - 현금흐름: CFO margin, FCF margin\n"
            "   - 밸류에이션: PER, PBR\n"
            "4) 핵심 강점 최대 3개, 약점 최대 2개를 도출하라.\n"
            "5) 데이터 품질 이슈(data_quality_note)가 있으면 포함하라."
        ),
        expected_output=(
            "재무 분석 결과 JSON:\n"
            '{\n'
            '  "ticker": str,\n'
            '  "as_of": str,\n'
            '  "overall_score": float,\n'
            '  "overall_grade": str,\n'
            '  "strengths": [str],    // 최대 3개\n'
            '  "weaknesses": [str],   // 최대 2개\n'
            '  "key_metrics": {\n'
            '    "profitability": {"opm": float|null, "roa": float|null},\n'
            '    "growth": {"sales_yoy": float|null, "op_income_yoy": float|null},\n'
            '    "stability": {"debt_equity": float|null, "current_ratio": float|null},\n'
            '    "cashflow": {"cfo_margin": float|null, "fcf_margin": float|null},\n'
            '    "valuation": {"per": float|null, "pbr": float|null}\n'
            '  },\n'
            '  "data_quality_note": str|null\n'
            '}'
        ),
        agent=fin_analyst,
    )

    t_dir = Task(
        description=(
            f"종목 {ticker}의 주가 방향성 예측 결과를 분석하라.\n\n"
            "절차:\n"
            "1) read_stock_direction_signal 툴로 해당 종목의 최신 예측 데이터를 조회하라.\n"
            "2) p_up (상승확률), rank_overall (전체 종목 중 순위), p_market_up, regime을 해석하라.\n"
            "3) 시그널 강도를 다음 기준으로 판단하라:\n"
            "   - p_up >= 0.65  →  강한 매수 시그널\n"
            "   - p_up >= 0.55  →  매수 시그널\n"
            "   - p_up >= 0.45  →  중립\n"
            "   - p_up >= 0.35  →  매도 시그널\n"
            "   - p_up <  0.35  →  강한 매도 시그널\n"
            "4) 시장 레짐이 하락(bearish)인 경우 종목 시그널을 한 단계 보수적으로 하향 조정하라.\n"
            "5) get_top_direction_signals 툴을 사용해 전체 시장에서의 상대적 위치도 파악하라."
        ),
        expected_output=(
            "방향성 예측 결과 JSON:\n"
            '{\n'
            '  "ticker": str,\n'
            '  "date": str,\n'
            '  "p_up": float,\n'
            '  "rank_overall": int,\n'
            '  "total_tickers": int,\n'
            '  "regime": str|null,\n'
            '  "signal_strength": str,  // 강한 매수|매수|중립|매도|강한 매도\n'
            '  "interpretation": str    // 1~2문장 해석\n'
            '}'
        ),
        agent=direction_analyst,
    )

    t_unstr = Task(
        description=(
            f"종목 {ticker}의 비정형(뉴스·공시·텍스트) 데이터를 분석하라.\n\n"
            "절차:\n"
            "1) read_unstructured_analysis 툴로 사전 분석 파일을 조회하라.\n"
            "2) status가 'AVAILABLE'이면 센티멘트 점수와 주요 이슈를 그대로 사용하라.\n"
            "3) status가 'PENDING'이면 news_rag_search 툴로 해당 종목·산업 관련 뉴스를 검색하라.\n"
            "   - 검색 질의 예시: 종목명, 주요 사업 키워드, 관련 산업 테마\n"
            "   - 검색 결과에서 센티멘트, 핵심 리스크, 핵심 기회를 요약하라.\n"
            "   - 이 경우 status는 'NEWS_RAG'로 기록하라.\n"
            "4) 어떤 방법으로 수집했든 최종 결과를 아래 JSON 형식으로 정리하라."
        ),
        expected_output=(
            "비정형 분석 결과 JSON:\n"
            '{\n'
            '  "ticker": str,\n'
            '  "status": "AVAILABLE"|"NEWS_RAG"|"PENDING",\n'
            '  "sentiment_score": float|null,\n'
            '  "key_issues": [str],\n'
            '  "news_themes": [str],\n'
            '  "news_risks": [str],\n'
            '  "news_opportunities": [str],\n'
            '  "last_updated": str|null\n'
            '}'
        ),
        agent=unstructured_analyst,
    )

    t_mgr = Task(
        description=(
            f"종목 {ticker}에 대한 분석 결과를 종합하여 최종 투자 리포트를 작성하라."
            f"{context_label}\n\n"
            f"작성 언어: {lang_label}\n"
            f"작성 톤: {style_label} 문체\n\n"
            "[핵심 원칙] 투자 입문자도 이해할 수 있도록 작성하라.\n"
            "- 전문 용어를 사용할 때는 반드시 괄호 안에 쉬운 설명을 덧붙여라.\n"
            "  예) OPM(영업이익률 — 매출에서 실제 영업으로 벌어들인 이익의 비율),\n"
            "      PER(주가수익비율 — 현재 주가가 이익에 비해 비싼지 싼지를 나타내는 수치),\n"
            "      PBR(주가순자산비율 — 회사 자산 가치 대비 주가 수준),\n"
            "      ROA(총자산이익률 — 보유한 자산으로 얼마나 이익을 냈는지),\n"
            "      유동비율(단기 부채를 갚을 수 있는 여유 자금 수준),\n"
            "      부채비율(자기 자본 대비 빌린 돈의 비율 — 낮을수록 재무적으로 안정적)\n"
            "- 숫자는 그 의미를 함께 설명하라. 예) 'PER 9.97 — 업종 평균보다 낮아 상대적으로 저렴하게 거래되고 있음'\n"
            "- 투자 의견은 구체적인 이유와 함께 '왜 그런지'를 쉽게 풀어 설명하라.\n\n"
            "[비정형 데이터 처리 원칙]\n"
            "- 재무 분석과 방향성 분석이 핵심 분석이며, 이 두 가지만으로도 완전한 투자 의견을 낼 수 있다.\n"
            "- 비정형 데이터(뉴스·공시 분석)가 AVAILABLE이면 '추가 인사이트'로 자연스럽게 포함하라.\n"
            "- 비정형 데이터가 PENDING이면 오류나 경고처럼 표시하지 말고,\n"
            "  '뉴스/공시 텍스트 분석은 추후 제공될 예정입니다' 정도로 한 줄만 가볍게 안내하라.\n"
            "- PENDING 상태가 분석의 완성도를 낮추는 것처럼 느껴지지 않도록 작성하라.\n\n"
            "필수 포함 사항:\n"
            "1) 재무·방향성 신호가 같은 방향인지(컨버전스 — 신호들이 일치함) "
            "반대 방향인지(다이버전스 — 신호들이 엇갈림) 명확히 분석하라.\n"
            "2) 투자 의견(BUY / HOLD / SELL)과 그 핵심 근거를 입문자가 바로 이해할 수 있도록 풀어서 제시하라.\n"
            "3) 주요 리스크를 최대 2가지, 전문 용어 없이 쉬운 말로 설명하라.\n"
            "4) 전체 내용을 2~3문장으로 요약하는 summary를 작성하라. "
            "summary는 투자를 처음 접하는 사람이 읽어도 바로 이해할 수 있어야 한다.\n"
            "5) 비정형 데이터가 AVAILABLE이면 unstructured_insight 필드에 추가 인사이트를 작성하라. "
            "PENDING이면 null로 두되, unstructured_note에 한 줄 안내문만 작성하라."
        ),
        expected_output=(
            "종합 투자 리포트 JSON:\n"
            '{\n'
            '  "ticker": str,\n'
            '  "generated_at": str,                   // ISO datetime\n'
            '  "summary": str,                        // 2~3문장, 입문자 눈높이 전체 요약\n'
            '  "signals": {\n'
            '    "fin_score": float|null,\n'
            '    "fin_grade": str|null,\n'
            '    "direction_signal": str,             // 강한 매수|매수|중립|매도|강한 매도\n'
            '    "direction_p_up": float|null,\n'
            '    "unstructured_sentiment": float|null\n'
            '  },\n'
            '  "signals_plain": {                    // 각 신호를 입문자 언어로 설명\n'
            '    "fin_summary": str,                 // 재무 상태를 2문장으로 쉽게 설명\n'
            '    "direction_summary": str,           // 방향성 신호를 1문장으로 쉽게 설명\n'
            '  },\n'
            '  "convergence_analysis": str,          // 신호 일치/충돌을 쉬운 말로 분석\n'
            '  "recommendation": "BUY"|"HOLD"|"SELL",\n'
            '  "recommendation_reason": str,         // 입문자도 이해할 수 있는 근거 설명\n'
            '  "key_risks": [str],                   // 최대 2개, 전문용어 없이 쉬운 설명\n'
            '  "unstructured_insight": str|null,     // 비정형 AVAILABLE일 때만 추가 인사이트\n'
            '  "unstructured_note": str|null         // 비정형 PENDING일 때 한 줄 안내문\n'
            '}'
        ),
        context=[t_fin, t_dir, t_unstr],
        agent=manager,
    )

    # ── mode별 크루 구성 및 실행 ───────────────────────────────────────────────

    if mode == "signal":
        # 종목 리스트 화면 — 방향성 시그널만 빠르게
        crew = Crew(
            agents=[direction_analyst],
            tasks=[t_dir],
            process=Process.sequential,
            verbose=True,
            max_execution_time=90,
        )
    elif mode == "fin":
        # 포트폴리오 재무 요약 화면 — 재무 분석만
        crew = Crew(
            agents=[fin_analyst],
            tasks=[t_fin],
            process=Process.sequential,
            verbose=True,
            max_execution_time=90,
        )
    elif mode == "summary":
        # 재요약 화면 — 이미 생성된 결과를 매니저가 다시 요약
        if not summary_input:
            raise ValueError("mode='summary'일 때 summary_input이 필요합니다.")
        t_resum = Task(
            description=(
                f"아래 분석 결과를 {lang_label}로, {style_label} 문체로 재요약하라.\n"
                "입문자가 이해할 수 있도록 핵심만 2~3문장으로 정리하고 "
                "투자 의견(BUY/HOLD/SELL)과 주요 리스크 1~2개를 포함하라.\n\n"
                f"[입력 분석 결과]\n{summary_input}"
            ),
            expected_output=(
                '{"ticker": str, "summary": str, "recommendation": str, "key_risks": [str]}'
            ),
            agent=manager,
        )
        crew = Crew(
            agents=[manager],
            tasks=[t_resum],
            process=Process.sequential,
            verbose=True,
            max_execution_time=90,
        )
    elif mode == "stock_detail":
        # 단일 종목 상세 페이지 — 3개 섹션 (투자원칙 적합도 / 기업분석 / 산업분석)
        if not user_profile_json:
            raise ValueError("mode='stock_detail'일 때 user_profile_json이 필요합니다.")
        _stock_item_json = stock_item_json or "{}"

        fit_analyst = Agent(
            role="투자원칙 적합도 분석가",
            goal=(
                "사용자의 투자 성향과 목표를 이 종목의 특성과 비교하여, "
                "이 종목이 사용자의 투자 원칙에 얼마나 잘 맞는지 설명한다."
            ),
            backstory=(
                "개인 투자자 교육 전문가이자 재무설계사. "
                "복잡한 투자 분석을 개인의 상황에 맞게 쉽게 풀어주는 것을 전문으로 하며, "
                "투자 초보자가 '이 종목이 나한테 맞는지'를 직관적으로 이해하도록 돕는다."
            ),
            tools=[read_investment_fit_data, read_fin_structured_report, read_stock_direction_signal, esg_analysis],
            llm=llm,
            verbose=True,
            allow_delegation=False,
            max_iter=8,
        )

        company_analyst = Agent(
            role="기업 심층 분석가",
            goal=(
                "DART 재무제표와 방향성 예측 데이터를 결합하여 "
                "기업의 현재 상태와 미래 전망을 종합적으로 분석한다."
            ),
            backstory=(
                "CFA 자격증 보유 12년 경력 리서치 애널리스트. "
                "재무 데이터와 시장 모멘텀을 통합 분석하여 기업 가치를 평가하며, "
                "입문자도 이해할 수 있는 명확한 언어로 기업 분석 리포트를 작성하는 데 특화."
            ),
            tools=[read_fin_structured_report, generate_fin_structured_report, read_stock_direction_signal, esg_analysis, reports_rag_search],
            llm=llm,
            verbose=True,
            allow_delegation=False,
            max_iter=8,
        )

        industry_analyst = Agent(
            role="산업/섹터 분석가",
            goal=(
                "해당 종목이 속한 산업의 현황, 성장성, 경쟁 구도를 분석하여 "
                "산업 관점에서 이 종목의 위치를 설명한다."
            ),
            backstory=(
                "글로벌 운용사 산업조사팀 출신 15년 경력 섹터 애널리스트. "
                "반도체, 이차전지, 바이오, 금융, 소비재 등 주요 업종 전반에 정통하며, "
                "거시경제 흐름과 업종 사이클을 투자자가 이해하기 쉽게 요약하는 것을 강점으로 한다. "
                "재무 데이터만으로 산업 트렌드가 충분히 파악되지 않을 때는 뉴스 검색을 통해 "
                "최신 산업 동향을 직접 수집하여 분석에 반영한다."
            ),
            tools=[read_fin_structured_report, news_rag_search, esg_analysis, reports_rag_search],
            llm=llm,
            verbose=True,
            allow_delegation=False,
            max_iter=8,
        )

        t_fit = Task(
            description=(
                f"종목 {ticker}에 대해 사용자 투자원칙 적합도 분석을 수행하라.{context_label}\n\n"
                f"[절대 규칙] 분석 대상은 반드시 {ticker}이어야 한다. 다른 종목을 분석 대상으로 대체하지 말 것.\n\n"
                "절차:\n"
                f"1) read_investment_fit_data 툴을 호출하라.\n"
                f"   - user_profile_json: {user_profile_json!r}\n"
                f"   - stock_item_json:   {_stock_item_json!r}\n"
                "   (위 값 그대로 툴에 전달하라. 수정 없이.)\n"
                "2) read_fin_structured_report 또는 read_stock_direction_signal 툴로 "
                "   추가 맥락 데이터를 보완해도 좋다.\n"
                "3) esg_analysis 툴로 ESG 보고서를 조회하라. "
                "   사용자 성향에 ESG·사회적책임 관련 항목이 있다면 적합도 평가에 반영하라. "
                "   NO_REPORT이면 ESG 항목은 생략하라.\n"
                "4) 분석 결과를 based on the data, 다음을 포함하라:\n"
                "   - 사용자 투자 성향(risk_tier)과 이 종목의 위험-수익 특성이 맞는지\n"
                "   - 추천 이유(reasons) 각각이 이 사용자에게 왜 의미 있는지\n"
                "   - 투자 기간·목표와의 적합성\n"
                "   - 주요 주의사항 1가지 (전문용어 없이)\n\n"
                "[작성 원칙] 사용자에게 직접 말하는 톤. '당신의', '고객님의' 대신 '내'로 표현. "
                "모든 문장은 반드시 '~합니다', '~입니다', '~습니다', '~니다' 등 격식체 존댓말로 끝내야 한다. "
                "절대 '~요', '~어', '~야', '~다' 등 반말이나 비격식체로 끝내지 말 것."
            ),
            expected_output=(
                "투자원칙 적합도 분석 JSON:\n"
                '{\n'
                '  "section": "투자원칙 적합도 분석",\n'
                '  "ticker": str,\n'
                '  "fit_score": float,         // 0.0~1.0, 종목이 사용자 성향과 맞는 정도\n'
                '  "fit_grade": str,            // 매우 적합|적합|보통|주의 필요\n'
                '  "fit_summary": str,          // 2~3문장, 입문자 눈높이 적합도 요약. 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "reason_explanations": [str], // 각 추천 이유를 사용자 상황에 맞게 설명 (최대 3개). 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "horizon_fit": str,          // 투자 기간과의 적합성 설명 1문장. 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "caution": str|null          // 주의사항 1가지 (없으면 null). 있다면 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '}'
            ),
            agent=fit_analyst,
        )

        t_company = Task(
            description=(
                f"종목 {ticker}에 대한 기업 심층 분석을 수행하라. 기준일: {as_of_label}.\n\n"
                f"[절대 규칙] 분석 대상은 반드시 {ticker}이어야 한다. "
                "read_fin_structured_report 결과에 alternatives 필드가 있더라도 "
                "그 종목들의 데이터를 현재 분석에 사용하거나 언급하지 말 것. "
                "재무 데이터가 없으면 '재무 데이터 미확보 종목'으로 표기하고 다른 종목을 분석하지 말 것.\n\n"
                "절차:\n"
                "1) read_fin_structured_report 툴로 재무 데이터를 조회하라.\n"
                "2) NOT_FOUND이면 재무 데이터 없이 분석 가능한 항목만 작성하라.\n"
                "3) read_stock_direction_signal 툴로 모멘텀 정보를 보완하라.\n"
                "4) esg_analysis 툴로 ESG 보고서를 조회하라. NO_REPORT이면 ESG 항목은 생략하라.\n"
                "5) reports_rag_search 툴로 해당 종목·기업 관련 증권사 리포트를 검색하라.\n"
                "   - 검색 질의 예시: '[종목명] 기업분석', '[종목명] 목표주가', '[종목명] 실적'\n"
                "   - 결과가 없으면 생략하고 다음 단계로 진행하라.\n"
                "6) 다음 항목을 분석하라:\n"
                "   - 사업 개요: 주력 사업, 위치한 산업/섹터\n"
                "   - 수익성: OPM(영업이익률), ROA(총자산이익률)\n"
                "   - 성장성: 매출·영업이익 YoY 성장\n"
                "   - 재무 건전성: 부채비율, 유동비율\n"
                "   - 현금흐름: CFO margin, FCF margin\n"
                "   - 밸류에이션: PER, PBR (저평가/고평가 여부)\n"
                "   - 주가 모멘텀: p_up 기반 단기 방향성\n"
                "   - ESG: 주요 리스크·기대 요인 (보고서가 있는 경우)\n"
                "   - 증권사 의견: 리포트 기반 목표주가·투자의견 (검색된 경우)\n"
                "7) 핵심 강점 2~3개, 주의 포인트 1~2개를 도출하라.\n\n"
                "[작성 원칙]\n"
                "- 문체: 모든 문장은 반드시 '~합니다', '~입니다', '~있습니다' 등 격식체(합쇼체)로 통일하라. "
                "'~함', '~임', '~됨' 같은 명사형 종결이나 '~이다', '~한다' 같은 평서형은 절대 사용하지 말 것.\n"
                "- 전문용어(예: OPM, PER, CDMO, HBM, FCF 등)는 반드시 괄호 안에 쉬운 한국어 설명을 덧붙여라. "
                "예시: 'OPM(영업이익률, 매출에서 영업이익이 차지하는 비율)', "
                "'CDMO(바이오의약품 위탁 개발·생산 서비스)', "
                "'HBM(고대역폭메모리, AI 연산에 특화된 고성능 반도체 메모리)'\n"
                "- 비전공자 투자 입문자도 이해할 수 있는 수준으로 작성하라."
            ),
            expected_output=(
                "기업분석 JSON:\n"
                '{\n'
                '  "section": "기업분석",\n'
                '  "ticker": str,\n'
                '  "company_name": str,\n'
                '  "sector": str,\n'
                '  "business_overview": str,     // 주력 사업 1~2문장\n'
                '  "financial_health": {\n'
                '    "profitability_summary": str,  // 수익성 2문장\n'
                '    "growth_summary": str,         // 성장성 2문장\n'
                '    "stability_summary": str,      // 재무 안정성 2문장\n'
                '    "cashflow_summary": str,       // 현금흐름 2문장\n'
                '    "valuation_summary": str       // 밸류에이션 2문장 (저평가/고평가 판단 포함)\n'
                '  },\n'
                '  "momentum_summary": str,      // 주가 모멘텀 1문장\n'
                '  "strengths": [str],           // 2~3개. 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "cautions": [str],            // 1~2개. 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "overall_company_view": str   // 기업 전반 평가 2~3문장. 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '}'
            ),
            agent=company_analyst,
        )

        t_industry = Task(
            description=(
                f"종목 {ticker}가 속한 산업/섹터에 대한 분석을 수행하라.\n\n"
                f"[절대 규칙] 분석 대상은 반드시 {ticker}이어야 한다. "
                "read_fin_structured_report 결과에 alternatives 필드가 있더라도 "
                "그 종목들의 정보를 현재 분석에 절대 사용하지 말 것. "
                "재무 데이터가 없으면 sector/industry를 null로 두고 분석을 계속 진행하라.\n\n"
                "절차:\n"
                "1) read_fin_structured_report 툴로 종목의 sector, industry 정보를 확인하라.\n"
                "2) news_rag_search 툴로 해당 산업·섹터 관련 최신 뉴스를 검색하라.\n"
                f"   - 검색 질의 예시: '[산업명] 트렌드', '[산업명] 성장', '{ticker} 경쟁사', '[산업명] 규제'\n"
                "   - 검색 결과의 뉴스가 현재 종목의 산업과 무관하면 사용하지 말 것.\n"
                "   - 뉴스가 없거나 검색 실패 시에도 멈추지 말고 다음 단계로 진행하라.\n"
                "3) reports_rag_search 툴로 해당 산업·섹터 관련 증권사 리포트를 검색하라.\n"
                "   - 검색 질의 예시: '[산업명] 업황', '[산업명] 전망', '[산업명] 성장성'\n"
                "   - 결과가 없으면 생략하고 다음 단계로 진행하라.\n"
                "4) esg_analysis 툴로 ESG 데이터를 조회하라. NO_REPORT이면 생략하라.\n"
                "5) 수집한 데이터를 바탕으로 다음을 분석하라:\n"
                "   - 산업 정의: 이 산업이 어떤 산업인지 쉬운 말로 설명\n"
                "   - 현재 트렌드: 뉴스 및 재무 데이터 기반 현재 주요 동향 2~3개\n"
                "   - 성장 전망: 향후 이 산업의 성장 가능성\n"
                "   - 주요 리스크: 산업 전반에 영향을 줄 수 있는 위험 요인 1~2개\n"
                "   - 경쟁 구도: 주요 경쟁사와 이 종목의 위치\n"
                "   - 규제·정책: 산업에 영향을 주는 주요 규제나 정부 정책\n"
                "6) 산업 관점에서 이 종목의 기회와 위협을 정리하라.\n\n"
                "[작성 원칙]\n"
                "- 문체: 모든 문장은 반드시 '~합니다', '~입니다', '~있습니다' 등 격식체(합쇼체)로 통일하라. "
                "'~함', '~임', '~됨' 같은 명사형 종결이나 '~이다', '~한다' 같은 평서형은 절대 사용하지 말 것.\n"
                "- 전문용어(예: CDMO, HBM, ETF, PER, 섹터, 밸류체인, 사이클 등)는 반드시 괄호 안에 쉬운 한국어 설명을 덧붙여라. "
                "예시: 'CDMO(바이오의약품 위탁 개발·생산 서비스)', "
                "'밸류체인(제품이 만들어지는 전체 공급망)', "
                "'업사이클(산업이 호황 국면에 진입하는 시기)'\n"
                "- 산업에 익숙하지 않은 투자 입문자도 이해할 수 있도록 쉽게 작성하라.\n"
                "- 뉴스 검색 결과가 없더라도 재무 섹터 정보와 일반 지식으로 작성하고, "
                "데이터 부재를 오류처럼 표시하지 말 것."
            ),
            expected_output=(
                "산업분석 JSON:\n"
                '{\n'
                '  "section": "산업분석",\n'
                '  "ticker": str,\n'
                '  "sector": str,\n'
                '  "industry": str,\n'
                '  "industry_overview": str,     // 산업 정의·설명 2~3문장\n'
                '  "current_trends": [str],      // 현재 주요 트렌드 2~3개. 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "growth_outlook": str,        // 성장 전망 2문장. 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "industry_risks": [str],      // 산업 리스크 1~2개. 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "competitive_position": str, // 이 종목의 경쟁 위치 1~2문장. 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "policy_regulatory": str|null, // 관련 규제·정책 (없으면 null). 있다면 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  "opportunity_threat_summary": str // 기회·위협 종합 2문장. 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '}'
            ),
            agent=industry_analyst,
        )

        t_detail_mgr = Task(
            description=(
                f"종목 {ticker}의 단일 종목 상세 페이지 최종 리포트를 작성하라."
                f"{context_label}\n\n"
                f"작성 언어: {lang_label}\n"
                f"작성 톤: {style_label} 문체\n\n"
                "앞서 네 분석가(투자원칙 적합도 / 기업분석 / 산업분석 / 비정형 데이터)의 결과를 종합하여 "
                "단일 종목 상세 페이지에 바로 사용할 수 있는 통합 리포트를 생성하라.\n\n"
                "[핵심 원칙]\n"
                "- 문체: 모든 문장은 반드시 '~합니다', '~입니다', '~있습니다' 등 격식체(합쇼체)로 통일하라. "
                "'~함', '~임', '~됨' 같은 명사형 종결이나 '~이다', '~한다' 같은 평서형은 절대 사용하지 말 것.\n"
                "- 전문용어(예: OPM, PER, CDMO, HBM, FCF, ETF, 밸류체인 등)는 반드시 괄호 안에 쉬운 한국어 설명을 덧붙여라.\n"
                "- 네 섹션의 내용이 서로 연결되도록 통합적 관점으로 서술하라.\n"
                "- 전체 요약 summary는 사용자가 이 종목을 '내가 살 종목인지'를 "
                "  직관적으로 판단할 수 있도록 핵심만 담아라.\n"
                "- 비정형 분석가의 결과(뉴스·센티멘트)와 기업분석가가 수집한 ESG·증권사 리포트 데이터를 "
                "  unstructured_analysis 필드에 반드시 포함하라. 데이터가 없으면 null로 두어라."
            ),
            expected_output=(
                "단일 종목 상세 페이지 통합 리포트 JSON:\n"
                '{\n'
                '  "ticker": str,\n'
                '  "generated_at": str,\n'
                '  "page_summary": str,           // 이 페이지 전체 핵심 요약 2~3문장\n'
                '  "investment_fit": {            // 투자원칙 적합도 섹션\n'
                '    "fit_score": float,\n'
                '    "fit_grade": str,\n'
                '    "fit_summary": str,\n'
                '    "reason_explanations": [str],\n'
                '    "horizon_fit": str,\n'
                '    "caution": str|null\n'
                '  },\n'
                '  "company_analysis": {          // 기업분석 섹션\n'
                '    "company_name": str,\n'
                '    "sector": str,\n'
                '    "business_overview": str,\n'
                '    "financial_health": {\n'
                '      "profitability_summary": str,\n'
                '      "growth_summary": str,\n'
                '      "stability_summary": str,\n'
                '      "cashflow_summary": str,\n'
                '      "valuation_summary": str\n'
                '    },\n'
                '    "momentum_summary": str,\n'
                '    "strengths": [str],           // 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "cautions": [str],            // 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "overall_company_view": str   // 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  },\n'
                '  "industry_analysis": {         // 산업분석 섹션\n'
                '    "sector": str,\n'
                '    "industry": str,\n'
                '    "industry_overview": str,     // 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "current_trends": [str],      // 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "growth_outlook": str,        // 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "industry_risks": [str],      // 각 항목 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "competitive_position": str,  // 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "policy_regulatory": str|null, // 있다면 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "opportunity_threat_summary": str // 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  },\n'
                '  "unstructured_analysis": {     // ESG·뉴스·증권사 리포트 인사이트\n'
                '    "esg_risks": str|null,        // ESG 주요 리스크 (없으면 null). 있다면 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "esg_opportunities": str|null, // ESG 기대 요인 (없으면 null). 있다면 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "news_summary": str|null,     // 최신 뉴스 요약 1~2문장 (없으면 null). 있다면 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '    "reports_insight": str|null   // 증권사 리포트 핵심 인사이트 (없으면 null). 있다면 반드시 ~합니다/~입니다/~습니다로 끝낼 것\n'
                '  }\n'
                '}'
            ),
            context=[t_fit, t_company, t_industry, t_unstr],
            agent=manager,
        )

        crew = Crew(
            agents=[fit_analyst, company_analyst, industry_analyst, unstructured_analyst, manager],
            tasks=[t_fit, t_company, t_industry, t_unstr, t_detail_mgr],
            process=Process.sequential,
            verbose=True,
            max_execution_time=360,
        )

    else:
        # full — 4개 에이전트 전부 (기본, 종목 상세 화면)
        crew = Crew(
            agents=[fin_analyst, direction_analyst, unstructured_analyst, manager],
            tasks=[t_fin, t_dir, t_unstr, t_mgr],
            process=Process.sequential,
            verbose=True,
            max_execution_time=300,
        )

    result = crew.kickoff()
    return str(result)


def run_portfolio_recommendation(
    llm: Any,
    user_risk_tier: str = "위험중립형",
    user_profile_json: str | None = None,
) -> str:
    """
    방향성 신호(signal_pack) + 재무 데이터(structured_report)를 사용하여
    3가지 스타일의 포트폴리오 추천 결과를 단일 CrewAI 실행으로 생성합니다.

    portfolio_model.py의 가격·DB 기반 스코어링을 대체합니다.

    Returns
    -------
    str
        JSON 배열 문자열 (3개 포트폴리오)
    """
    portfolio_strategist = Agent(
        role="AI 포트폴리오 전략가",
        goal=(
            f"{user_risk_tier} 투자자를 위해 방향성 신호와 재무 데이터를 결합하여 "
            "3가지 스타일의 최적 포트폴리오를 구성한다."
        ),
        backstory=(
            "퀀트 분석과 재무 분석을 겸비한 포트폴리오 매니저. "
            "LightGBM 방향성 모델과 DART 재무 데이터를 활용하여 "
            "투자자 성향에 맞는 맞춤 포트폴리오를 구성하는 데 전문성을 가진다."
        ),
        tools=[
            get_top_direction_signals,
            read_stock_direction_signal,
            read_fin_structured_report,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    # 유저 프로필 컨텍스트 구성
    _profile_context = ""
    if user_profile_json:
        try:
            import json as _json
            _p = _json.loads(user_profile_json)
            _survey = _p.get("survey", {})
            _lines = []
            _label_map = {
                "INVEST_GOAL": "투자 목적",
                "TARGET_HORIZON": "목표 시점",
                "TARGET_AMOUNT": "목표 금액",
                "CONTRIBUTION_TYPE": "투자 방식",
                "LUMP_SUM_AMOUNT": "일시금 금액",
                "MONTHLY_AMOUNT": "월 투자 금액",
                "MAX_HOLDINGS": "최대 보유 종목 수",
                "DIVIDEND_PREF": "배당 선호도",
                "ACCOUNT_TYPE": "계좌 유형",
            }
            for code, label in _label_map.items():
                val = _survey.get(code)
                if val is not None:
                    _lines.append(f"  - {label}: {val}")
            if _lines:
                _profile_context = "\n사용자 상세 정보:\n" + "\n".join(_lines) + "\n"
        except Exception:
            pass

    task = Task(
        description=(
            f"사용자 투자성향: {user_risk_tier}\n"
            f"{_profile_context}\n"
            "다음 절차로 3가지 스타일의 포트폴리오를 구성하라:\n\n"
            "1. get_top_direction_signals 툴로 stock 유형 상위 20개 종목을 조회하라.\n"
            "   (asset_type='stock', top_n=20)\n"
            "2. 상위 10개 종목 각각에 대해 read_fin_structured_report 툴로 재무 데이터를 조회하라.\n"
            "   (각 종목코드로 개별 호출)\n"
            "   ⚠️ 중요: read_fin_structured_report가 error=NOT_FOUND를 반환해도 절대 멈추지 말라.\n"
            "   재무 데이터가 없는 종목은 ai_fin_grade='정보없음'으로 처리하고 방향성 신호(p_adj, rank_overall)만으로 평가를 계속하라.\n"
            "   재무 데이터 부재는 종목 탈락 이유가 아니다. 모든 20개 종목 중 방향성 신호가 강한 종목을 우선 선정하라.\n"
            "3. 조회한 방향성 신호(p_adj, rank_overall)와 재무 데이터(있는 경우 overall_grade)를\n"
            "   종합하여 아래 3가지 스타일로 포트폴리오를 각각 구성하라:\n\n"
            "   [균형 추천형 - balanced]\n"
            "   - 재무 데이터 있으면 건전성 우선, 없으면 rank_overall 기준 상위 + p_adj 높음 균형\n"
            "   - 종목 수: 5~7개, 비중 합계: 100%\n\n"
            "   [모멘텀 집중형 - momentum]\n"
            "   - p_adj 기준 상위 종목 집중, 재무 데이터 있으면 참고하되 없어도 가능\n"
            "   - 종목 수: 5~7개, 비중 합계: 100%\n\n"
            "   [안정 우선형 - lowvol]\n"
            "   - 재무 데이터 있는 종목 중 안정성 우수 우선, 없으면 rank_overall 하위권(안정) 종목 선택\n"
            "   - 종목 수: 5~7개, 비중 합계: 100%\n\n"
            "4. 각 포트폴리오 종목에 weight_pct(합계 100%)를 배분하라.\n"
            "5. 각 종목별 선정 이유(1~2문장), 재무 등급(없으면 '정보없음'), 강점(최대 2개), 약점(최대 1개)을 작성하라.\n"
            "6. 세 포트폴리오에 다른 종목 구성을 사용해도 좋다. 스타일에 맞게 선별하라.\n"
        ),
        expected_output=(
            "반드시 아래 JSON 배열 형식으로만 출력하라. 마크다운 코드블록 없이 JSON만.\n\n"
            "[\n"
            "  {\n"
            '    "portfolio_label": "균형 추천형",\n'
            '    "portfolio_style": "balanced",\n'
            '    "portfolio_summary": "포트폴리오 특징 1~2문장",\n'
            '    "portfolio_items": [\n'
            "      {\n"
            '        "ticker": "005930",\n'
            '        "name": "삼성전자",\n'
            '        "weight_pct": 20.0,\n'
            '        "weight": 0.20,\n'
            '        "asset_type": "STOCK",\n'
            '        "selection_reason": "선정 이유 1~2문장",\n'
            '        "ai_fin_grade": "양호",\n'
            '        "ai_strengths": ["강점 1문장"],\n'
            '        "ai_weaknesses": ["약점 1문장"]\n'
            "      }\n"
            "    ]\n"
            "  },\n"
            "  { 모멘텀 집중형 동일 형식 },\n"
            "  { 안정 우선형 동일 형식 }\n"
            "]\n"
        ),
        agent=portfolio_strategist,
    )

    crew = Crew(
        agents=[portfolio_strategist],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        max_execution_time=300,
    )

    result = crew.kickoff()
    return str(result)


# ─────────────────────────────────────────────────────────────────────────────
# 투자성향 맞춤 종목 Top5 추천 (CrewAI 기반)
# ─────────────────────────────────────────────────────────────────────────────

def run_stock_recommendation(
    llm: Any,
    user_risk_tier: str = "위험중립형",
    user_profile_json: str | None = None,
) -> str:
    """
    방향성 신호(signal_pack) + 재무 데이터(structured_report)를 사용하여
    투자성향에 맞는 개별 종목 Top5를 추천합니다.

    Returns
    -------
    str
        JSON 객체 문자열 {"items": [...]}
    """
    stock_analyst = Agent(
        role="AI 종목 발굴 애널리스트",
        goal=(
            f"{user_risk_tier} 투자자를 위해 방향성 신호와 재무 데이터를 분석하여 "
            "최적 종목 Top5를 제시한다."
        ),
        backstory=(
            "LightGBM 기반 주가 방향성 모델과 DART 재무 데이터를 결합해 "
            "투자자 성향에 맞는 개별 종목을 발굴하는 퀀트 애널리스트. "
            "모멘텀, 재무 건전성, 리스크를 투자성향에 따라 가중하여 최적 종목을 선정한다."
        ),
        tools=[
            get_top_direction_signals,
            read_stock_direction_signal,
            read_fin_structured_report,
        ],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    # 유저 프로필 컨텍스트 구성
    _profile_context = ""
    if user_profile_json:
        try:
            import json as _json
            _p = _json.loads(user_profile_json)
            _survey = _p.get("survey", {})
            _label_map = {
                "INVEST_GOAL": "투자 목적",
                "TARGET_HORIZON": "목표 시점",
                "TARGET_AMOUNT": "목표 금액",
                "CONTRIBUTION_TYPE": "투자 방식",
                "MAX_HOLDINGS": "최대 보유 종목 수",
                "DIVIDEND_PREF": "배당 선호도",
            }
            _lines = [
                f"  - {lbl}: {_survey[code]}"
                for code, lbl in _label_map.items()
                if _survey.get(code)
            ]
            if _lines:
                _profile_context = "\n사용자 상세 정보:\n" + "\n".join(_lines) + "\n"
        except Exception:
            pass

    # 투자성향별 선정 기준
    _tier_guidance = {
        "공격투자형":  "p_adj가 가장 높은(상승 확률 최상위) 종목 5개를 우선 선정하라. 재무 리스크는 감수 가능하다.",
        "적극투자형":  "p_adj 상위 종목 중 재무 데이터가 있으면 overall_grade '양호' 이상 종목을 우선하라.",
        "위험중립형":  "p_adj와 재무 건전성(overall_grade)을 균형 있게 반영하여 5개를 선정하라.",
        "안전추구형":  "재무 데이터가 있는 종목 중 overall_grade '우수' 또는 '양호' 종목을 우선하고, p_adj는 참고만 하라.",
        "안정형":      "재무 '우수' 등급 이상을 최우선. p_adj보다 안정성(낮은 rank_overall 변동)을 중시하라.",
    }
    guidance = _tier_guidance.get(user_risk_tier, _tier_guidance["위험중립형"])

    task = Task(
        description=(
            f"사용자 투자성향: {user_risk_tier}\n"
            f"{_profile_context}\n"
            f"[선정 기준] {guidance}\n\n"
            "다음 절차로 종목 Top5를 선정하라:\n\n"
            "1. get_top_direction_signals 툴로 stock 유형 상위 30개 종목을 조회하라.\n"
            "   (asset_type='stock', top_n=30)\n"
            "2. 상위 종목들에 대해 read_fin_structured_report 툴로 재무 데이터를 조회하라.\n"
            "   ⚠️ NOT_FOUND 오류가 나도 멈추지 말고, 해당 종목은 ai_fin_grade='정보없음'으로 처리하라.\n\n"
            "[잡주 필터링 원칙 — 반드시 적용]\n"
            "아래 조건 중 1개라도 해당하면 해당 종목은 최종 추천에서 제외하라:\n"
            "  - 재무 데이터가 '정보없음'이면서 rank_overall이 500위권 밖인 종목 (신호도 약하고 재무도 없음)\n"
            "  - ai_fin_grade가 '주의' 등급인 종목 (재무 위험)\n"
            "  - 스팩(SPAC), 관리종목, 상장폐지 위험 종목으로 의심되는 이름(예: '제X호스팩', '홀딩스' 단독) → 제외\n"
            "  - 상장 후 6개월 미만으로 보이는 종목 (가격 데이터가 극히 짧음) → 제외\n\n"
            "[다양성 원칙]\n"
            "  - 동일 섹터(바이오/의약품, 반도체, 금융 등)에서 최대 2종목만 허용하라.\n"
            "  - p_adj 순위가 높더라도 이미 같은 섹터 2종목이 선정됐으면 다음 섹터 종목을 선택하라.\n\n"
            f"3. 위 기준을 모두 적용한 뒤, 투자성향 '{user_risk_tier}'에 최적인 우량 종목 5개를 선정하라.\n"
            "4. 각 종목의 선정 이유(reasons 리스트, 2~3개)와 종합 설명(explanation)을 한국어로 작성하라.\n"
            "   [설명 작성 지침]\n"
            "   - 단순 수익률 숫자만 강조하지 말 것\n"
            "   - '왜 이 종목이 이 투자성향의 투자자에게 적합한 구조를 가졌는지'를 반드시 포함할 것\n"
            "   - 초보 투자자도 이해할 수 있도록 전문 용어에는 괄호 설명을 붙일 것\n"
        ),
        expected_output=(
            "반드시 아래 JSON 객체 형식으로만 출력하라. 마크다운 코드블록 없이 JSON만.\n\n"
            "{\n"
            '  "items": [\n'
            '    {\n'
            '      "rank": 1,\n'
            '      "ticker": "005930",\n'
            '      "name": "삼성전자",\n'
            '      "market": "KOSPI",\n'
            '      "p_adj": 0.82,\n'
            '      "rank_overall": 2,\n'
            '      "ai_fin_grade": "양호",\n'
            '      "reasons": ["최근 상승 신호 강함", "재무 건전성 우수"],\n'
            '      "explanation": "종합 설명 1~2문장"\n'
            '    }\n'
            '  ]\n'
            "}\n"
        ),
        agent=stock_analyst,
    )

    crew = Crew(
        agents=[stock_analyst],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        max_execution_time=240,
    )

    result = crew.kickoff()
    return str(result)


# ─────────────────────────────────────────────────────────────────────────────
# MC 모델 선정 결과 설명 전용 에이전트 (선정은 하지 않고 설명만 작성)
# ─────────────────────────────────────────────────────────────────────────────

def run_mc_explanation_agent(
    llm: Any,
    mc_items_json: str,
    user_risk_tier: str = "위험중립형",
    mode: str = "stock",  # "stock" | "portfolio"
) -> str:
    """
    몬테카를로 모델이 이미 선정한 종목/포트폴리오에 대해
    방향성 신호 + 재무 데이터를 조회하여 자연어 설명을 추가합니다.

    ⚠️ 이 에이전트는 선정 결과를 변경하지 않습니다. 설명 텍스트만 반환합니다.

    Returns
    -------
    str
        JSON 배열 문자열 [{"ticker": "005930", "explanation": "..."}, ...]
    """
    explainer = Agent(
        role="AI 퀀트 리포터",
        goal=(
            "몬테카를로 모델이 이미 선정한 종목에 대해 LightGBM 방향성 신호와 재무 데이터를 확인하여 "
            "투자 초보자가 불안해하지 않고 이해할 수 있는 한국어 설명을 작성한다."
        ),
        backstory=(
            "퀀트 모델의 수치 결과를 투자자 친화적인 언어로 해석하는 전문 애널리스트. "
            "MC 모델이 선정한 종목은 그대로 유지하되, 비현실적으로 높은 수익률(예: 수천, 수만 퍼센트)은 "
            "수학적 모델의 '극심한 변동성 경고'로 해석하여 숫자 대신 정성적인 언어로 순화하여 설명한다."
        ),
        tools=[read_stock_direction_signal, read_fin_structured_report],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    task = Task(
        description=(
            f"사용자 투자성향: {user_risk_tier}\n\n"
            f"몬테카를로 모델 선정 결과 (변경 불가):\n{mc_items_json}\n\n"
            "위 각 종목에 대해 순서대로 수행하라:\n"
            "1. read_stock_direction_signal 툴로 방향성 신호(p_adj, rank_overall)를 조회하라.\n"
            "2. read_fin_structured_report 툴로 재무 데이터(overall_grade, 수익성, 안정성)를 조회하라.\n"
            "   NOT_FOUND여도 멈추지 말고 다음 종목으로 진행하라.\n"
            "3. MC 결과(p10/p50/p90)와 방향성 신호, 재무 데이터를 종합하여\n"
            f"   {user_risk_tier} 투자자에게 이 종목이 왜 적합한지 2~3문장으로 설명하라.\n\n"
            "⚠️ [수치 순화 원칙 — 반드시 준수] ⚠️\n"
            "   - MC 결과에 p50 기준 수익률이 1,000% 이상(예: 5,000%, 80,000%)인 종목이 있다면,\n"
            "     절대 그 숫자를 설명 문장에 직접 쓰지 마라.\n"
            "   - 대신 '가격 변동성이 매우 큰 고위험 모멘텀 종목', '단기 급등락 가능성이 있는 종목',\n"
            "     '공격적 성향에 맞는 높은 변동성 종목' 같은 정성적 표현으로 대체하라.\n"
            "   - p10/p50/p90 수치 자체를 설명에 인용할 때는 현실적인 범위(예: ±30~200%)만 사용하고,\n"
            "     비현실적 수치는 인용하지 마라.\n\n"
            "⚠️ 종목 목록, 순위, ticker는 절대 변경하지 마라. 설명 텍스트만 작성하라.\n"
        ),
        expected_output=(
            "반드시 아래 JSON 배열 형식으로만 출력하라. 마크다운 코드블록 없이 JSON만.\n\n"
            '[{"ticker": "005930", "explanation": "설명 2~3문장"}, ...]\n'
        ),
        agent=explainer,
    )

    crew = Crew(
        agents=[explainer],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        max_execution_time=180,
    )

    result = crew.kickoff()
    return str(result)


# ─────────────────────────────────────────────────────────────────────────────
# MC 후보 → CrewAI 최종 확정 에이전트
#
# 흐름: LightGBM+MC 1차 후보(15개) → CrewAI 재무검증+잡주필터 → 최종 5개 확정
# ─────────────────────────────────────────────────────────────────────────────

def run_mc_final_selection_agent(
    llm: Any,
    candidates_json: str,
    user_risk_tier: str = "위험중립형",
    user_profile_json: str | None = None,
) -> str:
    """
    몬테카를로 모델이 1차 선정한 후보 종목들을 입력받아
    재무 검증 + 잡주 필터 + 투자성향 적합성을 종합하여 최종 5개를 확정합니다.

    Parameters
    ----------
    candidates_json : str
        MC 1차 후보 JSON 배열.
        각 항목 필드: rank, ticker, name, market, p_adj, rank_overall,
                     ai_fin_grade, mc_p10_pct, mc_p50_pct, mc_p90_pct, vol_ann_pct

    Returns
    -------
    str
        JSON 객체 문자열 {"items": [...]} — 최종 확정 5개 종목
    """
    # 투자성향별 최종 선정 기준
    _tier_guidance = {
        "공격투자형":  "mc_p90_pct(낙관 시나리오)와 p_adj(상승 확률)가 최상위인 종목을 우선하라. 단, 잡주·신규상장 제외.",
        "적극투자형":  "mc_p50_pct(중간 시나리오)와 p_adj를 균형 있게 보고, 재무등급 '양호' 이상 종목을 우선하라.",
        "위험중립형":  "mc_p50_pct와 재무건전성(overall_grade)을 균등 반영하라. vol이 지나치게 높은 종목은 제외.",
        "안전추구형":  "재무 '우수'/'양호' 종목을 최우선. mc_p10_pct(비관 시나리오)가 -30% 이하인 종목은 제외.",
        "안정형":      "재무 '우수' 이상만 허용. vol_ann_pct 30% 이하 저변동성 종목 중심으로 선정하라.",
    }
    guidance = _tier_guidance.get(user_risk_tier, _tier_guidance["위험중립형"])

    # 유저 프로필 컨텍스트 구성
    _profile_context = ""
    if user_profile_json:
        try:
            import json as _json
            _p = _json.loads(user_profile_json)
            _survey = _p.get("survey", {})
            _label_map = {
                "INVEST_GOAL": "투자 목적",
                "TARGET_HORIZON": "목표 시점",
                "DIVIDEND_PREF": "배당 선호도",
            }
            _lines = [
                f"  - {lbl}: {_survey[code]}"
                for code, lbl in _label_map.items()
                if _survey.get(code)
            ]
            if _lines:
                _profile_context = "\n사용자 상세 정보:\n" + "\n".join(_lines) + "\n"
        except Exception:
            pass

    selector = Agent(
        role="AI 종목 심사위원",
        goal=(
            f"퀀트 모델이 제시한 후보 종목 중에서 {user_risk_tier} 투자자에게 진정으로 "
            "적합한 우량 종목 5개를 최종 확정한다. 잡주·부실주를 반드시 걸러내고 "
            "다양한 섹터에서 안정적인 포트폴리오를 구성한다."
        ),
        backstory=(
            "LightGBM+몬테카를로 퀀트 모델이 1차적으로 걸러낸 후보를 받아 "
            "DART 재무 데이터로 2차 검증하는 심사 애널리스트. "
            "퀀트 점수가 높아도 재무가 부실하거나 잡주 성격이면 과감히 탈락시키며, "
            "초보 투자자가 안심할 수 있는 구조의 종목을 최종 선발한다."
        ),
        tools=[read_fin_structured_report, read_stock_direction_signal],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    task = Task(
        description=(
            f"사용자 투자성향: {user_risk_tier}\n"
            f"{_profile_context}\n"
            f"[최종 선정 기준] {guidance}\n\n"
            "퀀트 모델(LightGBM + 몬테카를로) 1차 후보:\n"
            f"{candidates_json}\n\n"
            "다음 절차로 최종 5종목을 확정하라:\n\n"
            "1. 후보 전체에 대해 read_fin_structured_report 툴로 재무 데이터를 조회하라.\n"
            "   ⚠️ NOT_FOUND여도 멈추지 말고 '정보없음'으로 처리 후 계속하라.\n"
            "2. 조회한 재무 데이터를 바탕으로 아래 [잡주 필터]를 적용하라:\n"
            "   · 재무 데이터 '정보없음' + rank_overall 200위권 밖 → 제외\n"
            "   · ai_fin_grade '주의' 등급 → 제외\n"
            "   · 종목명에 '스팩', '제X호' 패턴 → 제외\n"
            "   · vol_ann_pct가 150% 초과하는 극단적 고변동성 종목 → 제외\n"
            "3. 남은 후보에서 투자성향 기준 + 섹터 다양성(동일 섹터 최대 2종목)을 적용하여\n"
            "   최종 5종목을 확정하라.\n"
            "4. 확정된 각 종목에 대해 한국어 설명(explanation)을 2~3문장으로 작성하라:\n"
            "   · 퀀트 점수만 나열하지 말고, '왜 이 투자성향에 적합한 구조인지' 포함\n"
            "   · 전문 용어에는 괄호 설명 추가\n"
            "   · mc_p50_pct가 500% 초과하는 종목은 수치를 직접 언급하지 말고\n"
            "     '고변동성 모멘텀 종목' 같은 정성적 표현으로 대체\n"
        ),
        expected_output=(
            "반드시 아래 JSON 객체 형식으로만 출력하라. 마크다운 코드블록 없이 JSON만.\n\n"
            "{\n"
            '  "items": [\n'
            '    {\n'
            '      "rank": 1,\n'
            '      "ticker": "005930",\n'
            '      "name": "삼성전자",\n'
            '      "reasons": ["선정 근거 1", "선정 근거 2"],\n'
            '      "explanation": "이 종목은 ... 투자성향에 적합합니다."\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
            "⚠️ items 배열은 정확히 5개. ticker와 name은 후보 목록에 있던 것만 사용.\n"
        ),
        agent=selector,
    )

    crew = Crew(
        agents=[selector],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        max_execution_time=300,
    )

    result = crew.kickoff()
    return str(result)


# ─────────────────────────────────────────────────────────────────────────────
# 비동기 래퍼 / DB 기반 진입점
# ─────────────────────────────────────────────────────────────────────────────

import asyncio as _asyncio
import functools as _functools
import os as _os


def _get_user_risk_tier(user_id: int) -> str:
    """DB에서 user_id의 investment_type을 조회해 risk_tier 문자열을 반환합니다."""
    import pymysql
    _RISK_MAP = {
        "공격투자형": "공격투자형",
        "적극투자형": "적극투자형",
        "위험중립형": "위험중립형",
        "안전추구형": "안전추구형",
        "안정추구형": "안전추구형",
        "안정형":     "안정형",
    }
    conn = pymysql.connect(
        host=_os.getenv("DB_HOST", "localhost"),
        port=int(_os.getenv("DB_PORT", 3306)),
        user=_os.getenv("DB_USER"),
        password=_os.getenv("DB_PASSWORD"),
        db=_os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT investment_type FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        if not row:
            return "위험중립형"
        return _RISK_MAP.get(row["investment_type"], "위험중립형")
    finally:
        conn.close()


async def run_manager_analysis_async(
    llm: Any,
    ticker: str,
    as_of: str | None = None,
    explain_lang: str = "ko",
    explain_style: str = "formal",
    mode: AnalysisMode = "full",
    summary_input: str | None = None,
    context_description: str | None = None,
    user_profile_json: str | None = None,
    stock_item_json: str | None = None,
) -> str:
    """run_manager_analysis의 비동기 래퍼 (ThreadPoolExecutor 실행)."""
    loop = _asyncio.get_event_loop()
    fn = _functools.partial(
        run_manager_analysis,
        llm=llm,
        ticker=ticker,
        as_of=as_of,
        explain_lang=explain_lang,
        explain_style=explain_style,
        mode=mode,
        summary_input=summary_input,
        context_description=context_description,
        user_profile_json=user_profile_json,
        stock_item_json=stock_item_json,
    )
    return await loop.run_in_executor(None, fn)


def run_db_stock_recommendation(llm: Any, user_id: int) -> str:
    """DB에서 user_id의 투자성향을 조회한 뒤 run_stock_recommendation을 호출합니다."""
    risk_tier = _get_user_risk_tier(user_id)
    return run_stock_recommendation(llm=llm, user_risk_tier=risk_tier)


async def run_db_stock_recommendation_async(llm: Any, user_id: int) -> str:
    """run_db_stock_recommendation의 비동기 래퍼."""
    loop = _asyncio.get_event_loop()
    fn = _functools.partial(run_db_stock_recommendation, llm=llm, user_id=user_id)
    return await loop.run_in_executor(None, fn)


def run_db_portfolio_recommendation(llm: Any, user_id: int, mode: str = "multi") -> str:
    """DB에서 user_id의 투자성향을 조회한 뒤 run_portfolio_recommendation을 호출합니다."""
    risk_tier = _get_user_risk_tier(user_id)
    return run_portfolio_recommendation(llm=llm, user_risk_tier=risk_tier)


async def run_db_portfolio_recommendation_async(llm: Any, user_id: int, mode: str = "multi") -> str:
    """run_db_portfolio_recommendation의 비동기 래퍼."""
    loop = _asyncio.get_event_loop()
    fn = _functools.partial(run_db_portfolio_recommendation, llm=llm, user_id=user_id, mode=mode)
    return await loop.run_in_executor(None, fn)
