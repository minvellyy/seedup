"""
투자 전문 챗봇 서비스
- OpenAI API와 개인화 데이터를 통합
- 사용자별 포트폴리오, 투자성향 반영
- 실시간 주식 데이터 연동
"""
from __future__ import annotations

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator
from sqlalchemy.orm import Session
from sqlalchemy import desc

import openai
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from pydantic import BaseModel

from models import User, ChatSession, ChatMessage, SurveyAnswer
from database import SessionLocal

# 실시간 데이터 조회를 위한 모듈 Import
try:
    from kis_client import get_current_price, get_daily_prices_1y
    _KIS_API_AVAILABLE = True
    print("[CHATBOT] KIS API 모듈 로드 성공")
except ImportError as e:
    _KIS_API_AVAILABLE = False
    print(f"[CHATBOT WARNING] KIS API 모듈 로드 실패: {e}")

# 웹 검색을 위한 모듈
import requests
import re

# ═══ RAG 비정형 데이터 모듈 Import ══════════════════════════════════════════════
_RAG_AVAILABLE = False
try:
    import sys
    from pathlib import Path
    _BACKEND_DIR = Path(__file__).resolve().parent
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))

    from rag_worker.tools.news_tool import search_news_direct
    from rag_worker.tools.reports_tool import search_reports_context
    from rag_worker.tools.esg_tool import analyze_esg_direct
    _RAG_AVAILABLE = True
    print("[CHATBOT] RAG 비정형 데이터 모듈 로드 성공 (뉴스 · 리포트 · ESG)")
except Exception as _rag_err:
    print(f"[CHATBOT WARNING] RAG 모듈 로드 실패 (챗봇은 정상 동작): {_rag_err}")

# ═══ 환경변수 & 설정 ═══════════════════════════════════════════════════════════

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[CHATBOT] .env 파일 로드 완료")
except ImportError:
    print("[CHATBOT WARNING] python-dotenv가 설치되지 않음")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
print(f"[CHATBOT] OpenAI API 키 확인: {'설정됨' if OPENAI_API_KEY else '없음'}")

if not OPENAI_API_KEY or OPENAI_API_KEY == "pp_env":
    print("[CHATBOT ERROR] OpenAI API 키가 올바르게 설정되지 않았습니다.")
    print("backend/.env 파일에 OPENAI_API_KEY=your_actual_api_key 를 설정해주세요.")
    raise ValueError("OpenAI API 키가 설정되지 않았습니다.")

try:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    print("[CHATBOT] OpenAI 클라이언트 초기화 완료")
except Exception as e:
    print(f"[CHATBOT ERROR] OpenAI 클라이언트 초기화 실패: {e}")
    raise

# ═══ Pydantic 모델 ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    user_id: int
    message: str
    session_id: Optional[str] = None
    
class ChatResponse(BaseModel):
    session_id: str
    message: str
    is_streaming: bool = False

class ChatSessionInfo(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime

# ═══ 실시간 데이터 조회 함수 ═══════════════════════════════════════════════════════

# 주요 종목 코드 매핑 (확장됨)
STOCK_CODE_MAP = {
    "삼성전자": "005930",
    "SK하이닉스": "000660", 
    "현대차": "005380",
    "삼성전자우": "005935",
    "LG에너지솔루션": "373220",
    "SK스퀘어": "402340",
    "삼성바이오로직스": "207940",
    "기아": "000270",
    "POSCO홀딩스": "005490",
    "네이버": "035420",
    "카카오": "035720",
    "셀트리온": "068270",
    "하이브": "352820",
    "LG화학": "051910",
    "삼성SDI": "006400",
    # 추가 주요 종목
    "현대모비스": "012330",
    "엘지디스플레이": "034220",
    "LG전자": "066570",
    "하이닉스": "000660",  # 동일 종목 다른 표기
    "삼성물산": "028260",
    "대한항공": "003490",
    "SK텔레콤": "017670",
    "네이버파이낸셜": "035420",  # 네이버 다른 표기
    "놀고테크": "078070",
    "전기전자": "004800",
    "키움증권": "039490",
    # 은행 및 금융
    "삼성전자환산": "005935",
    "삼성생목": "032830",
    "디비히어로": "123700",
    # 바이오/제약
    "예스코": "114190",
    "올리브영": "950170",
    "종근당": "185750"
}

def get_major_stocks_realtime_data() -> str:
    """주요 종목들의 실시간 데이터 조회 (투자 추천용) - SK하이닉스 포함"""
    major_stocks = ["삼성전자", "SK하이닉스", "LG화학", "카카오", "네이버", "셀트리온", "기아", "POSCO홀딩스"]
    
    realtime_data = "\n\n## 📈 주요 종목 실시간 데이터 (참고용)\n"
    realtime_data += "**⚠️ 아래 데이터는 실시간 정보입니다. 답변 시 반드시 이 데이터를 우선 사용해주세요.**\n\n"
    
    for company_name in major_stocks:
        stock_data = get_real_time_stock_data(company_name)
        if stock_data:
            current_price = stock_data.get("current_price")
            change_rate = stock_data.get("change_rate") 
            change_amount = stock_data.get("change_amount")
            
            # 가격 포맷팅
            try:
                price_formatted = f"{float(current_price):,.0f}원" if current_price != "N/A" else "N/A"
            except:
                price_formatted = f"{current_price}원" if current_price != "N/A" else "N/A"
            
            realtime_data += f"- **{company_name}** ({stock_data.get('code')}): {price_formatted}"
            
            if change_rate != "N/A":
                realtime_data += f" ({change_rate:+.2f}%)"
            realtime_data += "\n"
    
    realtime_data += "\n**🔴 중요: 위 실시간 가격 정보를 사용하여 정확한 분석과 추천을 제공해주세요.**\n"
    print(f"[CHATBOT] 주요 종목 실시간 데이터 구성 완료: {len(major_stocks)}개 종목")
    return realtime_data

def _lookup_stock_code_from_db(company_name: str) -> Optional[str]:
    """instruments 테이블에서 회사명으로 종목코드 조회 (STOCK_CODE_MAP 에 없을 때 fallback)"""
    try:
        import pymysql
        from dotenv import load_dotenv
        load_dotenv()
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            charset="utf8mb4",
            connect_timeout=3,
        )
        with conn:
            with conn.cursor() as cur:
                # 정확한 이름 우선, 없으면 부분 일치
                cur.execute(
                    "SELECT stock_code FROM instruments WHERE name = %s LIMIT 1",
                    (company_name,)
                )
                row = cur.fetchone()
                if row:
                    return str(row[0]).zfill(6)
                cur.execute(
                    "SELECT stock_code FROM instruments WHERE name LIKE %s LIMIT 1",
                    (f"%{company_name}%",)
                )
                row = cur.fetchone()
                if row:
                    return str(row[0]).zfill(6)
    except Exception as e:
        print(f"[CHATBOT] DB 종목코드 조회 실패: {e}")
    return None


