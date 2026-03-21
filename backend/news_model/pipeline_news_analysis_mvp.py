import os
import re
import json
import time
import html
import hashlib
import argparse
import urllib.parse
from datetime import datetime, timedelta
from difflib import get_close_matches, SequenceMatcher

import requests
import chromadb
import mysql.connector

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# =========================================================
# 환경설정
# =========================================================

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

NEWS_CHROMA_PATH = os.getenv("NEWS_CHROMA_PATH", "./news_chroma_db")

ANALYSIS_VERSION = "news_mvp_v2_dedup"

# 최근 며칠치 기사와 유사도 비교할지
DEDUP_LOOKBACK_DAYS = 3

# 제목/본문 유사도 임계치
TITLE_SIM_THRESHOLD = 0.92
BODY_SIM_THRESHOLD = 0.88

DEFAULT_QUERIES = [
    "미국 연준 금리",
    "원달러 환율",
    "유가",
    "중국 소비 회복",
    "반도체 업황",
    "HBM",
    "반도체 후공정",
    "AI 반도체 시장",
    "2차전지 업황",
    "양극재",
    "바이오 업황",
    "CDMO",
    "원전 수주",
    "원전 기자재",
    "로봇 산업",
    "화장품 ODM",
    "조선 기자재",
    "방산 수출",
    "우주항공",
    "인터넷 플랫폼",
    "클라우드 산업"
]

# 자유 추출 후 정규화용 taxonomy
CANONICAL_THEMES = [
    "반도체", "AI반도체", "HBM", "메모리", "반도체 후공정", "유리기판", "파운드리",
    "2차전지", "양극재", "음극재", "전해질", "분리막", "폐배터리", "전고체배터리",
    "바이오", "바이오의약품", "바이오시밀러", "CDMO", "제약", "의료기기",
    "금융", "은행", "증권", "보험", "카드",
    "인터넷", "플랫폼", "AI", "클라우드", "게임",
    "화장품", "화장품ODM", "뷰티",
    "원전", "원전기자재", "전력기기",
    "로봇", "로봇부품", "자동화",
    "조선", "조선기자재", "LNG",
    "방산", "우주항공", "항공우주부품",
    "건설", "건설기계", "부동산",
    "에너지", "태양광", "풍력", "수소", "정유",
    "소비재", "유통", "식품", "여행", "면세",
    "자동차", "자동차부품", "전기차"
]

THEME_SYNONYMS = {
    "고대역폭 메모리": "HBM",
    "고대역폭메모리": "HBM",
    "ai 메모리": "AI반도체",
    "ai 서버": "AI반도체",
    "패키징": "반도체 후공정",
    "후공정": "반도체 후공정",
    "odm": "화장품ODM",
    "코스메틱": "화장품",
    "cosmetic": "화장품",
    "bank": "은행",
    "cdmo": "CDMO",
    "bio": "바이오",
}

CANONICAL_EVENTS = [
    "금리인하", "금리인상", "환율상승", "환율하락", "유가급등", "유가하락",
    "실적개선", "실적부진", "수주확대", "공급차질", "공급망불안", "공급망재편",
    "정책지원", "규제강화", "증설", "감산", "수요증가", "수요둔화",
    "파업", "노조리스크", "중국소비회복", "기술개발", "양산개시"
]

EVENT_SYNONYMS = {
    "금리 인하": "금리인하",
    "금리 인상": "금리인상",
    "환율 상승": "환율상승",
    "환율 하락": "환율하락",
    "유가 급등": "유가급등",
    "유가 하락": "유가하락",
    "실적 개선": "실적개선",
    "실적 부진": "실적부진",
    "수주 확대": "수주확대",
    "공급망 불안": "공급망불안",
    "공급망 재편": "공급망재편",
    "정책 지원": "정책지원",
    "규제 강화": "규제강화",
    "수요 증가": "수요증가",
    "수요 둔화": "수요둔화",
    "양산 시작": "양산개시",
    "양산 개시": "양산개시",
    "노조 리스크": "노조리스크",
}

# ── OpenAI client lazy 초기화 ────────────────────────────────────────────────
_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client


