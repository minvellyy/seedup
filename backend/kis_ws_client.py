"""KIS 실시간 WebSocket 관리자.

KIS WebSocket으로 실시간 주식 체결가를 수신해 _price_store(메모리)에 저장한다.
FastAPI startup_event에서 init_manager()를 호출해 백그라운드 태스크로 기동.
SSE 엔드포인트(/api/stream/prices)에서 get_price_store()로 최신가 참조.

TR_ID: H0STCNT0 (주식현재가 실시간 체결)
수신 형식: "0|H0STCNT0|NNN|CODE^HH:MM:SS^현재가^부호^전일대비^등락률^..."
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Set

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

logger = logging.getLogger("kis_ws")

# ── 환경 변수 ─────────────────────────────────────────────────────────────────
_APPKEY    = os.getenv("APP_KEY", "").strip()
_SECRETKEY = os.getenv("APP_SECRET", "").strip()
_IS_MOCK   = os.getenv("KIS_MOCK", "false").lower() == "true"

# WebSocket URL
_WS_URL_REAL = "ws://ops.koreainvestment.com:21000"
_WS_URL_MOCK = "ws://ops.koreainvestment.com:31000"

# approval_key 캐시 파일
_APPROVAL_FILE = Path(__file__).parent / ".kis_approval_cache"

# ── 전역 상태 ──────────────────────────────────────────────────────────────────
_price_store: Dict[str, Dict] = {}   # { "005930": {"current_price": 75000, ...} }
_manager: Optional["KisWebSocketManager"] = None


# ── approval_key 발급 ─────────────────────────────────────────────────────────

def _load_approval_from_file() -> Optional[str]:
    """파일에서 approval_key 로드. 유효(1일)하면 반환, 만료면 None."""
    try:
        if not _APPROVAL_FILE.exists():
            return None
        data = json.loads(_APPROVAL_FILE.read_text(encoding="utf-8"))
        if float(data.get("expires_at", 0)) > time.time() + 60:
            return data["approval_key"]
    except Exception:
        pass
    return None


def _save_approval_to_file(key: str) -> None:
    try:
        payload = {
            "approval_key": key,
            "expires_at": time.time() + 86400,  # 1일
        }
        _APPROVAL_FILE.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def get_approval_key() -> str:
    """WebSocket 접속용 approval_key 발급(파일캐시 1일)."""
    cached = _load_approval_from_file()
    if cached:
        return cached

    url = "https://openapi.koreainvestment.com:9443/oauth2/Approval"
    body = {
        "grant_type": "client_credentials",
        "appkey": _APPKEY,
        "secretkey": _SECRETKEY,   # appsecret 아님!
    }
    resp = requests.post(url, json=body, timeout=10)
    resp.raise_for_status()
    key = resp.json()["approval_key"]
    _save_approval_to_file(key)
    logger.info("KIS approval_key 발급 완료")
    return key


# ── 구독 메시지 생성 ───────────────────────────────────────────────────────────

# 구독할 실시간 TR_ID 목록 (KRX 정규장 + NXT)
_REALTIME_TR_IDS = ["H0STCNT0", "H0NXCNT0"]


def _build_subscribe_msg(approval_key: str, stock_code: str, tr_id: str = "H0STCNT0", tr_type: str = "1") -> str:
    """tr_type '1'=구독, '2'=해제."""
    return json.dumps({
        "header": {
            "approval_key": approval_key,
            "custtype": "P",
            "tr_type": tr_type,
            "content-type": "utf-8",
        },
        "body": {
            "input": {
                "tr_id": tr_id,
                "tr_key": stock_code,
            }
        },
    })


# ── 데이터 파싱 ────────────────────────────────────────────────────────────────

def _parse_realtime(msg: str) -> Optional[Dict]:
    """H0STCNT0(KRX) / H0NXCNT0(NXT) 실시간 체결 메시지를 파싱해 dict 반환.

    수신 형식: "0|<TR_ID>|NNN|<data>"
    data 필드(^ 구분):
        [0] MKSC_SHRN_ISCD 종목코드
        [2] STCK_PRPR      현재가
        [3] PRDY_VRSS_SIGN 부호 (1=상한,2=상승,3=보합,4=하한,5=하락)
        [4] PRDY_VRSS      전일대비
        [5] PRDY_CTRT      등락률
        [13] ACML_VOL      누적거래량
    """
    try:
        parts = msg.split("|")
        if len(parts) < 4:
            return None
        # KRX 정규장(H0STCNT0) 또는 NXT(H0NXCNT0) 체결 메시지만 처리
        if parts[0] in ("0", "1") and parts[1] in _REALTIME_TR_IDS:
            data = parts[3].split("^")
            if len(data) < 14:
                return None
            code      = data[0]
            price     = int(data[2]) if data[2].isdigit() else 0
            sign      = data[3]   # '1'상한 '2'상승 '3'보합 '4'하한 '5'하락
            is_minus  = sign in ("4", "5")
            try:
                chg  = float(data[4]) * (-1 if is_minus else 1)
                rate = float(data[5]) * (-1 if is_minus else 1)
            except ValueError:
                chg = rate = 0.0
            try:
                vol = int(data[13])
            except ValueError:
                vol = 0

            return {
                "stock_code":   code,
                "current_price": price,
                "change":        chg,
                "change_rate":   rate,
                "volume":        vol,
            }
    except Exception as e:
        logger.debug("파싱 오류: %s", e)
    return None


# ── KisWebSocketManager ────────────────────────────────────────────────────────

class KisWebSocketManager:
    """KIS WebSocket 연결을 유지하며 실시간 체결가를 _price_store에 저장한다."""

    def __init__(self, is_mock: bool = False):
        self._ws_url        = _WS_URL_MOCK if is_mock else _WS_URL_REAL
        self._approval_key: Optional[str] = None
        self._subscribed:   Set[str]      = set()
        self._running       = False
        self._task: Optional[asyncio.Task] = None
        self._invalid_key   = False

    # ── 공개 API ──────────────────────────────────────────────────────────────

    async def start(self, initial_codes: list[str]) -> None:
        """백그라운드 루프 시작."""
        self._running = True
        # approval_key 초기 발급은 _run_loop 내에서 처리 (재연결 시도마다 갱신)
        self._task = asyncio.create_task(self._run_loop(initial_codes))
        logger.info("KIS WebSocket 백그라운드 태스크 시작")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def subscribe(self, codes: list[str]) -> None:
        """아직 구독 안 된 종목코드 추가 구독 요청 (큐로 전달)."""
        # _subscribed는 이제 "{code}:{tr_id}" 형식 → 하나라도 미완이면 pending에 추가
        new_codes = [
            c for c in codes
            if any(f"{c}:{tr_id}" not in self._subscribed for tr_id in _REALTIME_TR_IDS)
        ]
        if new_codes:
            self._pending_subscribe = getattr(self, "_pending_subscribe", set())
            self._pending_subscribe.update(new_codes)

    # ── 내부 루프 ─────────────────────────────────────────────────────────────

    async def _run_loop(self, initial_codes: list[str]) -> None:
        """연결 끊기면 지수 백오프 후 자동 재연결.

        구독할 종목이 없으면 연결을 시도하지 않고 대기한다.
        실패 시 대기: 5 → 10 → 20 → 40 → 60초(최대) 반복.
        """
        import websockets  # lazy import

        self._pending_subscribe: Set[str] = set(initial_codes)
        self._invalid_key = False  # OPSP0011 수신 시 True
        backoff = 5  # 초기 대기 시간(초)

        while self._running:
            # ── 구독 종목이 없으면 연결하지 않고 대기 ─────────────────────────
            if not self._pending_subscribe and not self._subscribed:
                await asyncio.sleep(5)
                continue

            try:
                # 재연결마다 approval_key 갱신 (캐시 유효하면 재사용, 만료시 재발급)
                if self._invalid_key:
                    if _APPROVAL_FILE.exists():
                        _APPROVAL_FILE.unlink()
                    self._invalid_key = False
                    logger.info("approval_key 캐시 초기화 후 재발급")
                try:
                    self._approval_key = get_approval_key()
                except Exception as key_err:
                    logger.warning("approval_key 발급 실패: %s — 30초 후 재시도", key_err)
                    await asyncio.sleep(30)
                    continue

                logger.info("KIS WS 연결 시도: %s", self._ws_url)
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=None,   # KIS는 텍스트 기반 PINGPONG 사용 → 내장 ping 비활성화
                    close_timeout=10,
                ) as ws:
                    logger.info("KIS WS 연결 성공")
                    self._subscribed.clear()
                    self._ws = ws
                    backoff = 5  # 연결 성공 시 백오프 초기화

                    recv_task   = asyncio.create_task(self._recv_loop(ws))
                    sender_task = asyncio.create_task(self._sender_loop(ws))
                    try:
                        await asyncio.gather(recv_task, sender_task)
                    except Exception:
                        recv_task.cancel()
                        sender_task.cancel()
                        raise

            except Exception as e:
                err_msg = str(e)
                # "no close frame" 는 KIS가 TCP를 조용히 끊은 것 — DEBUG로 낮춤
                if "no close frame" in err_msg:
                    logger.debug("KIS WS 연결 종료 (no close frame) — %d초 후 재연결", backoff)
                else:
                    logger.warning("KIS WS 연결 오류: %s — %d초 후 재연결", e, backoff)
                if not self._running:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)  # 최대 60초

    async def _recv_loop(self, ws) -> None:
        """수신 전용 루프."""
        async for raw in ws:
            if not self._running:
                break

            if raw == "PINGPONG":
                await ws.send("PINGPONG")
                continue

            if raw.startswith("{"):
                try:
                    sys_msg = json.loads(raw)
                    msg_cd  = sys_msg.get("body", {}).get("msg_cd", "")
                    rt_cd   = sys_msg.get("body", {}).get("rt_cd", "")
                    if msg_cd == "OPSP0011" or (rt_cd == "1" and "invalid" in sys_msg.get("body", {}).get("msg1", "").lower()):
                        logger.warning("approval_key 만료 감지 (OPSP0011) — 재연결 시 키 재발급 예약")
                        self._invalid_key = True
                        raise ConnectionError("invalid approval_key")
                    logger.debug("시스템 메시지: %s", sys_msg)
                except (ConnectionError, asyncio.CancelledError):
                    raise
                except Exception:
                    pass
                continue

            parsed = _parse_realtime(raw)
            if parsed:
                code = parsed["stock_code"]
                _price_store[code] = parsed
                logger.debug("수신 %s: %s", code, parsed["current_price"])

    async def _sender_loop(self, ws) -> None:
        """0.5초마다 pending 구독 요청을 WS로 전송, 30초마다 PINGPONG 하트비트 전송."""
        last_ping = asyncio.get_event_loop().time()
        while self._running:
            await self._flush_pending(ws)
            now = asyncio.get_event_loop().time()
            if now - last_ping >= 30:
                try:
                    await ws.send("PINGPONG")
                    last_ping = now
                    logger.debug("KIS WS PINGPONG 전송")
                except Exception:
                    break  # WS 연결 끊김 → _run_loop에서 재연결
            await asyncio.sleep(0.5)

    async def _flush_pending(self, ws) -> None:
        pending: Set[str] = getattr(self, "_pending_subscribe", set())
        for code in list(pending):
            # KRX + NXT 두 TR_ID 모두 구독 (이미 완료된 것은 skip)
            all_done = True
            for tr_id in _REALTIME_TR_IDS:
                sub_key = f"{code}:{tr_id}"
                if sub_key not in self._subscribed:
                    try:
                        msg = _build_subscribe_msg(self._approval_key, code, tr_id=tr_id)
                        await ws.send(msg)
                        self._subscribed.add(sub_key)
                        logger.info("KIS WS 구독: %s [%s]", code, tr_id)
                    except Exception as e:
                        logger.warning("구독 전송 실패 %s [%s]: %s", code, tr_id, e)
                        return  # WS 연결 문제 → _run_loop에서 재연결
                    all_done = False
            if all_done:
                pending.discard(code)
        if not pending:
            pending.clear()


# ── 전역 접근자 ───────────────────────────────────────────────────────────────

async def init_manager(initial_codes: list[str], is_mock: bool = False) -> None:
    """FastAPI startup_event에서 1회 호출."""
    global _manager
    _manager = KisWebSocketManager(is_mock=is_mock)
    await _manager.start(initial_codes)


def get_manager() -> Optional[KisWebSocketManager]:
    return _manager


def get_price_store() -> Dict[str, Dict]:
    """SSE 엔드포인트 등에서 최신 체결가 참조용."""
    return _price_store