def get_real_time_stock_data(company_name: str) -> Optional[Dict[str, Any]]:
    """실시간 주식 데이터 조회"""
    if not _KIS_API_AVAILABLE:
        return None

    # 1차: 하드코딩 맵, 2차: DB 조회
    stock_code = STOCK_CODE_MAP.get(company_name) or _lookup_stock_code_from_db(company_name)
    if not stock_code:
        return None
    # DB에서 찾은 경우 맵에 캐시 (같은 세션 중 재조회 방지)
    if company_name not in STOCK_CODE_MAP:
        STOCK_CODE_MAP[company_name] = stock_code
        print(f"[CHATBOT] DB에서 종목코드 발견: {company_name} → {stock_code}")
    
    try:
        print(f"[CHATBOT] 실시간 데이터 조회: {company_name} ({stock_code})")
        price_info = get_current_price(stock_code)
        return {
            "company": company_name,
            "code": stock_code,
            "current_price": price_info.get("current_price", "N/A"),
            "change_rate": price_info.get("change_rate", "N/A"),
            "change_amount": price_info.get("change", "N/A"),
            "volume": price_info.get("volume", "N/A"),
            "prev_close": price_info.get("prev_close", "N/A"),
            "price_date": price_info.get("price_date", "N/A"),
            "market_cap": price_info.get("market_cap"),
            "per": price_info.get("per"),
            "pbr": price_info.get("pbr"),
            "eps": price_info.get("eps"),
            "week52_high": price_info.get("week52_high"),
            "week52_low": price_info.get("week52_low"),
        }
    except Exception as e:
        print(f"[CHATBOT ERROR] 실시간 데이터 조회 실패: {e}")
        return None

def search_stock_info_in_message(message: str) -> List[Dict[str, Any]]:
    """메시지에서 종목명을 찾아 실시간 데이터 조회 (개선됨)"""
    found_stocks = []
    print(f"[CHATBOT DEBUG] 메시지에서 종목 검색: '{message}'")
    
    # 대소문자 상관없이 검색
    message_lower = message.lower()
    
    for company_name, stock_code in STOCK_CODE_MAP.items():
        company_lower = company_name.lower()
        
        # 정확한 매칭 우선
        if company_name in message:
            print(f"[CHATBOT DEBUG] 정확한 매칭 발견: {company_name}")
            stock_data = get_real_time_stock_data(company_name)
            if stock_data:
                found_stocks.append(stock_data)
                print(f"[CHATBOT DEBUG] 실시간 데이터 추가: {company_name}")
            continue
            
        # 부분 매칭 (예: "하이닉스" -> "SK하이닉스")
        if len(company_name) > 2:
            # 회사명에서 SK, LG 등 접두사 제외한 부분 추출
            base_name = company_name
            if company_name.startswith("SK"):
                base_name = company_name[2:]
            elif company_name.startswith("LG"):
                base_name = company_name[2:]
                
            # 기본 이름으로 검색
            if base_name in message and len(base_name) >= 2:
                print(f"[CHATBOT DEBUG] 부분 매칭 발견: {base_name} -> {company_name}")
                stock_data = get_real_time_stock_data(company_name)
                if stock_data:
                    found_stocks.append(stock_data)
                    print(f"[CHATBOT DEBUG] 실시간 데이터 추가: {company_name}")
                continue
    
    # 중복 제거
    seen_codes = set()
    unique_stocks = []
    for stock in found_stocks:
        if stock['code'] not in seen_codes:
            unique_stocks.append(stock)
            seen_codes.add(stock['code'])

    # STOCK_CODE_MAP에서 못 찾은 경우 DB에서 메시지 안의 회사명 검색
    if not unique_stocks and _KIS_API_AVAILABLE:
        try:
            import pymysql
            from dotenv import load_dotenv
            load_dotenv()
            conn = pymysql.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 3306)),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME"),
                charset="utf8mb4",
                connect_timeout=3,
            )
            with conn:
                with conn.cursor() as cur:
                    # 메시지 안에 포함된 회사명 검색 (길이 3자 이상만)
                    cur.execute(
                        "SELECT name, stock_code FROM instruments "
                        "WHERE INSTR(%s, name) > 0 AND LENGTH(name) >= 3 "
                        "ORDER BY LENGTH(name) DESC LIMIT 3",
                        (message,)
                    )
                    rows = cur.fetchall()
            for name, code in rows:
                stock_code = str(code).zfill(6)
                if stock_code not in seen_codes:
                    STOCK_CODE_MAP[name] = stock_code  # 캐시
                    stock_data = get_real_time_stock_data(name)
                    if stock_data:
                        unique_stocks.append(stock_data)
                        seen_codes.add(stock_code)
                        print(f"[CHATBOT] DB fallback 종목 발견: {name} → {stock_code}")
        except Exception as e:
            print(f"[CHATBOT] DB 종목 fallback 실패: {e}")

    print(f"[CHATBOT DEBUG] 최종 발견된 종목: {len(unique_stocks)}개")
    for stock in unique_stocks:
        print(f"[CHATBOT DEBUG] - {stock['company']} ({stock['code']})")

    return unique_stocks

