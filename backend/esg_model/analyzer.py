"""
ESG RAG 분석기 코어
- MySQL esg_reports 테이블에서 보고서 원문 로드
- SBERT로 관련 청크 추출 (RAG)
- GPT-4o-mini로 리스크/기대요인 자연어 분석
- 결과를 DB에 캐시 → 재호출 시 GPT 비용 없이 즉시 반환
"""
import os
from datetime import datetime

import numpy as np
import pymysql
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer

load_dotenv()

# ── 싱글턴 ──────────────────────────────────────────────────────────────────
_embed_model = None
_openai_client = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    return _embed_model


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def _get_db_conn():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "192.168.101.70"),
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ.get("DB_USER", "developer_team"),
        password=os.environ.get("DB_PASSWORD", "0327"),
        database=os.environ.get("DB_NAME", "seedup_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


# ── 텍스트 처리 ──────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) <= chunk_size:
            current += para + "\n"
        else:
            if current:
                chunks.append(current.strip())
            current = (current[-overlap:] + para + "\n") if overlap and current else (para + "\n")
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _retrieve_top_chunks(query: str, chunks: list[str], top_k: int = 8) -> list[str]:
    if not chunks:
        return []
    model = _get_embed_model()
    q_emb = model.encode([query])[0]
    c_embs = model.encode(chunks)
    q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)
    c_norms = c_embs / (np.linalg.norm(c_embs, axis=1, keepdims=True) + 1e-9)
    scores = c_norms @ q_norm
    top_idx = np.argsort(scores)[::-1][:top_k]
    return [chunks[i] for i in sorted(top_idx)]


# ── GPT 프롬프트 ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "당신은 ESG(환경·사회·지배구조) 전문 애널리스트입니다. "
    "제공된 ESG 보고서 발췌 내용만을 근거로 답변하세요. "
    "보고서에 명시되지 않은 내용은 절대 추측하거나 언급하지 마세요. "
    "한국어로 간결하고 자연스럽게 답변하세요."
)

_RISK_OPP_PROMPT = (
    "이 기업의 ESG 보고서 내용을 바탕으로 아래 형식으로만 답변해줘.\n"
    "보고서에 직접 언급된 구체적인 내용(수치, 사업명, 규제명 등)을 포함해서 작성해.\n"
    "근거가 없는 항목은 해당 줄을 아예 생략해. 두 줄 외에 다른 문장은 절대 추가하지 마.\n\n"
    "리스크 요인: (탄소 규제, 공급망 문제, 사회적 갈등, 법적 리스크 등 보고서에서 확인된 구체적 리스크들을 나열한 자연스러운 한 문장. 없으면 이 줄 생략)\n"
    "기대 요인: (재생에너지 투자, 친환경 제품, 사회공헌 성과, 지배구조 개선 등 보고서에서 확인된 구체적 기회·성장 요인들을 나열한 자연스러운 한 문장. 없으면 이 줄 생략)"
)


# ── 핵심 공개 함수 ───────────────────────────────────────────────────────────

def analyze_by_stock_code(stock_code: str, force_refresh: bool = False) -> dict | None:
    """
    종목코드로 ESG 리스크/기대요인 분석.

    Args:
        stock_code:     종목코드 (예: "005930")
        force_refresh:  True면 캐시 무시하고 GPT 재분석

    Returns:
        {
            "stock_code":    "005930",
            "company_name":  "삼성전자",
            "published_at":  "2025-06-27",
            "risks":         "탄소배출권 비용 증가, 수자원 리스크...",   # 없으면 None
            "opportunities": "Net Zero 2050 이행, 고효율 설비 교체...", # 없으면 None
            "analyzed_at":   "2026-03-12T10:00:00",
            "cached":        True / False,
        }
        None → 보고서 없음 (언급 불필요)
    """
    # 1. DB에서 최신 보고서 조회
    with _get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, company_name, title, published_at, "
                "risks, opportunities, analyzed_at "
                "FROM esg_reports "
                "WHERE stock_code = %s ORDER BY published_at DESC LIMIT 1",
                (stock_code,),
            )
            row = cur.fetchone()

    if not row:
        return None  # 보고서 없음

    # 2. 캐시 히트
    if not force_refresh and row["analyzed_at"] and row["risks"] is not None:
        return {
            "stock_code":    stock_code,
            "company_name":  row["company_name"],
            "published_at":  str(row["published_at"] or "")[:10],
            "risks":         row["risks"],
            "opportunities": row["opportunities"],
            "analyzed_at":   str(row["analyzed_at"]),
            "cached":        True,
        }

    # 3. 보고서 원문 로드
    with _get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT full_text FROM esg_reports WHERE id = %s", (row["id"],))
            text_row = cur.fetchone()

    full_text = (text_row or {}).get("full_text") or ""
    if not full_text:
        return None

    # 4. RAG: 관련 청크 추출
    chunks = _chunk_text(full_text)
    context = "\n\n---\n\n".join(_retrieve_top_chunks(_RISK_OPP_PROMPT, chunks))

    # 5. GPT 호출
    user_msg = (
        f"[기업명] {row['company_name']}\n"
        f"[보고서] {row['title']} ({str(row['published_at'] or '')[:10]})\n\n"
        f"[발췌]\n{context}\n\n"
        f"[지시]\n{_RISK_OPP_PROMPT}"
    )
    resp = _get_openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=400,
    )
    answer = resp.choices[0].message.content.strip()

    # 6. 파싱
    risks, opportunities = None, None
    for line in answer.splitlines():
        line = line.strip()
        if line.startswith("리스크 요인:"):
            v = line[len("리스크 요인:"):].strip()
            risks = v or None
        elif line.startswith("기대 요인:"):
            v = line[len("기대 요인:"):].strip()
            opportunities = v or None

    # 7. 캐시 저장
    now = datetime.now()
    with _get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE esg_reports "
                "SET risks=%s, opportunities=%s, analyzed_at=%s "
                "WHERE id=%s",
                (risks, opportunities, now, row["id"]),
            )
        conn.commit()

    return {
        "stock_code":    stock_code,
        "company_name":  row["company_name"],
        "published_at":  str(row["published_at"] or "")[:10],
        "risks":         risks,
        "opportunities": opportunities,
        "analyzed_at":   now.isoformat(),
        "cached":        False,
    }
