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


def _normalize_codes(codes_raw: str) -> list[str]:
    """codes 쿼리 문자열을 6자리 종목코드 리스트로 정규화한다."""
    if not codes_raw:
        return []
    seen = set()
    normalized: list[str] = []
    for token in str(codes_raw).split(","):
        code = token.strip()
        if not code:
            continue
        if code.isdigit():
            code = code.zfill(6)
        if len(code) != 6 or not code.isdigit():
            continue
        if code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    return normalized


async def _price_event_generator(codes: list[str]) -> AsyncGenerator[str, None]:
    """push 방식 SSE — KIS WS 수신 즉시 해당 클라이언트에만 전달.

    연결 시: codes 구독 + 큐 등록
    연결 해제 시: 큐 제거 + 구독자 없는 종목 WS 구독 취소
    """
    from kis_ws_client import register_queue, unregister_queue, subscribe_codes, unsubscribe_codes

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    # 큐 등록 & KIS WS 구독 (필요 시)
    register_queue(codes, queue)
    await subscribe_codes(codes)

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=20.0)
                code = item["code"]
                data = item["data"]
                payload = {
                    code: {
                        "current_price": data["current_price"],
                        "change":        data["change"],
                        "change_rate":   data["change_rate"],
                        "volume":        data["volume"],
                    }
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    except asyncio.CancelledError:
        logger.debug("SSE 클라이언트 연결 종료")
    finally:
        # 큐 제거 & 구독자 없어진 종목 WS 구독 해제
        empty_codes = unregister_queue(codes, queue)
        if empty_codes:
            asyncio.get_running_loop().create_task(unsubscribe_codes(empty_codes))


@router.get("/ws-status")
async def ws_status():
    """KIS WebSocket 연결 상태 확인용 디버그 엔드포인트."""
    from kis_ws_client import get_manager, get_price_store
    manager = get_manager()
    store = get_price_store()
    if manager is None:
        return {"initialized": False, "price_store_count": len(store)}

    # KisWebSocketPool vs KiwoomWebSocketManager 공통 처리
    if hasattr(manager, "_workers"):
        # KisWebSocketPool
        workers_info = [
            {
                "running": w._running,
                "subscribed_count": len(w._subscribed),
                "subscribed_sample": sorted(w._subscribed)[:10],
            }
            for w in manager._workers
        ]
        return {
            "initialized": True,
            "type": "pool",
            "worker_count": manager.worker_count,
            "total_subscribed": manager.total_subscribed,
            "workers": workers_info,
            "price_store_count": len(store),
            "price_store_sample": {k: v for k, v in list(store.items())[:5]},
        }
    else:
        # KisWebSocketManager (단일)
        return {
            "initialized": True,
            "type": "single",
            "running": manager._running,
            "subscribed_count": len(manager._subscribed),
            "subscribed_sample": sorted(manager._subscribed)[:10],
            "pending": sorted(getattr(manager, "_pending_subscribe", set()))[:10],
            "price_store_count": len(store),
            "price_store_sample": {k: v for k, v in list(store.items())[:5]},
        }


@router.get("/prices")
async def stream_prices(codes: str = ""):
    """실시간 주가 SSE 스트림.

    Query params:
        codes: 콤마 구분 종목코드 (예: 005930,000660,035720)
    """
    code_list = _normalize_codes(codes)
    if not code_list:
        # 코드 없으면 빈 메시지 후 즉시 종료
        async def empty():
            yield ": no codes\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    logger.info("SSE /prices 연결: %d개 종목 구독 요청", len(code_list))

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # Nginx proxy 버퍼 비활성
    }
    return StreamingResponse(
        _price_event_generator(code_list),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/test-inject")
async def test_inject_prices(codes: str = ""):
    """장 마감 시 테스트용 — _price_store에 1초마다 랜덤 변동 주가를 주입.

    브라우저에서 /api/stream/prices?codes=... 를 열어둔 상태에서
    /api/stream/test-inject?codes=005930,000660 을 호출하면
    10초간 0.5~1% 범위의 랜덤 가격 변동을 시뮬레이션한다.
    """
    import random
    from kis_ws_client import get_price_store, get_manager
    from kis_client import get_current_price

    code_list = _normalize_codes(codes)
    if not code_list:
        return {"error": "codes 파라미터 필요 (예: ?codes=005930,000660)"}

    store = get_price_store()

    # 현재가 기준 초기값 로드 (store에 없으면 KIS REST API로 가져옴)
    for code in code_list:
        if code not in store:
            try:
                info = get_current_price(code)
                store[code] = {
                    "stock_code":    code,
                    "current_price": int(info["current_price"]),
                    "change":        info["change"],
                    "change_rate":   info["change_rate"],
                    "volume":        info.get("volume", 0),
                }
            except Exception:
                store[code] = {
                    "stock_code": code, "current_price": 50000,
                    "change": 0.0, "change_rate": 0.0, "volume": 0,
                }

    # 10회 × 1초 = 10초간 변동 주입
    injected = []
    for _ in range(10):
        await asyncio.sleep(1)
        for code in code_list:
            base = store[code]["current_price"]
            delta_rate = random.uniform(-0.005, 0.005)   # ±0.5%
            new_price  = max(1, round(base * (1 + delta_rate) / 100) * 100)
            change     = new_price - base
            store[code] = {
                "stock_code":    code,
                "current_price": new_price,
                "change":        float(change),
                "change_rate":   round(change / base * 100, 2),
                "volume":        store[code].get("volume", 0) + random.randint(100, 5000),
            }
        injected.append({c: store[c]["current_price"] for c in code_list})

    return {"message": f"{len(code_list)}개 종목 10초 시뮬레이션 완료", "history": injected}