def format_real_time_data(stocks_data: List[Dict[str, Any]]) -> str:
    """실시간 데이터를 챗봇 응답용 텍스트로 포맷팅"""
    if not stocks_data:
        print("[CHATBOT DEBUG] format_real_time_data: 데이터가 비어있음")
        return ""
    
    print(f"[CHATBOT DEBUG] format_real_time_data: {len(stocks_data)}개 종목 포맷팅 시작")
    formatted = "\n\n## 📈 실시간 주가 정보\n"
    
    for stock in stocks_data:
        print(f"[CHATBOT DEBUG] 포맷팅 중: {stock}")
        price = stock.get("current_price", "N/A")
        change_rate = stock.get("change_rate", "N/A") 
        change_amount = stock.get("change_amount", "N/A")
        
        # 변화율에 따른 이모지 추가
        if change_rate != "N/A":
            try:
                rate_float = float(change_rate)
                if rate_float > 0:
                    trend_emoji = "🔴"  # 상승
                elif rate_float < 0:
                    trend_emoji = "🔵"  # 하락
                else:
                    trend_emoji = "⚪"  # 보합
            except:
                trend_emoji = "⚪"
        else:
            trend_emoji = "⚪"
        
        # 숫자 포맷팅 안전하게 처리
        try:
            price_formatted = f"{float(price):,.0f}원" if price != "N/A" else "N/A"
        except:
            price_formatted = f"{price}원" if price != "N/A" else "N/A"
            
        try:
            change_amount_formatted = f"{float(change_amount):,.0f}원" if change_amount != "N/A" else "N/A"
        except:
            change_amount_formatted = f"{change_amount}원" if change_amount != "N/A" else "N/A"
        
        market_cap = stock.get("market_cap")
        per = stock.get("per")
        pbr = stock.get("pbr")
        week52_high = stock.get("week52_high")
        week52_low  = stock.get("week52_low")

        formatted += f"### {trend_emoji} **{stock['company']}** ({stock['code']})\n"
        formatted += f"- **현재가**: {price_formatted}\n"
        formatted += f"- **등락률**: {change_rate}%\n" if change_rate != "N/A" else "- **등락률**: N/A\n"
        formatted += f"- **등락액**: {change_amount_formatted}\n"
        if market_cap:
            formatted += f"- **시가총액**: {market_cap:,.0f}억원\n"
        if per:
            formatted += f"- **PER**: {per:.2f}배\n"
        if pbr:
            formatted += f"- **PBR**: {pbr:.2f}배\n"
        if week52_high and week52_low:
            formatted += f"- **52주 최고/최저**: {week52_high:,.0f}원 / {week52_low:,.0f}원\n"
        formatted += "\n"
    
    formatted += "*📅 실시간 데이터 (한국투자증권 API)*\n"
    print(f"[CHATBOT DEBUG] 포맷팅 완료: {len(formatted)}자")
    return formatted

# ═══ RAG 비정형 데이터 컨텍스트 생성 ══════════════════════════════════════════

import html as _html


def build_web_search_context(message: str):
    """네이버 뉴스 검색으로 실시간 웹 정보를 가져와 컨텍스트를 생성한다.

    Returns:
        (context_str, citations) — citations: [{"text": str, "url": str|None}, ...]
    """
    parts: List[str] = []
    citations: List[Dict[str, Any]] = []

    def _clean(s: str) -> str:
        return _html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

    # ── 1. 네이버 뉴스 검색 ───────────────────────────────────────────────────
    naver_id     = os.getenv("NAVER_CLIENT_ID")
    naver_secret = os.getenv("NAVER_CLIENT_SECRET")
    if naver_id and naver_secret:
        try:
            resp = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers={
                    "X-Naver-Client-Id": naver_id,
                    "X-Naver-Client-Secret": naver_secret,
                },
                params={"query": message, "display": 3, "sort": "date"},
                timeout=5,
            )
            if resp.ok:
                items = resp.json().get("items", [])

                # 허용 도메인 → 언론사명 (허용리스트 방식: 여기 없으면 제외)
                _ALLOWED_SOURCES = {
                    # 경제지
                    "hankyung.com":      "한국경제",
                    "mk.co.kr":          "매일경제",
                    "sedaily.com":       "서울경제",
                    "edaily.co.kr":      "이데일리",
                    "mt.co.kr":          "머니투데이",
                    "heraldcorp.com":    "헤럴드경제",
                    "fn.co.kr":          "파이낸셜뉴스",
                    "fnnews.com":        "파이낸셜뉴스",
                    "thebell.co.kr":     "더벨",
                    "bizwatch.co.kr":    "비즈워치",
                    "fetimes.co.kr":     "파이낸셜투데이",
                    "infostock.co.kr":   "인포스탁",
                    # 종합일간지
                    "chosun.com":        "조선일보",
                    "donga.com":         "동아일보",
                    "joongang.co.kr":    "중앙일보",
                    "hani.co.kr":        "한겨레",
                    "khan.co.kr":        "경향신문",
                    "kmib.co.kr":        "국민일보",
                    "munhwa.com":        "문화일보",
                    "segye.com":         "세계일보",
                    # 통신사
                    "yna.co.kr":         "연합뉴스",
                    "yonhapnewstv.co.kr":"연합뉴스TV",
                    "newsis.com":        "뉴시스",
                    "news1.kr":          "뉴스1",
                    # IT·산업
                    "etnews.com":        "전자신문",
                    "inews24.com":       "아이뉴스24",
                    "zdnet.co.kr":       "ZDNet Korea",
                    # 해외
                    "reuters.com":       "로이터",
                    "bloomberg.com":     "블룸버그",
                    "investing.com":     "인베스팅닷컴",
                }

                def _get_source(url: str):
                    """URL이 허용 도메인이면 (언론사명, True), 아니면 (None, False)"""
                    try:
                        domain = url.split("//")[-1].split("/")[0].lower()
                        domain = domain.replace("www.", "").replace("m.", "")
                        for key, name in _ALLOWED_SOURCES.items():
                            if key in domain:
                                return name, True
                    except Exception:
                        pass
                    return None, False

                # 허용 도메인 소속 기사만 통과
                filtered = []
                for item in items:
                    orig_url = item.get("originallink", item.get("link", ""))
                    name, ok = _get_source(orig_url)
                    if ok:
                        item["_source_name"] = name
                        filtered.append(item)

                if filtered:
                    lines = ["\n\n## 🔍 네이버 뉴스 검색 결과 (실시간)\n"]
                    for i, item in enumerate(filtered, 1):
                        title    = _clean(item.get("title", ""))
                        desc     = _clean(item.get("description", ""))
                        pub_date = item.get("pubDate", "")[:16] if item.get("pubDate") else ""
                        orig_url = item.get("originallink", item.get("link", ""))
                        source   = item["_source_name"]
                        lines.append(f"{i}. **{title}**\n   {desc}")
                        citations.append({"text": f"{source} ({pub_date})", "url": orig_url})
                    parts.append("\n".join(lines))
                    print(f"[CHATBOT WEB] 네이버 뉴스 {len(filtered)}건 로드 (허용도메인 / 전체 {len(items)}건)")
            else:
                print(f"[CHATBOT WEB] 네이버 응답 오류: {resp.status_code}")
        except Exception as e:
            print(f"[CHATBOT WEB] 네이버 검색 실패: {e}")

    if not parts:
        return "", []

    header = "\n\n---\n**🌐 실시간 웹 검색 결과 — 아래 최신 정보를 참고해 답변하세요.**"
    footer = "\n---"
    return header + "".join(parts) + footer, citations


