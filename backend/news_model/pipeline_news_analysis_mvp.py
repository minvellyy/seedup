import os
import re
import json
import time
import html
import hashlib
import argparse
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from difflib import get_close_matches, SequenceMatcher

import requests
import chromadb
import mysql.connector

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# =========================================================
# ?섍꼍?ㅼ젙
# =========================================================

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

CHROMA_PATH = os.getenv(
    "CHROMA_PATH",
    str(Path(__file__).resolve().parent / "chroma_db")
)

ANALYSIS_VERSION = "news_mvp_v2_dedup"

# 理쒓렐 硫곗튌移?湲곗궗? ?좎궗??鍮꾧탳?좎?
DEDUP_LOOKBACK_DAYS = 3

# ?쒕ぉ/蹂몃Ц ?좎궗???꾧퀎移?
TITLE_SIM_THRESHOLD = 0.92
BODY_SIM_THRESHOLD = 0.88

DEFAULT_QUERIES = [
    "誘멸뎅 ?곗? 湲덈━",
    "?먮떖???섏쑉",
    "?좉?",
    "以묎뎅 ?뚮퉬 ?뚮났",
    "諛섎룄泥??낇솴",
    "HBM",
    "諛섎룄泥??꾧났??,
    "AI 諛섎룄泥??쒖옣",
    "2李⑥쟾吏 ?낇솴",
    "?묎레??,
    "諛붿씠???낇솴",
    "CDMO",
    "?먯쟾 ?섏＜",
    "?먯쟾 湲곗옄??,
    "濡쒕큸 ?곗뾽",
    "?붿옣??ODM",
    "議곗꽑 湲곗옄??,
    "諛⑹궛 ?섏텧",
    "?곗＜??났",
    "?명꽣???뚮옯??,
    "?대씪?곕뱶 ?곗뾽"
]

# ?먯쑀 異붿텧 ???뺢퇋?붿슜 taxonomy
CANONICAL_THEMES = [
    "諛섎룄泥?, "AI諛섎룄泥?, "HBM", "硫붾え由?, "諛섎룄泥??꾧났??, "?좊━湲고뙋", "?뚯슫?쒕━",
    "2李⑥쟾吏", "?묎레??, "?뚭레??, "?꾪빐吏?, "遺꾨━留?, "?먮같?곕━", "?꾧퀬泥대같?곕━",
    "諛붿씠??, "諛붿씠?ㅼ쓽?쏀뭹", "諛붿씠?ㅼ떆諛??, "CDMO", "?쒖빟", "?섎즺湲곌린",
    "湲덉쑖", "???, "利앷텒", "蹂댄뿕", "移대뱶",
    "?명꽣??, "?뚮옯??, "AI", "?대씪?곕뱶", "寃뚯엫",
    "?붿옣??, "?붿옣?늀DM", "酉고떚",
    "?먯쟾", "?먯쟾湲곗옄??, "?꾨젰湲곌린",
    "濡쒕큸", "濡쒕큸遺??, "?먮룞??,
    "議곗꽑", "議곗꽑湲곗옄??, "LNG",
    "諛⑹궛", "?곗＜??났", "??났?곗＜遺??,
    "嫄댁꽕", "嫄댁꽕湲곌퀎", "遺?숈궛",
    "?먮꼫吏", "?쒖뼇愿?, "?띾젰", "?섏냼", "?뺤쑀",
    "?뚮퉬??, "?좏넻", "?앺뭹", "?ы뻾", "硫댁꽭",
    "?먮룞李?, "?먮룞李⑤???, "?꾧린李?
]

THEME_SYNONYMS = {
    "怨좊???룺 硫붾え由?: "HBM",
    "怨좊???룺硫붾え由?: "HBM",
    "ai 硫붾え由?: "AI諛섎룄泥?,
    "ai ?쒕쾭": "AI諛섎룄泥?,
    "?⑦궎吏?: "諛섎룄泥??꾧났??,
    "?꾧났??: "諛섎룄泥??꾧났??,
    "odm": "?붿옣?늀DM",
    "肄붿뒪硫뷀떛": "?붿옣??,
    "cosmetic": "?붿옣??,
    "bank": "???,
    "cdmo": "CDMO",
    "bio": "諛붿씠??,
}

CANONICAL_EVENTS = [
    "湲덈━?명븯", "湲덈━?몄긽", "?섏쑉?곸듅", "?섏쑉?섎씫", "?좉?湲됰벑", "?좉??섎씫",
    "?ㅼ쟻媛쒖꽑", "?ㅼ쟻遺吏?, "?섏＜?뺣?", "怨듦툒李⑥쭏", "怨듦툒留앸텋??, "怨듦툒留앹옱??,
    "?뺤콉吏??, "洹쒖젣媛뺥솕", "利앹꽕", "媛먯궛", "?섏슂利앷?", "?섏슂?뷀솕",
    "?뚯뾽", "?몄“由ъ뒪??, "以묎뎅?뚮퉬?뚮났", "湲곗닠媛쒕컻", "?묒궛媛쒖떆"
]

