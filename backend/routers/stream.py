"""SSE(Server-Sent Events) 실시간 주가 스트리밍 엔드포인트.

GET /api/stream/prices?codes=005930,000660,...
- KIS WebSocket _price_store에서 0.5초 간격으로 변동분을 SSE로 전송
- 연결 시 해당 종목코드들을 KIS WS에 구독 등록
- keepalive: 20초마다 ": keepalive" 코멘트 전송
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger("stream")

router = APIRouter(prefix="/api/stream", tags=["stream"])


async def _price_event_generator(codes: list[str]) -> AsyncGenerator[str, None]:
    """변동된 종목 가격을 SSE 이벤트로 yield."""
    # 지연 import (순환 참조 방지)
    from kis_ws_client import get_manager, get_price_store

    # 요청된 코드들을 WS 관리자에 구독 등록
    manager = get_manager()
    if manager:
        await manager.subscribe(codes)

    price_store = get_price_store()
    last_sent: dict[str, dict] = {}   # 직전 전송 스냅샷
    keepalive_counter = 0

    try:
        while True:
            await asyncio.sleep(0.5)
            keepalive_counter += 1

            # 변동된 종목만 추려서 전송
            updates: dict[str, dict] = {}
            for code in codes:
                entry = price_store.get(code)
                if entry is None:
                    continue
                prev = last_sent.get(code)
                if prev is None or prev["current_price"] != entry["current_price"]:
                    updates[code] = {
                        "current_price": entry["current_price"],
                        "change":        entry["change"],
                        "change_rate":   entry["change_rate"],
                        "volume":        entry["volume"],
                    }
                    last_sent[code] = entry.copy()

            if updates:
                yield f"data: {json.dumps(updates, ensure_ascii=False)}\n\n"

            # 20초(40턴) 마다 keepalive 코멘트
            if keepalive_counter >= 40:
                keepalive_counter = 0
                yield ": keepalive\n\n"

    except asyncio.CancelledError:
        logger.debug("SSE 클라이언트 연결 종료")


@router.get("/prices")
async def stream_prices(codes: str = ""):
    """실시간 주가 SSE 스트림.

    Query params:
        codes: 콤마 구분 종목코드 (예: 005930,000660,035720)
    """
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        # 코드 없으면 빈 메시지 후 즉시 종료
        async def empty():
            yield ": no codes\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # Nginx proxy 버퍼 비활성
    }
    return StreamingResponse(
        _price_event_generator(code_list),
        media_type="text/event-stream",
        headers=headers,
    )