def build_rag_context(message: str, found_stocks: List[Dict[str, Any]]):
    """뉴스 · 증권사 리포트 · ESG RAG DB를 검색해 챗봇 컨텍스트를 생성한다.

    Returns:
        (context_str, citations) — citations: [{"text": str, "url": str|None}, ...]
    """
    if not _RAG_AVAILABLE:
        return "", []

    # 첫 번째 종목 코드 · 회사명 추출
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    if found_stocks:
        ticker = found_stocks[0].get("code")
        company_name = found_stocks[0].get("company")

    context_parts: List[str] = []
    citations: List[Dict[str, Any]] = []

    # ── 1. 뉴스 검색 ──────────────────────────────────────────────────────────
    try:
        news_results = search_news_direct(message, n_results=3, company_name=company_name)
        if news_results:
            lines = ["\n\n## 📰 관련 최신 뉴스 (내부 DB)\n"]
            for i, r in enumerate(news_results, 1):
                doc = r.get("doc", "")[:300].strip()
                meta = r.get("meta", {})
                title = meta.get("title", "")
                source_url = meta.get("source_url", "") or None
                date_str = meta.get("date", meta.get("published_at", ""))
                date_label = f" ({date_str[:10]})" if date_str else ""
                display_title = title or meta.get("query_topic", "")
                lines.append(f"{i}. {doc}{date_label}")
                citation_text = f"{display_title}{date_label}" if display_title else f"뉴스{date_label}"
                citations.append({"text": citation_text, "url": source_url})
            context_parts.append("\n".join(lines))
            print(f"[CHATBOT RAG] 뉴스 {len(news_results)}건 로드")
    except Exception as e:
        print(f"[CHATBOT RAG] 뉴스 검색 실패: {e}")

    # ── 2. 증권사 리포트 검색 ─────────────────────────────────────────────────
    try:
        import urllib.parse as _urlparse
        report_results_raw = search_reports_context(message, k=4, ticker=ticker)
        # 리포트 제목 기준 중복 제거 후 최대 2건
        seen_titles: set = set()
        report_results = []
        for r in report_results_raw:
            t = r.get("metadata", {}).get("report_title", "")
            if t not in seen_titles:
                seen_titles.add(t)
                report_results.append(r)
            if len(report_results) >= 2:
                break
        if report_results:
            lines = ["\n\n## 📋 관련 증권사 리포트 (내부 DB)\n"]
            for i, r in enumerate(report_results, 1):
                meta = r.get("metadata", {})
                brokerage = meta.get("brokerage", "")
                title = meta.get("report_title", "")
                date_str = meta.get("report_date", "")
                header = " · ".join(filter(None, [brokerage, title, date_str]))
                content = r.get("content", "")[:400].strip()

                # PDF URL 생성 (source, report_type 메타데이터 활용)
                source = meta.get("source", "")
                report_type = meta.get("report_type", "")
                pdf_url: Optional[str] = None
                if source and report_type:
                    pdf_filename = source.replace(".json", ".pdf")
                    pdf_path = os.path.join(
                        os.path.dirname(__file__), "reports", report_type, pdf_filename
                    )
                    if os.path.exists(pdf_path):
                        pdf_url = (
                            f"/api/v1/reports/pdf/"
                            f"{_urlparse.quote(report_type, safe='')}/"
                            f"{_urlparse.quote(pdf_filename, safe='')}"
                        )

                label = " · ".join(filter(None, [brokerage, title, date_str])) or "리포트"
                citations.append({"text": label, "url": pdf_url})
                lines.append(f"{i}. [{header}]\n{content}")
            context_parts.append("\n".join(lines))
            print(f"[CHATBOT RAG] 증권사 리포트 {len(report_results)}건 로드")
    except Exception as e:
        print(f"[CHATBOT RAG] 리포트 검색 실패: {e}")

    # ── 3. ESG 분석 (종목이 특정된 경우만) ────────────────────────────────────
    if ticker:
        try:
            esg_result = analyze_esg_direct(ticker)
            if esg_result and isinstance(esg_result, dict):
                lines = [f"\n\n## 🌱 ESG 분석 ({company_name or ticker})\n"]
                risks = (
                    esg_result.get("risks")
                    or esg_result.get("risk_factors")
                    or esg_result.get("negative_factors")
                    or []
                )
                opps = (
                    esg_result.get("opportunities")
                    or esg_result.get("positive_factors")
                    or esg_result.get("expected_factors")
                    or []
                )
                if risks:
                    risk_text = (
                        "、".join(risks[:3]) if isinstance(risks, list)
                        else str(risks)[:200]
                    )
                    lines.append(f"- 리스크: {risk_text}")
                if opps:
                    opp_text = (
                        "、".join(opps[:3]) if isinstance(opps, list)
                        else str(opps)[:200]
                    )
                    lines.append(f"- 기대요인: {opp_text}")
                if len(lines) > 1:
                    context_parts.append("\n".join(lines))
                    print(f"[CHATBOT RAG] ESG 데이터 로드: {ticker}")
        except Exception as e:
            print(f"[CHATBOT RAG] ESG 분석 실패: {e}")

    if not context_parts:
        return "", []

    header = "\n\n---\n**📚 내부 비정형 데이터 (뉴스 · 리포트 · ESG) — 아래 내용을 참고해 답변하세요.**"
    footer = "\n---"
    return header + "".join(context_parts) + footer, citations


def build_citations_section(citations: List[Dict[str, Any]]) -> str:
    """출처 리스트를 마크다운 출처 섹션 문자열로 변환한다."""
    if not citations:
        return ""
    lines = ["\n\n---\n📰 **참고 출처**"]
    for c in citations:
        text = c.get("text", "")
        url  = c.get("url")
        if url:
            lines.append(f"- [{text}]({url})")
        else:
            lines.append(f"- {text}")
    lines.append("---")
    return "\n".join(lines)


