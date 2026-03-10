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
        tools=[read_fin_structured_report, generate_fin_structured_report],
        llm=llm,
        verbose=True,
        allow_delegation=False,
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
            "현재 개발 중인 모듈을 담당하며, 데이터 미비 시 PENDING 상태를 명확히 보고한다."
        ),
        tools=[read_unstructured_analysis],
        llm=llm,
        verbose=True,
        allow_delegation=False,
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
    )

    # ── 태스크 ─────────────────────────────────────────────────────────────────

    t_fin = Task(
        description=(
            f"종목 {ticker}의 정형 재무 데이터를 분석하라. 기준일: {as_of_label}.\n\n"
            "절차:\n"
            "1) read_fin_structured_report 툴로 데이터를 먼저 조회하라.\n"
            "2) NOT_FOUND 오류가 반환되면 generate_fin_structured_report 툴을 사용해 생성하라.\n"
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
            f"종목 {ticker}의 비정형(뉴스·공시·텍스트) 데이터 분석 결과를 조회하라.\n\n"
            "절차:\n"
            "1) read_unstructured_analysis 툴로 데이터를 조회하라.\n"
            "2) status가 'AVAILABLE'이면 센티멘트 점수와 주요 이슈를 요약하라.\n"
            "3) status가 'PENDING'이면 아직 준비 중인 데이터임을 기록하라.\n"
            "   → 이것은 오류가 아니라 추후 보완될 추가 분석 영역이다.\n"
            "   → 재무·방향성 분석이 핵심이며, 비정형은 보너스 정보임을 인지하라."
        ),
        expected_output=(
            "비정형 분석 결과 JSON:\n"
            '{\n'
            '  "ticker": str,\n'
            '  "status": "AVAILABLE"|"PENDING",\n'
            '  "sentiment_score": float|null,\n'
            '  "key_issues": [str],\n'
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
            tools=[read_investment_fit_data, read_fin_structured_report, read_stock_direction_signal],
            llm=llm,
            verbose=True,
            allow_delegation=False,
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
            tools=[read_fin_structured_report, generate_fin_structured_report, read_stock_direction_signal],
            llm=llm,
            verbose=True,
            allow_delegation=False,
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
                "거시경제 흐름과 업종 사이클을 투자자가 이해하기 쉽게 요약하는 것을 강점으로 한다."
            ),
            tools=[read_fin_structured_report],
            llm=llm,
            verbose=True,
            allow_delegation=False,
        )

        t_fit = Task(
            description=(
                f"종목 {ticker}에 대해 사용자 투자원칙 적합도 분석을 수행하라.{context_label}\n\n"
                "절차:\n"
                f"1) read_investment_fit_data 툴을 호출하라.\n"
                f"   - user_profile_json: {user_profile_json!r}\n"
                f"   - stock_item_json:   {_stock_item_json!r}\n"
                "   (위 값 그대로 툴에 전달하라. 수정 없이.)\n"
                "2) read_fin_structured_report 또는 read_stock_direction_signal 툴로 "
                "   추가 맥락 데이터를 보완해도 좋다.\n"
                "3) 분석 결과를 based on the data, 다음을 포함하라:\n"
                "   - 사용자 투자 성향(risk_tier)과 이 종목의 위험-수익 특성이 맞는지\n"
                "   - 추천 이유(reasons) 각각이 이 사용자에게 왜 의미 있는지\n"
                "   - 투자 기간·목표와의 적합성\n"
                "   - 주요 주의사항 1가지 (전문용어 없이)\n\n"
                "[작성 원칙] 사용자에게 직접 말하는 톤. '당신의', '고객님의' 대신 '내'로 표현."
            ),
            expected_output=(
                "투자원칙 적합도 분석 JSON:\n"
                '{\n'
                '  "section": "투자원칙 적합도 분석",\n'
                '  "ticker": str,\n'
                '  "fit_score": float,         // 0.0~1.0, 종목이 사용자 성향과 맞는 정도\n'
                '  "fit_grade": str,            // 매우 적합|적합|보통|주의 필요\n'
                '  "fit_summary": str,          // 2~3문장, 입문자 눈높이 적합도 요약\n'
                '  "reason_explanations": [str], // 각 추천 이유를 사용자 상황에 맞게 설명 (최대 3개)\n'
                '  "horizon_fit": str,          // 투자 기간과의 적합성 설명 1문장\n'
                '  "caution": str|null          // 주의사항 1가지 (없으면 null)\n'
                '}'
            ),
            agent=fit_analyst,
        )

        t_company = Task(
            description=(
                f"종목 {ticker}에 대한 기업 심층 분석을 수행하라. 기준일: {as_of_label}.\n\n"
                "절차:\n"
                "1) read_fin_structured_report 툴로 재무 데이터를 조회하라.\n"
                "2) NOT_FOUND이면 generate_fin_structured_report를 사용하라.\n"
                "3) read_stock_direction_signal 툴로 모멘텀 정보를 보완하라.\n"
                "4) 다음 항목을 분석하라:\n"
                "   - 사업 개요: 주력 사업, 위치한 산업/섹터\n"
                "   - 수익성: OPM(영업이익률), ROA(총자산이익률)\n"
                "   - 성장성: 매출·영업이익 YoY 성장\n"
                "   - 재무 건전성: 부채비율, 유동비율\n"
                "   - 현금흐름: CFO margin, FCF margin\n"
                "   - 밸류에이션: PER, PBR (저평가/고평가 여부)\n"
                "   - 주가 모멘텀: p_up 기반 단기 방향성\n"
                "5) 핵심 강점 2~3개, 주의 포인트 1~2개를 도출하라.\n\n"
                "[작성 원칙] 전문용어 사용 시 반드시 괄호 안에 쉬운 설명을 덧붙여라."
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
                '  "strengths": [str],           // 2~3개\n'
                '  "cautions": [str],            // 1~2개\n'
                '  "overall_company_view": str   // 기업 전반 평가 2~3문장\n'
                '}'
            ),
            agent=company_analyst,
        )

        t_industry = Task(
            description=(
                f"종목 {ticker}가 속한 산업/섹터에 대한 분석을 수행하라.\n\n"
                "절차:\n"
                "1) read_fin_structured_report 툴로 종목의 sector, industry 정보를 확인하라.\n"
                "2) 해당 산업에 대해 다음을 분석하라:\n"
                "   - 산업 정의: 이 산업이 어떤 산업인지 쉬운 말로 설명\n"
                "   - 현재 트렌드: 현재 이 산업의 주요 동향과 이슈\n"
                "   - 성장 전망: 향후 이 산업의 성장 가능성\n"
                "   - 주요 리스크: 산업 전반에 영향을 줄 수 있는 위험 요인 1~2개\n"
                "   - 경쟁 구도: 주요 경쟁사와 이 종목의 위치\n"
                "   - 규제·정책: 산업에 영향을 주는 주요 규제나 정부 정책\n"
                "3) 산업 관점에서 이 종목의 기회와 위협을 정리하라.\n\n"
                "[작성 원칙] 산업에 익숙하지 않은 투자 입문자도 이해할 수 있도록 쉽게 작성하라."
            ),
            expected_output=(
                "산업분석 JSON:\n"
                '{\n'
                '  "section": "산업분석",\n'
                '  "ticker": str,\n'
                '  "sector": str,\n'
                '  "industry": str,\n'
                '  "industry_overview": str,     // 산업 정의·설명 2~3문장\n'
                '  "current_trends": [str],      // 현재 주요 트렌드 2~3개\n'
                '  "growth_outlook": str,        // 성장 전망 2문장\n'
                '  "industry_risks": [str],      // 산업 리스크 1~2개\n'
                '  "competitive_position": str, // 이 종목의 경쟁 위치 1~2문장\n'
                '  "policy_regulatory": str|null, // 관련 규제·정책 (없으면 null)\n'
                '  "opportunity_threat_summary": str // 기회·위협 종합 2문장\n'
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
                "앞서 세 분석가(투자원칙 적합도 / 기업분석 / 산업분석)의 결과를 종합하여 "
                "단일 종목 상세 페이지에 바로 사용할 수 있는 통합 리포트를 생성하라.\n\n"
                "[핵심 원칙]\n"
                "- 투자 입문자도 이해할 수 있도록 전문 용어에 괄호 설명을 붙여라.\n"
                "- 세 섹션의 내용이 서로 연결되도록 통합적 관점으로 서술하라.\n"
                "- 전체 요약 summary는 사용자가 이 종목을 '내가 살 종목인지'를 "
                "  직관적으로 판단할 수 있도록 핵심만 담아라."
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
                '    "strengths": [str],\n'
                '    "cautions": [str],\n'
                '    "overall_company_view": str\n'
                '  },\n'
                '  "industry_analysis": {         // 산업분석 섹션\n'
                '    "sector": str,\n'
                '    "industry": str,\n'
                '    "industry_overview": str,\n'
                '    "current_trends": [str],\n'
                '    "growth_outlook": str,\n'
                '    "industry_risks": [str],\n'
                '    "competitive_position": str,\n'
                '    "policy_regulatory": str|null,\n'
                '    "opportunity_threat_summary": str\n'
                '  }\n'
                '}'
            ),
            context=[t_fit, t_company, t_industry],
            agent=manager,
        )

        crew = Crew(
            agents=[fit_analyst, company_analyst, industry_analyst, manager],
            tasks=[t_fit, t_company, t_industry, t_detail_mgr],
            process=Process.sequential,
            verbose=True,
            max_execution_time=180,
        )

    else:
        # full — 4개 에이전트 전부 (기본, 종목 상세 화면)
        crew = Crew(
            agents=[fin_analyst, direction_analyst, unstructured_analyst, manager],
            tasks=[t_fin, t_dir, t_unstr, t_mgr],
            process=Process.sequential,
            verbose=True,
            max_execution_time=180,
        )

    result = crew.kickoff()
    return str(result)


def run_portfolio_recommendation(
    llm: Any,
    user_risk_tier: str = "위험중립형",
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

    task = Task(
        description=(
            f"사용자 투자성향: {user_risk_tier}\n\n"
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