EVENT_SYNONYMS = {
    "湲덈━ ?명븯": "湲덈━?명븯",
    "湲덈━ ?몄긽": "湲덈━?몄긽",
    "?섏쑉 ?곸듅": "?섏쑉?곸듅",
    "?섏쑉 ?섎씫": "?섏쑉?섎씫",
    "?좉? 湲됰벑": "?좉?湲됰벑",
    "?좉? ?섎씫": "?좉??섎씫",
    "?ㅼ쟻 媛쒖꽑": "?ㅼ쟻媛쒖꽑",
    "?ㅼ쟻 遺吏?: "?ㅼ쟻遺吏?,
    "?섏＜ ?뺣?": "?섏＜?뺣?",
    "怨듦툒留?遺덉븞": "怨듦툒留앸텋??,
    "怨듦툒留??ы렪": "怨듦툒留앹옱??,
    "?뺤콉 吏??: "?뺤콉吏??,
    "洹쒖젣 媛뺥솕": "洹쒖젣媛뺥솕",
    "?섏슂 利앷?": "?섏슂利앷?",
    "?섏슂 ?뷀솕": "?섏슂?뷀솕",
    "?묒궛 ?쒖옉": "?묒궛媛쒖떆",
    "?묒궛 媛쒖떆": "?묒궛媛쒖떆",
    "?몄“ 由ъ뒪??: "?몄“由ъ뒪??,
}

client = OpenAI()
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
news_analysis_index = chroma_client.get_or_create_collection(name="news_analysis_index")

# =========================================================
# ?좏떥
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
    return bool(re.search(r"[媛-??", text))


def is_meaningful_article(title: str, body: str, min_body_len: int = 60) -> bool:
    """
    ?덈Т 吏㏃? ?띾낫/?쒖꽭 湲곗궗 ?쒓굅??
    """
    title = normalize_text(title)
    body = normalize_text(body)

    if len(body) < min_body_len:
        return False

    noisy_patterns = [
        r"^\[?띾낫\]",
        r"留덇컧$",
        r"?μ쨷$",
        r"?ㅼ쟾??",
        r"?ㅽ썑??",
        r"醫낃?$",
    ]

    # ?쒕ぉ???덈Т 吏㏐퀬 body??吏㏃쑝硫??쒓굅
    if len(title) < 12 and len(body) < 80:
        return False

    for p in noisy_patterns:
        if re.search(p, title):
            # ?띾낫?쇰룄 body媛 異⑸텇??湲몃㈃ ?대┫ ???덉?留?
            # MVP?먯꽑 蹂댁닔?곸쑝濡??쒓굅
            return False

    return True

def normalize_title_for_dedup(title: str) -> str:
    title = normalize_text(title).lower()
    title = re.sub(r"[^媛-?즑-z0-9 ]", "", title)
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
    res = client.embeddings.create(
        model=OPENAI_EMBED_MODEL,
        input=text
    )
    return res.data[0].embedding


# =========================================================
# ?ㅽ궎留?
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
    print("??init-db ?꾨즺")


# =========================================================
# ?댁뒪 ?섏쭛
# =========================================================

def fetch_naver_news(query, days_back=90, max_items=300):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET ?섍꼍蹂?섍? ?꾩슂?⑸땲??")

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

                # ?쒓뎅??湲곗궗留??섏쭛
                if not is_korean_text(title):
                    continue

                # ?덈Т 吏㏃? 湲곗궗/?띾낫 ?쒓굅
                if not is_meaningful_article(title, desc, min_body_len=60):
                    continue

                news_id = md5_hash(link)  # 留곹겕 以묐났 ?쒓굅
                content_hash = build_content_hash(title, desc)  # ?댁슜 ?댁떆 以묐났 ?쒓굅
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
# 以묐났 ?쒓굅
# =========================================================