# ═══ 투자 전문 프롬프트 ═══════════════════════════════════════════════════════

INVESTMENT_SYSTEM_PROMPT = """당신은 한국의 투자 전문가 AI 어시스턴트 'SEED UP'입니다.

## 역할과 전문성
- 한국 주식시장(코스피, 코스닥) 전문가
- 포트폴리오 관리 및 리스크 관리 어드바이저
- 투자 교육 및 용어 설명 전문가
- 매수/매도/보유 판단 조언 제공

## 🔴 실시간 데이터 사용 원칙 (중요!)
- **반드시 제공된 실시간 주가 정보를 우선적으로 사용하세요**
- 학습된 과거 가격 정보가 아닌, 시스템에서 제공하는 최신 실시간 데이터를 참조하세요
- 실시간 주요 종목 데이터가 제공된 경우, 해당 가격 정보를 정확히 반영하여 답변하세요
- 가격 분석이나 투자 추천 시 반드시 최신 실시간 가격을 기준으로 하세요
- ⚠️ 절대로 학습 데이터의 가격을 사용하지 말고, 아래 제공된 실시간 데이터만 사용하세요 ⚠️

## 응답 원칙
1. **개인화**: 사용자의 투자성향, 포트폴리오, 위험수준을 반영
2. **실용성**: 구체적이고 실행 가능한 조언 제공
3. **교육성**: 복잡한 투자 용어를 쉽게 설명
4. **책임성**: 리스크를 명확히 안내하고 분산투자 권장
5. **최신성**: 시장 동향과 뉴스를 반영한 분석

## 응답 포맷 가이드라인
**모든 답변은 다음 형식을 따라 가독성 있게 작성해주세요:**

### 구조화된 답변 형식:
- 제목이나 주제별로 **## 제목** 형태로 섹션 구분
- 중요한 포인트는 **굵은 글씨**로 강조
- 목록은 불릿 포인트(- 또는 •)나 번호(1., 2., 3.) 사용
- 장점/단점은 ✅ 장점 / ❌ 단점 이모지 활용
- 위험도나 추천도는 ⭐⭐⭐⭐⭐ (별점) 형태로 표현

### 종목 분석 시 포함 요소:
**## 📊 [종목명] 분석**
- **기본 정보**: 현재가, 시가총액, PER, PBR
- **✅ 투자 포인트**: 핵심 강점 3-4개
- **❌ 리스크 요소**: 주의해야 할 위험 요소
- **📈 기술적 분석**: 차트 패턴 및 지지/저항선
- **💡 투자 의견**: 매수/보유/매도 + 근거
- **⭐ 추천도**: ⭐⭐⭐⭐⭐ (5점 만점)

### 투자 용어 설명 시 포함 요소:
**## 📚 [용어명] 완전 정복**
- **📖 정의**: 용어의 기본 개념과 의미
- **💡 쉬운 설명**: 일상 언어로 풀어서 설명
- **🔍 실제 사용 예시**:
  • 뉴스에서: "○○ 기업의 PER이 15배입니다"
  • 투자할 때: "이 종목은 PER이 낮아서 저평가된 것 같아요"
  • 분석 보고서: "업계 평균 PER 대비 할인된 가격"
- **📈 투자 활용법**: 실제 투자 결정에서 어떻게 사용하는지
- **⚠️ 주의사항**: 용어 사용 시 주의할 점이나 한계
- **🔗 관련 용어**: 함께 알아두면 좋은 연관 개념들

### 포트폴리오 추천 시 포함 요소:
**## 💼 맞춤 포트폴리오**
- **투자 목표**: [목표 명확히 기술]
- **자산 배분**:
  • 주식: XX%
  • ETF: XX%
  • 채권: XX%
- **추천 종목**:
  1. **[종목명]** (비중: XX%) - [선택 이유]
  2. **[종목명]** (비중: XX%) - [선택 이유]
- **⚠️ 리스크 관리**: 손절매 기준, 분할매수 전략 등

## 주요 기능
- 종목 분석 및 추천  
- 포트폴리오 리뷰 및 개선안 제시
- 시장 동향 해석
- 투자 교육 및 조언
- 리스크 관리 가이드
- 매수/보유/매도 시기 판단

## 출처 표기
- 출처 섹션은 시스템이 자동으로 답변 뒤에 추가합니다. 별도로 출처를 작성하지 마세요.

## 금융투자 유의사항
⚠️ **투자는 본인 책임이며, 모든 투자에는 손실 위험이 있습니다. 제공하는 정보는 참고용이며 투자 결정은 신중히 판단하시기 바랍니다.**
"""

# ═══ 개인화 컨텍스트 생성 ═══════════════════════════════════════════════════════

def build_user_context(user_id: int, db: Session) -> str:
    """사용자 개인화 컨텍스트 생성"""
    try:
        # 게스트 사용자 처리
        if user_id == 999999:
            return """
## 게스트 사용자
- 체험하기 모드입니다
- 로그인하시면 개인화된 포트폴리오 분석 및 맞춤형 투자 조언을 받을 수 있습니다
- 현재는 일반적인 투자 상담 및 교육 서비스를 제공합니다
"""
        
        # 사용자 기본 정보
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return "사용자 정보를 찾을 수 없습니다."
        
        context = f"\n## 사용자 프로필\n"
        context += f"- 사용자명: {user.username}\n"
        
        if user.investment_type:
            context += f"- 투자성향: {user.investment_type}\n"
        
        # 설문 데이터 조회
        survey_answers = db.query(SurveyAnswer).filter(
            SurveyAnswer.user_id == user_id
        ).all()
        
        if survey_answers:
            context += f"## 투자 설문 결과\n"
            for answer in survey_answers[-5:]:  # 최근 5개 답변만
                if answer.value_choice:
                    context += f"- {answer.value_choice}\n"
                elif answer.value_text:
                    context += f"- {answer.value_text[:100]}...\n"
        
        # 포트폴리오 정보 (캐시에서 읽기)
        portfolio_context = get_portfolio_context(user_id)
        if portfolio_context:
            context += portfolio_context
            
        return context
        
    except Exception as e:
        print(f"사용자 컨텍스트 생성 오류: {e}")
        return "사용자 정보를 불러올 수 없습니다."