# ── ChromaDB lazy 초기화 ──────────────────────────────────────────────────────
# 모듈 import 시점이 아닌 실제 첫 사용 시점에 연결 (서버 기동 보호)
_chroma_client = None
_news_analysis_index = None
_chroma_init_lock = __import__("threading").Lock()  # 멀티스레드 동시 초기화 방지
_chroma_query_lock = __import__("threading").Lock()  # SQLite 동시 쿼리 경쟁 방지


def _get_chroma_index():
    """ChromaDB 클라이언트와 컬렉션을 lazy 싱글턴으로 반환합니다."""
    global _chroma_client, _news_analysis_index
    if _news_analysis_index is None:
        with _chroma_init_lock:
            if _news_analysis_index is None:  # double-checked locking
                _chroma_client = chromadb.PersistentClient(path=NEWS_CHROMA_PATH)
                _news_analysis_index = _chroma_client.get_or_create_collection(
                    name="news_analysis_index"
                )
    return _news_analysis_index


# 하위 호환성: 기존 코드가 news_analysis_index 를 직접 참조하는 경우를 위한 proxy
class _CollectionProxy:
    """news_analysis_index 를 직접 쓰는 기존 코드를 그대로 동작하게 하는 프록시."""
    def upsert(self, *a, **kw):
        return _get_chroma_index().upsert(*a, **kw)
    def delete(self, *a, **kw):
        return _get_chroma_index().delete(*a, **kw)
    def query(self, *a, **kw):
        return _get_chroma_index().query(*a, **kw)
    def get(self, *a, **kw):
        return _get_chroma_index().get(*a, **kw)
    def add(self, *a, **kw):
        return _get_chroma_index().add(*a, **kw)


news_analysis_index = _CollectionProxy()

# =========================================================
# 유틸
# =========================================================