def find_duplicate_news(conn, news):
    """
    ?곗꽑?쒖쐞:
    1) 留곹겕 湲곕컲 以묐났: news_id
    2) ?댁슜 ?댁떆 湲곕컲 以묐났: content_hash
    3) ?쒕ぉ/?댁슜 ?좎궗??湲곕컲 ?쇰━ 以묐났
    """
    cur = conn.cursor(dictionary=True)

    # 1. 留곹겕 湲곕컲 以묐났 (news_id)
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

    # 2. content_hash 湲곕컲 以묐났
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
    
    # 2.5 dedup_key ?숈씪 湲곗궗 ?곗꽑 寃??
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

    # 3. ?쒕ぉ/?댁슜 ?좎궗??湲곕컲 ?쇰━ 以묐났
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

    print(f"  ??????꾨즺: 珥?{inserted_count}嫄?/ 以묐났 ?뚮옒洹?{duplicate_count}嫄?)
    return inserted_count


# =========================================================
# ?먯쑀 異붿텧 湲곕컲 ?댁뒪 遺꾩꽍
# =========================================================

def llm_analyze_news_freeform(title, body):
    prompt = f"""
?덈뒗 湲덉쑖 ?댁뒪 鍮꾩젙???곗씠??遺꾩꽍湲곕떎.
?꾨옒 ?댁뒪瑜??쎄퀬, ?ъ옄 遺꾩꽍???쒖슜?????덈룄濡?援ъ“?뷀븯??
?꾨낫 ?ъ쟾???섏〈?섏? 留먭퀬 ?댁뒪 ?댁슜??洹쇨굅???먯쑀濡?쾶 異붿텧?섎씪.
諛섎뱶??JSON留?異쒕젰?섎씪.

洹쒖튃:
1) mentioned_entities: ?щ엺, 湲곗뾽, 湲곌?, ?쒗뭹, 援?? ???듭떖 紐낆궗
2) companies: 湲곗뾽紐낅쭔
3) organizations: ?뺣?/湲곌?/?⑥껜/?몄“/?묓쉶/援?? 湲곌? ??
4) themes: ?ъ옄/?곗뾽 愿?먯쓽 ?뚮쭏
5) industries: ?곗뾽/?낆쥌
6) events: ?쒖옣/?곗뾽 ?대깽??
7) sentiment: positive / negative / neutral
8) importance_score: 0~1
   ?꾨옒 湲곗??쇰줈 ?됯??섎씪.
   - 0.9 ~ 1.0: ?쒖옣 ?꾨컲?????곹뼢??以????덈뒗 嫄곗떆/?뺤콉/吏?뺥븰 ?댁뒪
   - 0.7 ~ 0.89: ?뱀젙 ?곗뾽 ?꾨컲???곹뼢??二쇰뒗 ?낇솴/怨듦툒留??섏슂/洹쒖젣 蹂??
   - 0.5 ~ 0.69: 媛쒕퀎 湲곗뾽 ?먮뒗 ?쇰? ?곗뾽???섎? ?덈뒗 ?댁뒪
   - 0.3 ~ 0.49: ?쇰컲 ?뺣낫??湲곗궗, ?곹뼢 踰붿쐞媛 ?쒗븳?곸씤 ?댁뒪
   - 0.0 ~ 0.29: ?⑥닚 ?띾낫??諛섎났???섎?媛 ?쏀븳 湲곗궗
9) risk_points: 由ъ뒪???붿젏 由ъ뒪??
10) opportunity_points: 湲고쉶 ?붿젏 由ъ뒪??
11) article_summary: 2臾몄옣 ?대궡 ?붿빟
12) JSON ???띿뒪??湲덉?
13) importance_score??湲곗궗???쒖옣 ?곹뼢 踰붿쐞? ?곗뾽 ?뚭툒??湲곗??쇰줈 ?됯??섍퀬, ?⑥닚 湲곗궗 湲몄씠???먭레?곸씤 ?쒗쁽留뚯쑝濡??믨쾶 二쇱? 留?寃?

?댁뒪 ?쒕ぉ:
{title}

?댁뒪 ?댁슜:
{body}

異쒕젰 ?뺤떇:
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
        res = client.chat.completions.create(
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
# Chroma ?몃뜳??
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
            "importance_score": analysis["importance_score"]
        }]
    )


# =========================================================
# 諛곗튂
# =========================================================

def collect_news(days_back=90, queries=None):
    queries = queries or DEFAULT_QUERIES
    all_rows = []

    for query in queries:
        news_list = fetch_naver_news(query, days_back=days_back, max_items=300)
        save_news_raw(news_list)
        all_rows.extend(news_list)
        print(f"collected: {query} -> {len(news_list)}嫄?)
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
    print(f"pending analysis (non-duplicate only): {len(rows)}嫄?)

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
        print("??젣??90??珥덇낵 ?댁뒪 ?놁쓬")
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

    print(f"??90??珥덇낵 ?댁뒪 ??젣 ?꾨즺: {len(old_ids)}嫄?)


def daily_batch(days_back=90, retention_days=90):
    print("?? daily-batch ?쒖옉")
    collect_news(days_back=days_back)
    analyze_pending_news(limit=1000)
    prune_old_news(retention_days=retention_days)
    print("??daily-batch ?꾨즺")


# =========================================================
# 議고쉶??
# =========================================================

def search_news_context(query, n_results=5):

    query_emb = get_embedding(query)

    try:
        res = news_analysis_index.query(
            query_embeddings=[query_emb],
            n_results=n_results
        )

        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]

        return [{"doc": d, "meta": m} for d, m in zip(docs, metas)]

    except Exception as e:
        print("寃???ㅻ쪟:", e)
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

    else:
        print("""
?ъ슜 ?덉떆:
  python pipeline_news_analysis_mvp.py init-db
  python pipeline_news_analysis_mvp.py collect --days-back 90
  python pipeline_news_analysis_mvp.py analyze-pending --limit 300
  python pipeline_news_analysis_mvp.py prune --retention-days 90
  python pipeline_news_analysis_mvp.py daily-batch --days-back 90 --retention-days 90
""")


if __name__ == "__main__":
    main()