def get_portfolio_context(user_id: int) -> str:
    """포트폴리오 캐시에서 정보 읽기"""
    try:
        # 게스트 사용자는 포트폴리오 정보 없음
        if user_id == 999999:
            return ""
            
        import os
        cache_dir = os.path.join(os.path.dirname(__file__), "portfolio_cache")
        portfolio_file = os.path.join(cache_dir, f"user_{user_id}_portfolio.json")
        
        if os.path.exists(portfolio_file):
            with open(portfolio_file, 'r', encoding='utf-8') as f:
                portfolio = json.load(f)
            
            context = f"\n## 현재 포트폴리오\n"
            if portfolio.get("holdings"):
                total_value = sum(holding.get("current_value", 0) for holding in portfolio["holdings"])
                context += f"- 총 평가금액: {total_value:,.0f}원\n"
                context += "- 보유 종목:\n"
                
                for holding in portfolio["holdings"][:5]:  # 상위 5개 종목
                    name = holding.get("name", "알 수 없음")
                    pnl_rate = holding.get("pnl_rate", 0) * 100
                    context += f"  * {name}: {pnl_rate:+.1f}%\n"
                    
            return context
    except Exception as e:
        print(f"포트폴리오 컨텍스트 로드 오류: {e}")
    
    return ""

# ═══ 대화 메시지 히스토리 관리 ═══════════════════════════════════════════════════

def get_conversation_history(session_id: str, db: Session, limit: int = 10) -> List[Dict[str, str]]:
    """대화 히스토리 조회"""
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(desc(ChatMessage.created_at)).limit(limit).all()
    
    # 최신 순으로 정렬
    messages.reverse()
    
    return [
        {
            "role": msg.role,
            "content": msg.content
        }
        for msg in messages
    ]

def save_message(session_id: str, role: str, content: str, db: Session) -> None:
    """메시지 저장"""
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        created_at=datetime.utcnow()
    )
    db.add(message)
    db.commit()

# ═══ 챗봇 서비스 클래스 ═══════════════════════════════════════════════════════