def get_mysql():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        autocommit=False
    )


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def md5_hash(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def safe_json_loads(text, default=None):
    try:
        return json.loads(text)
    except Exception:
        return default


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace("<b>", "").replace("</b>", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def is_korean_text(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[가-힣]", text))


def is_meaningful_article(title: str, body: str, min_body_len: int = 60) -> bool:
    """
    너무 짧은 속보/시세 기사 제거용
    """
    title = normalize_text(title)
    body = normalize_text(body)

    if len(body) < min_body_len:
        return False

    noisy_patterns = [
        r"^\[속보\]",
        r"마감$",
        r"장중$",
        r"오전장$",
        r"오후장$",
        r"종가$",
    ]

    # 제목이 너무 짧고 body도 짧으면 제거
    if len(title) < 12 and len(body) < 80:
        return False

    for p in noisy_patterns:
        if re.search(p, title):
            # 속보라도 body가 충분히 길면 살릴 수 있지만,
            # MVP에선 보수적으로 제거
            return False

    return True

def normalize_title_for_dedup(title: str) -> str:
    title = normalize_text(title).lower()
    title = re.sub(r"[^가-힣a-z0-9 ]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def normalize_body_for_dedup(body: str) -> str:
    body = normalize_text(body).lower()
    body = re.sub(r"\s+", " ", body).strip()
    return body


def build_content_hash(title: str, body: str) -> str:
    norm_title = normalize_title_for_dedup(title)
    norm_body = normalize_body_for_dedup(body)
    return md5_hash(f"{norm_title}\n{norm_body}")


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "").ratio()


def unique_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if x is None:
            continue
        x = str(x).strip()
        if not x:
            continue
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def normalize_theme(theme: str):
    if not theme:
        return None
    raw = theme.strip()
    low = raw.lower()

    if low in THEME_SYNONYMS:
        return THEME_SYNONYMS[low]

    for t in CANONICAL_THEMES:
        if raw == t:
            return t

    matched = get_close_matches(raw, CANONICAL_THEMES, n=1, cutoff=0.8)
    if matched:
        return matched[0]

    return raw


def normalize_event(event: str):
    if not event:
        return None
    raw = event.strip()
    low = raw.lower()

    if low in EVENT_SYNONYMS:
        return EVENT_SYNONYMS[low]

    for e in CANONICAL_EVENTS:
        if raw == e:
            return e

    matched = get_close_matches(raw, CANONICAL_EVENTS, n=1, cutoff=0.8)
    if matched:
        return matched[0]

    return raw


def get_embedding(text: str):
    text = (text or "").strip()
    if not text:
        return []
    res = _get_openai_client().embeddings.create(
        model=OPENAI_EMBED_MODEL,
        input=text
    )
    return res.data[0].embedding


# =========================================================
# 스키마
# =========================================================

def init_db():
    conn = get_mysql()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS news_raw (
        news_id VARCHAR(64) PRIMARY KEY,
        source VARCHAR(50),
        source_url TEXT,
        title TEXT,
        body_or_desc TEXT,
        published_at DATETIME,
        ingested_at DATETIME,
        query_topic VARCHAR(255),
        content_hash VARCHAR(64),
        dedup_key VARCHAR(255),
        is_duplicate TINYINT DEFAULT 0,
        duplicate_of_news_id VARCHAR(64) NULL,
        dedup_method VARCHAR(50) NULL,
        INDEX idx_published_at (published_at),
        INDEX idx_query_topic (query_topic),
        INDEX idx_content_hash (content_hash),
        INDEX idx_dedup_key (dedup_key),
        INDEX idx_is_duplicate (is_duplicate),
        INDEX idx_duplicate_of_news_id (duplicate_of_news_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS news_analysis (
        news_id VARCHAR(64) PRIMARY KEY,
        mentioned_entities_json JSON,
        companies_json JSON,
        organizations_json JSON,
        themes_json JSON,
        industries_json JSON,
        events_json JSON,
        sentiment VARCHAR(20),
        importance_score FLOAT,
        risk_points_json JSON,
        opportunity_points_json JSON,
        article_summary TEXT,
        raw_extraction_json JSON,
        analysis_version VARCHAR(50),
        analyzed_at DATETIME,
        FOREIGN KEY (news_id) REFERENCES news_raw(news_id)
    )
    """)

    conn.commit()
    conn.close()
    print("✅ init-db 완료")


# =========================================================
# 뉴스 수집
# =========================================================

def fetch_naver_news(query, days_back=90, max_items=300):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 필요합니다.")

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    limit_date = datetime.now() - timedelta(days=days_back)
    enc_query = urllib.parse.quote(query)

    all_news = []
    seen_links = set()

    for start_idx in range(1, min(max_items, 1000) + 1, 100):
        url = f"https://openapi.naver.com/v1/search/news.json?query={enc_query}&display=100&start={start_idx}&sort=date"

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                break

            items = response.json().get("items", [])
            if not items:
                break

            stop_outer = False
            for item in items:
                link = item.get("link", "")
                if not link or link in seen_links:
                    continue

                pub_dt = datetime.strptime(item["pubDate"], "%a, %d %b %Y %H:%M:%S +0900")
                if pub_dt < limit_date:
                    stop_outer = True
                    break

                title = normalize_text(item.get("title", ""))
                desc = normalize_text(item.get("description", ""))

                # 한국어 기사만 수집
                if not is_korean_text(title):
                    continue

                # 너무 짧은 기사/속보 제거
                if not is_meaningful_article(title, desc, min_body_len=60):
                    continue

                news_id = md5_hash(link)  # 링크 중복 제거
                content_hash = build_content_hash(title, desc)  # 내용 해시 중복 제거
                dedup_key = normalize_title_for_dedup(title)

                all_news.append({
                    "news_id": news_id,
                    "source": "naver_news",
                    "source_url": link,
                    "title": title,
                    "body_or_desc": desc,
                    "published_at": pub_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "ingested_at": now_str(),
                    "query_topic": query,
                    "content_hash": content_hash,
                    "dedup_key": dedup_key
                })
                seen_links.add(link)

            if stop_outer:
                break

            time.sleep(0.05)
        except Exception:
            break

    return all_news


# =========================================================
# 중복 제거
# =========================================================

def find_duplicate_news(conn, news):
    """
    우선순위:
    1) 링크 기반 중복: news_id
    2) 내용 해시 기반 중복: content_hash
    3) 제목/내용 유사도 기반 논리 중복
    """
    cur = conn.cursor(dictionary=True)

    # 1. 링크 기반 중복 (news_id)
    cur.execute("""
        SELECT news_id
        FROM news_raw
        WHERE news_id = %s
        LIMIT 1
    """, (news["news_id"],))
    row = cur.fetchone()
    if row:
        return {
            "is_duplicate": 1,
            "duplicate_of_news_id": row["news_id"],
            "dedup_method": "news_id"
        }

    # 2. content_hash 기반 중복
    cur.execute("""
        SELECT news_id
        FROM news_raw
        WHERE content_hash = %s
        LIMIT 1
    """, (news["content_hash"],))
    row = cur.fetchone()
    if row:
        return {
            "is_duplicate": 1,
            "duplicate_of_news_id": row["news_id"],
            "dedup_method": "content_hash"
        }
    
    # 2.5 dedup_key 동일 기사 우선 검사
    cur.execute("""
        SELECT news_id, title, body_or_desc, published_at
        FROM news_raw
        WHERE dedup_key = %s
        ORDER BY published_at DESC
        LIMIT 20
    """, (news["dedup_key"],))
    same_title_rows = cur.fetchall()

    for row in same_title_rows:
        return {
            "is_duplicate": 1,
            "duplicate_of_news_id": row["news_id"],
            "dedup_method": "dedup_key"
        }

    # 3. 제목/내용 유사도 기반 논리 중복
    published_dt = datetime.strptime(news["published_at"], "%Y-%m-%d %H:%M:%S")
    from_dt = (published_dt - timedelta(days=DEDUP_LOOKBACK_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        SELECT news_id, title, body_or_desc, published_at
        FROM news_raw
        WHERE published_at >= %s
        ORDER BY published_at DESC
        LIMIT 300
    """, (from_dt,))
    rows = cur.fetchall()

    new_title = normalize_title_for_dedup(news["title"])
    new_body = normalize_body_for_dedup(news["body_or_desc"])

    for row in rows:
        old_title = normalize_title_for_dedup(row["title"])
        old_body = normalize_body_for_dedup(row["body_or_desc"])

        title_sim = text_similarity(new_title, old_title)
        body_sim = text_similarity(new_body, old_body)

        if title_sim >= TITLE_SIM_THRESHOLD and body_sim >= BODY_SIM_THRESHOLD:
            return {
                "is_duplicate": 1,
                "duplicate_of_news_id": row["news_id"],
                "dedup_method": "similarity"
            }

    return {
        "is_duplicate": 0,
        "duplicate_of_news_id": None,
        "dedup_method": None
    }


def save_news_raw(news_list):
    if not news_list:
        return 0

    conn = get_mysql()
    cur = conn.cursor()

    inserted_count = 0
    duplicate_count = 0

    for n in news_list:
        dup = find_duplicate_news(conn, n)

        cur.execute("""
            INSERT INTO news_raw(
                news_id, source, source_url, title, body_or_desc,
                published_at, ingested_at, query_topic, content_hash, dedup_key,
                is_duplicate, duplicate_of_news_id, dedup_method
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                title=VALUES(title),
                body_or_desc=VALUES(body_or_desc),
                published_at=VALUES(published_at),
                query_topic=VALUES(query_topic),
                content_hash=VALUES(content_hash),
                dedup_key=VALUES(dedup_key),
                is_duplicate=VALUES(is_duplicate),
                duplicate_of_news_id=VALUES(duplicate_of_news_id),
                dedup_method=VALUES(dedup_method)
        """, (
            n["news_id"],
            n["source"],
            n["source_url"],
            n["title"],
            n["body_or_desc"],
            n["published_at"],
            n["ingested_at"],
            n["query_topic"],
            n["content_hash"],
            n["dedup_key"],
            dup["is_duplicate"],
            dup["duplicate_of_news_id"],
            dup["dedup_method"]
        ))

        inserted_count += 1
        if dup["is_duplicate"] == 1:
            duplicate_count += 1

    conn.commit()
    conn.close()

    print(f"  ↳ 저장 완료: 총 {inserted_count}건 / 중복 플래그 {duplicate_count}건")
    return inserted_count


# =========================================================
# 자유 추출 기반 뉴스 분석
# =========================================================

def llm_analyze_news_freeform(title, body):
    prompt = f"""
너는 금융 뉴스 비정형 데이터 분석기다.
아래 뉴스를 읽고, 투자 분석에 활용할 수 있도록 구조화하라.
후보 사전에 의존하지 말고 뉴스 내용에 근거해 자유롭게 추출하라.
반드시 JSON만 출력하라.

규칙:
1) mentioned_entities: 사람, 기업, 기관, 제품, 국가 등 핵심 명사
2) companies: 기업명만
3) organizations: 정부/기관/단체/노조/협회/국가 기관 등
4) themes: 투자/산업 관점의 테마
5) industries: 산업/업종
6) events: 시장/산업 이벤트
7) sentiment: positive / negative / neutral
8) importance_score: 0~1
   아래 기준으로 평가하라.
   - 0.9 ~ 1.0: 시장 전반에 큰 영향을 줄 수 있는 거시/정책/지정학 뉴스
   - 0.7 ~ 0.89: 특정 산업 전반에 영향을 주는 업황/공급망/수요/규제 변화
   - 0.5 ~ 0.69: 개별 기업 또는 일부 산업에 의미 있는 뉴스
   - 0.3 ~ 0.49: 일반 정보성 기사, 영향 범위가 제한적인 뉴스
   - 0.0 ~ 0.29: 단순 홍보성/반복성/의미가 약한 기사
9) risk_points: 리스크 요점 리스트
10) opportunity_points: 기회 요점 리스트
11) article_summary: 2문장 이내 요약
12) JSON 외 텍스트 금지
13) importance_score는 기사의 시장 영향 범위와 산업 파급력 기준으로 평가하고, 단순 기사 길이나 자극적인 표현만으로 높게 주지 말 것

뉴스 제목:
{title}

뉴스 내용:
{body}

출력 형식:
{{
  "mentioned_entities": [],
  "companies": [],
  "organizations": [],
  "themes": [],
  "industries": [],
  "events": [],
  "sentiment": "neutral",
  "importance_score": 0.5,
  "risk_points": [],
  "opportunity_points": [],
  "article_summary": ""
}}
"""
    try:
        res = _get_openai_client().chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        content = res.choices[0].message.content.strip()
        parsed = safe_json_loads(content, None)
        return parsed
    except Exception:
        return None


def postprocess_analysis(analysis):
    if analysis is None:
        return {
            "mentioned_entities": [],
            "companies": [],
            "organizations": [],
            "themes": [],
            "industries": [],
            "events": [],
            "sentiment": "neutral",
            "importance_score": 0.5,
            "risk_points": [],
            "opportunity_points": [],
            "article_summary": "",
            "raw_extraction": {}
        }

    themes = [normalize_theme(x) for x in analysis.get("themes", [])]
    events = [normalize_event(x) for x in analysis.get("events", [])]

    return {
        "mentioned_entities": unique_keep_order(analysis.get("mentioned_entities", [])),
        "companies": unique_keep_order(analysis.get("companies", [])),
        "organizations": unique_keep_order(analysis.get("organizations", [])),
        "themes": unique_keep_order(themes),
        "industries": unique_keep_order(analysis.get("industries", [])),
        "events": unique_keep_order(events),
        "sentiment": analysis.get("sentiment", "neutral"),
        "importance_score": float(analysis.get("importance_score", 0.5)),
        "risk_points": unique_keep_order(analysis.get("risk_points", [])),
        "opportunity_points": unique_keep_order(analysis.get("opportunity_points", [])),
        "article_summary": (analysis.get("article_summary", "") or "").strip(),
        "raw_extraction": analysis
    }


def save_news_analysis(news_id, analysis):
    conn = get_mysql()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO news_analysis(
            news_id,
            mentioned_entities_json,
            companies_json,
            organizations_json,
            themes_json,
            industries_json,
            events_json,
            sentiment,
            importance_score,
            risk_points_json,
            opportunity_points_json,
            article_summary,
            raw_extraction_json,
            analysis_version,
            analyzed_at
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            mentioned_entities_json=VALUES(mentioned_entities_json),
            companies_json=VALUES(companies_json),
            organizations_json=VALUES(organizations_json),
            themes_json=VALUES(themes_json),
            industries_json=VALUES(industries_json),
            events_json=VALUES(events_json),
            sentiment=VALUES(sentiment),
            importance_score=VALUES(importance_score),
            risk_points_json=VALUES(risk_points_json),
            opportunity_points_json=VALUES(opportunity_points_json),
            article_summary=VALUES(article_summary),
            raw_extraction_json=VALUES(raw_extraction_json),
            analysis_version=VALUES(analysis_version),
            analyzed_at=VALUES(analyzed_at)
    """, (
        news_id,
        json.dumps(analysis["mentioned_entities"], ensure_ascii=False),
        json.dumps(analysis["companies"], ensure_ascii=False),
        json.dumps(analysis["organizations"], ensure_ascii=False),
        json.dumps(analysis["themes"], ensure_ascii=False),
        json.dumps(analysis["industries"], ensure_ascii=False),
        json.dumps(analysis["events"], ensure_ascii=False),
        analysis["sentiment"],
        analysis["importance_score"],
        json.dumps(analysis["risk_points"], ensure_ascii=False),
        json.dumps(analysis["opportunity_points"], ensure_ascii=False),
        analysis["article_summary"],
        json.dumps(analysis["raw_extraction"], ensure_ascii=False),
        ANALYSIS_VERSION,
        now_str()
    ))

    conn.commit()
    conn.close()


# =========================================================
# Chroma 인덱싱
# =========================================================

def index_news_analysis(news_row, analysis):
    doc = f"""
    [NEWS]
    title: {news_row['title']}
    summary: {analysis['article_summary']}
    themes: {", ".join(analysis['themes'])}
    events: {", ".join(analysis['events'])}
    companies: {", ".join(analysis['companies'])}
    organizations: {", ".join(analysis['organizations'])}
    industries: {", ".join(analysis['industries'])}
    risk: {", ".join(analysis['risk_points'])}
    opportunity: {", ".join(analysis['opportunity_points'])}
    sentiment: {analysis['sentiment']}
    """.strip()

    emb = get_embedding(doc)

    news_analysis_index.upsert(
        ids=[news_row["news_id"]],
        documents=[doc],
        embeddings=[emb],
        metadatas=[{
            "news_id": news_row["news_id"],
            "published_at": str(news_row["published_at"]),
            "query_topic": news_row["query_topic"],
            "sentiment": analysis["sentiment"],
            "importance_score": analysis["importance_score"],
            "title": news_row.get("title", "") or "",
            "source_url": news_row.get("source_url", "") or "",
        }]
    )


def reindex_all_to_chroma(batch_size: int = 50) -> int:
    """MySQL news_analysis 전체를 ChromaDB에 재색인합니다.
    ChromaDB가 비어있거나 손상된 경우 복구용으로 사용합니다.
    Returns: 색인된 문서 수
    """
    conn = get_mysql()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            nr.news_id, nr.title, nr.source_url, nr.published_at, nr.query_topic,
            na.article_summary,
            na.themes_json, na.events_json, na.companies_json,
            na.organizations_json, na.industries_json,
            na.risk_points_json, na.opportunity_points_json,
            na.sentiment, na.importance_score
        FROM news_raw nr
        JOIN news_analysis na ON nr.news_id = na.news_id
        WHERE nr.is_duplicate = 0
        ORDER BY nr.published_at DESC
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("재색인할 데이터가 없습니다.")
        return 0

    print(f"총 {len(rows)}건 재색인 시작...")
    indexed = 0

    for i, row in enumerate(rows, 1):
        try:
            analysis = {
                "article_summary": row["article_summary"] or "",
                "themes":        json.loads(row["themes_json"] or "[]"),
                "events":        json.loads(row["events_json"] or "[]"),
                "companies":     json.loads(row["companies_json"] or "[]"),
                "organizations": json.loads(row["organizations_json"] or "[]"),
                "industries":    json.loads(row["industries_json"] or "[]"),
                "risk_points":   json.loads(row["risk_points_json"] or "[]"),
                "opportunity_points": json.loads(row["opportunity_points_json"] or "[]"),
                "sentiment":     row["sentiment"] or "neutral",
                "importance_score": float(row["importance_score"] or 0.5),
            }
            index_news_analysis(row, analysis)
            indexed += 1
            if i % batch_size == 0:
                print(f"  진행: {i}/{len(rows)}건")
        except Exception as e:
            print(f"  [SKIP] {row['news_id']}: {e}")

    print(f"✅ 재색인 완료: {indexed}건")
    return indexed


# =========================================================
# 배치
# =========================================================

def collect_news(days_back=90, queries=None):
    queries = queries or DEFAULT_QUERIES
    all_rows = []

    for query in queries:
        news_list = fetch_naver_news(query, days_back=days_back, max_items=300)
        save_news_raw(news_list)
        all_rows.extend(news_list)
        print(f"collected: {query} -> {len(news_list)}건")
        time.sleep(0.2)

    return all_rows


def get_unanalyzed_news(limit=500):
    conn = get_mysql()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT nr.*
        FROM news_raw nr
        LEFT JOIN news_analysis na
            ON nr.news_id = na.news_id
        WHERE na.news_id IS NULL
          AND nr.is_duplicate = 0
        ORDER BY nr.published_at DESC
        LIMIT %s
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return rows


def analyze_pending_news(limit=500):
    rows = get_unanalyzed_news(limit=limit)
    print(f"pending analysis (non-duplicate only): {len(rows)}건")

    for i, row in enumerate(rows, start=1):
        raw = llm_analyze_news_freeform(row["title"], row["body_or_desc"])
        analysis = postprocess_analysis(raw)

        save_news_analysis(row["news_id"], analysis)
        index_news_analysis(row, analysis)

        print(f"[{i}/{len(rows)}] analyzed -> {row['news_id']}")
        time.sleep(0.15)


def prune_old_news(retention_days=90):
    threshold = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_mysql()
    cur = conn.cursor()

    cur.execute("""
        SELECT news_id
        FROM news_raw
        WHERE published_at < %s
    """, (threshold,))
    old_ids = [r[0] for r in cur.fetchall()]

    if not old_ids:
        conn.close()
        print("삭제할 90일 초과 뉴스 없음")
        return

    placeholders = ",".join(["%s"] * len(old_ids))

    cur.execute(f"DELETE FROM news_analysis WHERE news_id IN ({placeholders})", tuple(old_ids))
    cur.execute(f"DELETE FROM news_raw WHERE news_id IN ({placeholders})", tuple(old_ids))

    conn.commit()
    conn.close()

    chunk_size = 500
    for i in range(0, len(old_ids), chunk_size):
        chunk = old_ids[i:i + chunk_size]
        try:
            news_analysis_index.delete(ids=chunk)
        except Exception:
            pass

    print(f"✅ 90일 초과 뉴스 삭제 완료: {len(old_ids)}건")


def daily_batch(days_back=90, retention_days=90):
    print("🚀 daily-batch 시작")
    collect_news(days_back=days_back)
    analyze_pending_news(limit=1000)
    prune_old_news(retention_days=retention_days)
    print("✅ daily-batch 완료")


# =========================================================
# 조회용
# =========================================================

def search_news_context(query, n_results=5, company_name=None):
    """
    임베딩 유사도로 후보를 넓게 수집한 뒤 유사도(60%) + 최신성(40%) 결합 스코어로 재정렬하여 반환.
    - 후보 풀: n_results * 4 (유사도 기반 광역 검색)
    - company_name 전달 시 해당 기업 관련 기사 우선 필터링
    - 재정렬: similarity 순위 60% + recency 40% 결합 스코어
    - 반환: 상위 n_results 건
    """
    query_emb = get_embedding(query)

    try:
        candidate_size = max(n_results * 4, 20)
        with _chroma_query_lock:  # SQLite 동시 접근 경쟁 방지
            res = news_analysis_index.query(
                query_embeddings=[query_emb],
                n_results=candidate_size
            )

        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]

        # ChromaDB 반환 순서 = 유사도 내림차순 (best first)
        candidates = [{"doc": d, "meta": m} for d, m in zip(docs, metas)]

        # company_name 필터링: query_topic 또는 doc 본문에 회사명 포함 여부
        if company_name:
            filtered = [
                c for c in candidates
                if company_name in c["meta"].get("query_topic", "")
                or company_name in c.get("doc", "")
            ]
            if filtered:
                candidates = filtered

        total = len(candidates)
        now_dt = datetime.now()

        def combined_score(idx, meta):
            # 유사도 스코어: idx가 낮을수록(ChromaDB 상위) 높음
            sim_score = (total - idx) / total if total > 0 else 0.0
            # 최신성 스코어: published_at이 최근일수록 높음 (90일 기준 선형 감쇠)
            pub = meta.get("published_at", "")
            try:
                pub_dt = datetime.fromisoformat(str(pub))
                days_old = max(0, (now_dt - pub_dt).days)
                rec_score = max(0.0, 1.0 - days_old / 90.0)
            except Exception:
                rec_score = 0.0
            return sim_score * 0.6 + rec_score * 0.4

        scored = sorted(
            enumerate(candidates),
            key=lambda x: combined_score(x[0], x[1]["meta"]),
            reverse=True,
        )

        results = [c for _, c in scored[:n_results]]

        # MySQL에서 title, source_url 보완 (ChromaDB 메타에 없는 경우)
        news_ids = [r["meta"].get("news_id") for r in results if r["meta"].get("news_id")]
        if news_ids:
            try:
                conn = get_mysql()
                cur = conn.cursor(dictionary=True)
                placeholders = ",".join(["%s"] * len(news_ids))
                cur.execute(
                    f"SELECT news_id, title, source_url FROM news_raw WHERE news_id IN ({placeholders})",
                    news_ids,
                )
                db_rows = {row["news_id"]: row for row in cur.fetchall()}
                conn.close()
                for r in results:
                    nid = r["meta"].get("news_id")
                    if nid and nid in db_rows:
                        r["meta"]["title"] = db_rows[nid].get("title") or r["meta"].get("title", "")
                        r["meta"]["source_url"] = db_rows[nid].get("source_url") or r["meta"].get("source_url", "")
            except Exception as db_err:
                print(f"[news] MySQL title/url 보완 실패: {db_err}")

        return results

    except Exception as e:
        print("검색 오류:", e)
        return []


# =========================================================
# CLI
# =========================================================

def parse_args():
    parser = argparse.ArgumentParser(description="News Analysis MVP Pipeline")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init-db")

    p_collect = sub.add_parser("collect")
    p_collect.add_argument("--days-back", type=int, default=90)

    p_analyze = sub.add_parser("analyze-pending")
    p_analyze.add_argument("--limit", type=int, default=500)

    p_prune = sub.add_parser("prune")
    p_prune.add_argument("--retention-days", type=int, default=90)

    p_batch = sub.add_parser("daily-batch")
    p_batch.add_argument("--days-back", type=int, default=90)
    p_batch.add_argument("--retention-days", type=int, default=90)

    sub.add_parser("reindex-all")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "init-db":
        init_db()

    elif args.command == "collect":
        collect_news(days_back=args.days_back)

    elif args.command == "analyze-pending":
        analyze_pending_news(limit=args.limit)

    elif args.command == "prune":
        prune_old_news(retention_days=args.retention_days)

    elif args.command == "daily-batch":
        daily_batch(days_back=args.days_back, retention_days=args.retention_days)

    elif args.command == "reindex-all":
        reindex_all_to_chroma()

    else:
        print("""
사용 예시:
  python pipeline_news_analysis_mvp.py init-db
  python pipeline_news_analysis_mvp.py collect --days-back 90
  python pipeline_news_analysis_mvp.py analyze-pending --limit 300
  python pipeline_news_analysis_mvp.py prune --retention-days 90
  python pipeline_news_analysis_mvp.py daily-batch --days-back 90 --retention-days 90
  python pipeline_news_analysis_mvp.py reindex-all
""")


if __name__ == "__main__":
    main()