# scripts/run_crewai_structured.py
import argparse
import os
from crewai import LLM
from src.agents.crew_structured import run_structured_crewai

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--as_of", required=True)
    ap.add_argument("--target_year", type=int, default=2024)
    ap.add_argument("--base_year", type=int, default=2023)
    ap.add_argument("--with_market_cap", action="store_true")
    ap.add_argument("--with_price", action="store_true")
    ap.add_argument("--fs_div", default="CONSOL")
    args = ap.parse_args()

    # OpenAI 키/모델은 환경변수로
    llm = LLM(
        model=os.getenv("CREWAI_MODEL", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY", "")
    )

    out = run_structured_crewai(
        llm=llm,
        ticker=args.ticker,
        as_of=args.as_of,
        target_year=args.target_year,
        base_year=args.base_year,
        with_market_cap=args.with_market_cap,
        with_price=args.with_price,
        fs_div=args.fs_div,
    )
    print(out)

if __name__ == "__main__":
    main()