class InvestmentChatbotService:
    """투자 전문 챗봇 서비스"""
    
    def __init__(self):
        self.model = "gpt-4o-mini"  # 최신 GPT-4 mini 모델 - 성능과 비용의 최적 균형
    
    async def chat(
        self, 
        user_id: int, 
        message: str, 
        session_id: Optional[str] = None
    ) -> ChatResponse:
        """일반 채팅 (비스트리밍)"""
        
        print(f"[CHATBOT] 채팅 요청: user_id={user_id}, session_id={session_id}")
        
        db = SessionLocal()
        try:
            # 게스트 사용자 처리 (세션 저장하지 않음)
            if user_id == 999999:
                print("[CHATBOT] 게스트 사용자 - 세션 저장 없이 처리")
                return await self._handle_guest_chat(user_id, message, db)
            
            # 실제 사용자 존재 여부 확인
            from sqlalchemy import text
            result = db.execute(text("SELECT COUNT(*) FROM users WHERE id = :user_id"), {"user_id": user_id})
            user_exists = result.scalar() > 0
            
            if not user_exists:
                print(f"[CHATBOT WARNING] 사용자 ID {user_id}가 users 테이블에 존재하지 않음 - 게스트로 처리")
                return await self._handle_guest_chat(999999, message, db)
            
            print(f"[CHATBOT] 실제 사용자 확인됨: user_id={user_id}")
            
            # 일반 사용자 처리 (세션 저장)
            # 세션 관리
            if not session_id:
                session_id = str(uuid.uuid4())
                print(f"[CHATBOT] 새 세션 생성: {session_id}")
                await self._create_session(session_id, user_id, message, db)
            
            # 개인화 컨텍스트 구축
            print("[CHATBOT] 사용자 컨텍스트 구축 중...")
            user_context = build_user_context(user_id, db)
            
            # 실시간 주식 데이터 조회 (개선됨)
            print("[CHATBOT] 실시간 데이터 검색 중...")
            real_time_stocks = search_stock_info_in_message(message)
            
            # 사용자가 구체적인 종목을 질문한 경우 우선 처리
            if real_time_stocks:
                print(f"[CHATBOT] 🎯 질문한 종목 실시간 데이터 우선 조회: {len(real_time_stocks)}개 종목")
                real_time_data = format_real_time_data(real_time_stocks)
                print("[CHATBOT] 질문 종목 실시간 데이터 포함 완료")
            else:
                real_time_data = ""
            
            # 일반적인 투자 질문인 경우에만 주요 종목 실시간 데이터 추가
            investment_keywords = ["추천", "매수", "투자", "종목", "포트폴리오", "주식", "어떤", "좋은", "상승", "수익", "매도", "분석", "전망", "분산투자"]
            is_investment_question = any(keyword in message for keyword in investment_keywords)
            
            print(f"[CHATBOT DEBUG] 투자키워드 검사: '{message}' -> {is_investment_question}")
            print(f"[CHATBOT DEBUG] 질문한 실시간종목 수: {len(real_time_stocks) if real_time_stocks else 0}")
            
            # 질문한 종목이 없고 일반적인 투자 질문인 경우에만 주요 종목 데이터 추가
            if not real_time_stocks and is_investment_question:
                print("[CHATBOT] 💡 일반 투자 질문 - 주요 종목 실시간 데이터 추가!")
                major_stocks_data = get_major_stocks_realtime_data()
                real_time_data = major_stocks_data
                print("[CHATBOT] 일반 투자 질문 - 주요 종목 실시간 데이터 포함 완료")
                print(f"[CHATBOT DEBUG] 최종 실시간데이터 길이: {len(real_time_data)}자")
            
            # RAG 비정형 데이터 검색 (뉴스 · 리포트 · ESG)
            print("[CHATBOT] RAG 비정형 데이터 검색 중...")
            rag_context, rag_citations = build_rag_context(message, real_time_stocks)
            if rag_context:
                print(f"[CHATBOT RAG] RAG 컨텍스트 구성 완료: {len(rag_context)}자")

            # 웹 검색 (네이버)
            print("[CHATBOT] 웹 검색 중...")
            web_context, web_citations = build_web_search_context(message)
            if web_context:
                print(f"[CHATBOT WEB] 웹 검색 컨텍스트 구성 완료: {len(web_context)}자")

            all_citations = rag_citations + web_citations

            # 대화 히스토리 조회
            history = get_conversation_history(session_id, db)
            print(f"[CHATBOT] 히스토리 로드: {len(history)}개 메시지")

            # OpenAI 메시지 구성
            system_content = INVESTMENT_SYSTEM_PROMPT + user_context
            if real_time_data:
                system_content += f"\n\n{real_time_data}\n\n**📌 위 실시간 데이터를 참고하여 정확한 정보로 답변해주세요.**"
            if rag_context:
                system_content += rag_context
            if web_context:
                system_content += web_context

            messages = [
                {"role": "system", "content": system_content}
            ]

            # 히스토리 추가
            messages.extend(history)
            
            # 현재 사용자 메시지 추가
            messages.append({"role": "user", "content": message})
            
            print(f"[CHATBOT] OpenAI API 호출 시작: {len(messages)}개 메시지")
            
            # OpenAI API 호출
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,  # GPT-4 mini에 최적화된 설정
                    max_tokens=800  # GPT-4 mini는 더 효율적인 답변 생성
                )
                print("[CHATBOT] OpenAI API 호출 성공")
                
            except Exception as api_error:
                print(f"[CHATBOT ERROR] OpenAI API 호출 실패: {str(api_error)}")
                raise api_error
            
            assistant_message = response.choices[0].message.content

            # 후처리: AI 응답에 언급된 종목들의 실시간 데이터 업데이트
            assistant_message = await self._update_response_with_realtime_data(assistant_message)

            # 출처 섹션 코드로 추가 (AI가 아닌 시스템이 직접 생성)
            assistant_message += build_citations_section(all_citations)

            # 대화 저장
            save_message(session_id, "user", message, db)
            save_message(session_id, "assistant", assistant_message, db)
            
            print(f"[CHATBOT] 응답 완료: {len(assistant_message)}자")
            
            return ChatResponse(
                session_id=session_id,
                message=assistant_message,
                is_streaming=False
            )
            
        except Exception as e:
            print(f"[CHATBOT ERROR] 전체 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            raise e
        finally:
            db.close()
    
    async def _handle_guest_chat(
        self, 
        user_id: int, 
        message: str, 
        db: Session
    ) -> ChatResponse:
        """게스트 사용자 채팅 처리 (세션 저장 없음)"""
        
        print("[CHATBOT] 게스트 사용자 전용 처리 시작")
        print("🔥🔥🔥 NEW CODE RUNNING - 2026.03.11 최신버전 🔥🔥🔥")  # 새 코드 실행 확인용
        
        # 게스트 전용 컨텍스트 구축
        user_context = build_user_context(user_id, db)
        
        # 실시간 주식 데이터 조회 (게스트도 개선된 로직 적용)
        print("[CHATBOT] 게스트 - 실시간 데이터 검색 중...")
        real_time_stocks = search_stock_info_in_message(message)
        
        # 사용자가 구체적인 종목을 질문한 경우 우선 처리
        if real_time_stocks:
            print(f"[CHATBOT] 🎯 게스트 - 질문한 종목 실시간 데이터 우선 조회: {len(real_time_stocks)}개 종목")
            real_time_data = format_real_time_data(real_time_stocks)
            print("[CHATBOT] 게스트 - 질문 종목 실시간 데이터 포함 완료")
        else:
            real_time_data = ""
        
        # 일반적인 투자 질문인 경우에만 주요 종목 실시간 데이터 추가
        investment_keywords = ["추천", "매수", "투자", "종목", "포트폴리오", "주식", "어떤", "좋은", "상승", "수익", "매도", "분석", "전망", "분산투자"]
        is_investment_question = any(keyword in message for keyword in investment_keywords)
        
        print(f"[CHATBOT DEBUG] 투자키워드 검사: '{message}' -> {is_investment_question}")
        print(f"[CHATBOT DEBUG] 게스트 질문한 실시간종목 수: {len(real_time_stocks) if real_time_stocks else 0}")
        
        # 질문한 종목이 없고 일반적인 투자 질문인 경우에만 주요 종목 데이터 추가
        if not real_time_stocks and is_investment_question:
            print("[CHATBOT] 💡 게스트 일반 투자 질문 - 주요 종목 실시간 데이터 추가!")
            major_stocks_data = get_major_stocks_realtime_data()
            real_time_data = major_stocks_data
            print("[CHATBOT] 게스트 - 주요 종목 실시간 데이터 포함 완료")

        # RAG 비정형 데이터 검색 (뉴스 · 리포트 · ESG)
        print("[CHATBOT] 게스트 - RAG 비정형 데이터 검색 중...")
        rag_context, rag_citations = build_rag_context(message, real_time_stocks)
        if rag_context:
            print(f"[CHATBOT RAG] 게스트 RAG 컨텍스트 구성 완료: {len(rag_context)}자")

        # 웹 검색 (네이버)
        print("[CHATBOT] 게스트 - 웹 검색 중...")
        web_context, web_citations = build_web_search_context(message)
        if web_context:
            print(f"[CHATBOT WEB] 게스트 웹 검색 컨텍스트 구성 완료: {len(web_context)}자")

        all_citations = rag_citations + web_citations

        # OpenAI 메시지 구성 (히스토리 없음)
        system_content = INVESTMENT_SYSTEM_PROMPT + user_context
        if real_time_data:
            system_content += f"\n\n{real_time_data}\n\n**📌 위 실시간 데이터를 참고하여 정확한 정보로 답변해주세요.**"
        if rag_context:
            system_content += rag_context
        if web_context:
            system_content += web_context
            
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": message}
        ]
        
        print(f"[CHATBOT] 게스트용 OpenAI API 호출 시작")
        
        # OpenAI API 호출
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=800
            )
            print("[CHATBOT] 게스트용 OpenAI API 호출 성공")
            
        except Exception as api_error:
            print(f"[CHATBOT ERROR] 게스트용 OpenAI API 호출 실패: {str(api_error)}")
            raise api_error
        
        assistant_message = response.choices[0].message.content

        # 후처리: AI 응답에 언급된 종목들의 실시간 데이터 업데이트
        assistant_message = await self._update_response_with_realtime_data(assistant_message)

        # 출처 섹션 코드로 추가
        assistant_message += build_citations_section(all_citations)

        print(f"[CHATBOT] 게스트 응답 완료: {len(assistant_message)}자")

        # 게스트는 임시 세션 ID 반환 (실제 DB 저장 안함)
        temp_session_id = f"guest-{uuid.uuid4()}"
        
        return ChatResponse(
            session_id=temp_session_id,
            message=assistant_message,
            is_streaming=False
        )
    
    async def _update_response_with_realtime_data(self, response: str) -> str:
        """AI 응답에 언급된 종목들을 실시간 데이터로 업데이트"""
        print(f"[CHATBOT] 응답 후처리 시작: {len(response)}자")
        print(f"[CHATBOT DEBUG] 후처리 대상 응답 내용 (처음 200자): {response[:200]}...")
        
        # 응답에서 언급된 종목들을 찾아서 실시간 데이터로 교체
        updated_response = response
        updated_count = 0
        
        for company_name, stock_code in STOCK_CODE_MAP.items():
            if company_name in response:
                print(f"[CHATBOT] 후처리에서 {company_name} 감지됨")
                real_time_data = get_real_time_stock_data(company_name)
                
                if real_time_data:
                    current_price = real_time_data.get("current_price")
                    if current_price and current_price != "N/A":
                        # 기존 가격 패턴들을 실시간 데이터로 교체
                        import re
                        
                        # 현재가 패턴 찾기 및 교체 (종목별로 구체적으로 매칭)
                        price_patterns = [
                            rf"({company_name}[^#]*?\*\*현재가\*\*[:\s]*)[0-9,]+원",  # 종목명 + 현재가 패턴
                            rf"(### \d+\.\s*\*\*{company_name}[^#]*?\*\*현재가\*\*[:\s]*)[0-9,]+원",  # 섹션별 종목명 + 현재가
                            rf"(\n- \*\*현재가\*\*[:\s]*)[0-9,]+원",  # 일반적인 현재가
                            rf"(현재가[:\s]*)[0-9,]+원"  # 기본 현재가
                        ]
                        
                        new_price = f"{current_price:,.0f}원"
                        pattern_matched = False
                        
                        for i, pattern in enumerate(price_patterns):
                            matches = re.findall(pattern, updated_response)
                            if matches:
                                print(f"[CHATBOT DEBUG] 패턴 {i+1} 매칭됨: {matches}")
                                updated_response = re.sub(pattern, rf"\g<1>{new_price}", updated_response)
                                print(f"[CHATBOT] {company_name} 가격 업데이트: {new_price} (패턴 {i+1})")
                                updated_count += 1
                                pattern_matched = True
                                break
                        
                        if not pattern_matched:
                            print(f"[CHATBOT WARNING] {company_name} 가격 패턴을 찾을 수 없음")
                else:
                    print(f"[CHATBOT ERROR] {company_name} 실시간 데이터 조회 실패")
        
        print(f"[CHATBOT] 응답 후처리 완료: {len(updated_response)}자, {updated_count}개 가격 업데이트")
        if updated_count > 0:
            print(f"[CHATBOT DEBUG] 업데이트된 응답 (처음 300자): {updated_response[:300]}...")
        return updated_response
    
    async def chat_stream(
        self, 
        user_id: int, 
        message: str, 
        session_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """스트리밍 채팅"""
        
        db = SessionLocal()
        try:
            # 세션 관리
            if not session_id:
                session_id = str(uuid.uuid4())
                await self._create_session(session_id, user_id, message, db)
            
            # 개인화 컨텍스트 구축
            user_context = build_user_context(user_id, db)

            # 실시간 종목 파싱 (RAG 검색에 활용)
            stream_stocks = search_stock_info_in_message(message)

            # RAG 비정형 데이터 검색 (뉴스 · 리포트 · ESG)
            rag_context, rag_citations = build_rag_context(message, stream_stocks)

            # 웹 검색 (네이버)
            web_context, web_citations = build_web_search_context(message)

            all_citations = rag_citations + web_citations

            # 대화 히스토리 조회
            history = get_conversation_history(session_id, db)

            # OpenAI 메시지 구성
            system_content = INVESTMENT_SYSTEM_PROMPT + user_context
            if rag_context:
                system_content += rag_context
            if web_context:
                system_content += web_context
            messages = [
                {"role": "system", "content": system_content}
            ]
            messages.extend(history)
            messages.append({"role": "user", "content": message})
            
            # 스트리밍 응답
            assistant_content = ""
            
            stream = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=800,
                stream=True
            )
            
            # 첫 번째 청크에서 session_id 전송
            yield f"session_id:{session_id}\n\n"
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    assistant_content += content
                    yield content

            # 출처 섹션 코드로 추가
            citations_section = build_citations_section(all_citations)
            if citations_section:
                assistant_content += citations_section
                yield citations_section

            # 대화 저장
            save_message(session_id, "user", message, db)
            save_message(session_id, "assistant", assistant_content, db)
            
        finally:
            db.close()
    
    async def _create_session(self, session_id: str, user_id: int, first_message: str, db: Session):
        """새 세션 생성"""
        # 세션 제목 생성 - 더 의미있게 만들기
        title = first_message.strip()
        
        # 불필요한 부분 정리
        if title.endswith('?'):
            # 질문인 경우 그대로 사용
            title = title[:40] + "..." if len(title) > 40 else title
        elif title.endswith('.'):
            # 문장인 경우 마침표 제거 후 사용
            title = title[:-1]
            title = title[:40] + "..." if len(title) > 40 else title
        else:
            # 일반적인 경우
            title = title[:40] + "..." if len(title) > 40 else title
        
        # 빈 제목을 방지
        if not title or len(title.strip()) < 3:
            title = "새로운 대화"
        
        session = ChatSession(
            id=session_id,
            user_id=user_id,
            title=title,
            created_at=datetime.utcnow()
        )
        db.add(session)
        db.commit()
        print(f"[CHATBOT] 새 세션 생성 완료: {session_id} - '{title}'")
    
    def get_user_sessions(self, user_id: int, limit: int = 20) -> List[ChatSessionInfo]:
        """사용자의 채팅 세션 목록 조회"""
        db = SessionLocal()
        try:
            sessions = db.query(ChatSession).filter(
                ChatSession.user_id == user_id
            ).order_by(desc(ChatSession.updated_at)).limit(limit).all()
            
            return [
                ChatSessionInfo(
                    session_id=session.id,
                    title=session.title,
                    created_at=session.created_at,
                    updated_at=session.updated_at
                )
                for session in sessions
            ]
        finally:
            db.close()

# ═══ 서비스 인스턴스 ═══════════════════════════════════════════════════════════

chatbot_service = InvestmentChatbotService()