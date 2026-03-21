# manager_agent/tools/unstructured_tool.py
#
# 비정형 데이터 분석 모델 연동 툴.
# backend/rag_worker 패키지(ESG · 뉴스 · 증권사 리포트 통합 RAG 워커)를 사용한다.
#
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from crewai.tools import tool

# backend/ 를 sys.path 에 추가 → rag_worker, esg_model 등 임포트 가능
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent   # backend/
_WORKSPACE = _BACKEND_DIR.parent                               # workspace root
for _p in (str(_BACKEND_DIR), str(_WORKSPACE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from rag_worker.tools.esg_tool import analyze_esg_direct
from rag_worker.tools.news_tool import search_news_direct
from rag_worker.tools.reports_tool import search_reports_context


def _get_company_name(ticker: str) -> str | None:
    """ticker → 회사명. esg_reports(MySQL) → universe parquet 순으로 조회."""
    t = str(ticker).zfill(6)

    # 1차: MySQL esg_reports
    try:
        import pymysql
        from dotenv import load_dotenv
        load_dotenv()
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "192.168.101.70"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT company_name FROM esg_reports WHERE stock_code=%s LIMIT 1",
                    (t,),
                )
                row = cur.fetchone()
        if row and row.get("company_name"):
            return row["company_name"]
    except Exception:
        pass

    # 2차: instruments 테이블 (전체 상장 종목 포함)
    try:
        import pymysql
        from dotenv import load_dotenv
        load_dotenv()
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "192.168.101.70"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name FROM instruments WHERE stock_code=%s LIMIT 1",
                    (t,),
                )
                row = cur.fetchone()
        if row and row.get("name"):
            return row["name"]
    except Exception:
        pass

    # 3차: universe parquet
    try:
        from config import FIN_MODEL_DIR
        import pandas as pd
        univ_path = FIN_MODEL_DIR / "data" / "processed" / "universe_k200_k150_fixed.parquet"
        if univ_path.exists():
            univ = pd.read_parquet(univ_path)
            univ["ticker"] = univ["ticker"].astype(str).str.zfill(6)
            row_df = univ[univ["ticker"] == t]
            if not row_df.empty:
                return str(row_df.iloc[0]["name"])
    except Exception:
        pass

    return None


@tool("read_unstructured_analysis")
def read_unstructured_analysis(ticker: str) -> str:
    """비정형 데이터 분석 결과를 조회합니다.
    ESG 보고서 리스크·기대요인, 관련 최신 뉴스, 증권사 리포트 인사이트를 통합 반환합니다.
    Args:
        ticker: 종목코드 (예: '005930')
    """
    t = str(ticker).zfill(6)
    output: dict = {"ticker": t, "status": "OK"}

    # 1. ESG 분석
    try:
        esg = analyze_esg_direct(t)
        output["esg"] = esg if esg is not None else {"status": "NO_REPORT"}
    except Exception as exc:
        output["esg"] = {"status": "ERROR", "message": str(exc)}

    # ticker → 회사명 (뉴스·리포트 검색 쿼리에 활용)
    # DB instruments 테이블의 이름을 최우선으로 사용한다.
    # ESG 보고서의 company_name은 모회사·그룹사 이름일 수 있어 뉴스 검색이 엉뚱한 결과를 반환할 수 있음.
    company_name = _get_company_name(t) or (
        output["esg"].get("company_name")
        if isinstance(output.get("esg"), dict)
        else None
    )
    search_query = company_name or t

    # 2. 뉴스 검색 (반드시 회사명 필터 사용 — company_name 없으면 검색 생략)
    if not company_name:
        output["news"] = {"status": "NO_RELEVANT_NEWS",
                          "message": f"{t} 회사명을 확인할 수 없어 뉴스를 조회하지 않습니다. news_summary는 반드시 null로 설정하세요."}
    else:
        try:
            news_results = search_news_direct(search_query, n_results=5, company_name=company_name)
            if news_results:
                output["news"] = [{"doc": r["doc"], "meta": r["meta"]} for r in news_results]
            else:
                output["news"] = {"status": "NO_RELEVANT_NEWS",
                                  "message": f"{company_name} 관련 뉴스가 없습니다. news_summary는 반드시 null로 설정하세요."}
        except Exception as exc:
            output["news"] = {"status": "ERROR", "message": str(exc)}

    # 3. 증권사 리포트 검색 (ticker 필터 + 회사명 쿼리)
    try:
        report_results = search_reports_context(search_query, k=3, ticker=t)
        output["reports"] = [
            {"content": r["content"], "metadata": r["metadata"]}
            for r in report_results
        ]
    except Exception as exc:
        output["reports"] = {"status": "ERROR", "message": str(exc)}

    return json.dumps(output, ensure_ascii=False, indent=2)
