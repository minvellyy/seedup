"""FastAPI 라우터 — LLM 전문용어 자동 추출 엔드포인트.

POST /api/v1/terms/extract
    Body : { "text": "<AI 분석 텍스트>" }
    Response: { "terms": { "용어": "설명", ... } }

페이지 로딩 시 프론트엔드가 호출. GPT-4o-mini 가 분석 텍스트를 읽고
일반 투자자가 이해하기 어려운 전문 용어를 최대 8개 추출해 쉬운 설명과 함께 반환합니다.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from fastapi import APIRouter
from pydantic import BaseModel

load_dotenv()

router = APIRouter()


class TermExtractRequest(BaseModel):
    text: str


@router.post("/terms/extract")
async def extract_terms(req: TermExtractRequest):
    """분석 텍스트에서 전문 용어를 LLM으로 자동 추출합니다."""
    text = req.text.strip()
    if len(text) < 20:
        return {"terms": {}}

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"terms": {}}

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)

        prompt = (
            "다음 금융·투자 분석 텍스트에서 일반 투자자가 이해하기 어려운 전문 용어를 추출하고, "
            "각 용어에 대해 1-2문장의 쉬운 한국어 설명을 작성해주세요.\n\n"
            "규칙:\n"
            "- 텍스트에 실제로 등장하는 단어·약어만 선택\n"
            "- 일반 단어·회사명·국가명·사람 이름은 제외\n"
            "- 산업·금융·기술 전문 약어(영문/한글) 또는 어려운 개념어를 우선 선택\n"
            "- 최대 8개 추출\n"
            '- 반드시 JSON 형식으로만 응답: {"용어": "설명", ...}\n\n'
            f"텍스트:\n{text[:3000]}"
        )

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=800,
        )

        raw = response.choices[0].message.content
        terms: dict = json.loads(raw)
        # 안전 필터: 키·값 모두 문자열이고 키 길이가 너무 길지 않은 것만 허용
        terms = {
            k: v
            for k, v in terms.items()
            if isinstance(k, str) and isinstance(v, str) and len(k) <= 20
        }
        return {"terms": terms}

    except Exception as e:
        print(f"[terms/extract] 오류: {e}")
        return {"terms": {}}
