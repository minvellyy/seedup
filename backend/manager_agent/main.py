# manager_agent/main.py
#
# CLI 진입점:
#   python -m manager_agent.main --ticker 005930
#   python -m manager_agent.main --ticker 005930 --as_of 2024-12-31 --lang ko --style friendly
#
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 워크스페이스 루트(07_crewai/)를 sys.path에 추가 — 직접 실행 시에도 import 가능하도록
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# .env 로드 (manager_agent/.env 우선, 없으면 상위 .env)
try:
    from dotenv import load_dotenv
    _env = Path(__file__).parent / ".env"
    load_dotenv(_env if _env.exists() else _ROOT / ".env", override=False)
except ImportError:
    pass  # python-dotenv 없으면 환경변수 직접 설정 필요


def _make_llm():
    """환경변수 MANAGER_LLM_MODEL 기반으로 LLM 객체를 생성합니다.
    기본값: openai/gpt-4o-mini
    """
    model = os.getenv("MANAGER_LLM_MODEL", "openai/gpt-4o-mini")
    try:
        from crewai import LLM
        return LLM(model=model)
    except (ImportError, AttributeError):
        # crewai 버전에 따라 LLM 클래스가 없을 수 있음 → langchain fallback
        from langchain_openai import ChatOpenAI
        # langchain은 'openai/' prefix 없이 모델명만 사용
        lc_model = model.replace("openai/", "")
        return ChatOpenAI(model=lc_model)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manager Agent: 세 분석 모델 통합 투자 리포트 생성"
    )
    parser.add_argument("--ticker", required=True, help="종목코드 (예: 005930)")
    parser.add_argument("--as_of", default=None, help="기준일 YYYY-MM-DD (없으면 최신)")
    parser.add_argument("--lang", default="ko", choices=["ko", "en"], help="리포트 언어")
    parser.add_argument("--style", default="formal", choices=["formal", "friendly"], help="리포트 문체")
    parser.add_argument(
        "--mode",
        default="full",
        choices=["full", "signal", "fin", "summary", "stock_detail"],
        help=(
            "실행 모드: "
            "full=전체분석(종목상세), "
            "signal=방향성만(종목리스트), "
            "fin=재무만(포트폴리오), "
            "summary=재요약, "
            "stock_detail=단일종목상세(투자원칙적합도+기업분석+산업분석)"
        ),
    )
    parser.add_argument(
        "--context",
        default=None,
        dest="context_description",
        help="이 분석이 사용될 화면/목적 설명 (예: '종목 상세 페이지 — 투자 입문자 대상')",
    )
    parser.add_argument(
        "--user-profile",
        default=None,
        dest="user_profile_json",
        help="[stock_detail 모드 전용] UserProfileSummary JSON 문자열. 없으면 샘플 프로파일 사용.",
    )
    parser.add_argument(
        "--stock-item",
        default=None,
        dest="stock_item_json",
        help="[stock_detail 모드 전용] StockItem JSON 문자열 (추천 결과). 없으면 빈 JSON 사용.",
    )
    args = parser.parse_args()

    from manager_agent.crew import run_manager_analysis
    import json

    llm = _make_llm()

    # stock_detail 모드에서 user_profile_json이 없으면 샘플 프로파일 사용
    user_profile_json = args.user_profile_json
    if args.mode == "stock_detail" and not user_profile_json:
        _sample = {
            "risk_tier": "위험중립형",
            "grade": "3등급",
            "horizon_years": 3,
            "goal": "자산증식",
            "deployment": "분산투자",
            "monthly_contribution_krw": 500000,
            "total_assets_krw": 30000000,
            "dividend_pref_1to5": 3,
            "account_type": "일반",
        }
        user_profile_json = json.dumps(_sample, ensure_ascii=False)
        print("[INFO] --user-profile 미지정 → 샘플 프로파일(위험중립형) 사용")

    result = run_manager_analysis(
        llm=llm,
        ticker=args.ticker,
        as_of=args.as_of,
        explain_lang=args.lang,
        explain_style=args.style,
        mode=args.mode,
        context_description=args.context_description,
        user_profile_json=user_profile_json,
        stock_item_json=args.stock_item_json,
    )
    print(result)


if __name__ == "__main__":
    main()
