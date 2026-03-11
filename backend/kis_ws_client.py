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

# KIS WebSocket 1연결당 최대 구독 종목 수 (기본 40, 계정 등급에 따라 조정)
_MAX_SUBSCRIPTIONS = int(os.getenv("KIS_MAX_SUBSCRIPTIONS", "40"))

# WebSocket URL
_WS_URL_REAL = "ws://ops.koreainvestment.com:21000"
_WS_URL_MOCK = "ws://ops.koreainvestment.com:31000"

# approval_key 캐시 파일
_APPROVAL_FILE = Path(__file__).parent / ".kis_approval_cache"
_approval_lock = __import__("threading").Lock()  # 다중 Worker 동시 재발급 방지

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


def get_approval_key(force_refresh: bool = False) -> str:
    """WebSocket 접속용 approval_key 발급(파일캐시 1일).

    force_refresh=True 이면 캐시를 무시하고 새로 발급 (OPSP0011 감지 시 사용).
    Lock으로 다중 Worker 동시 재발급을 방지한다.
    """
    # Lock 없이 빠른 읽기 (force_refresh 아닌 경우)
    if not force_refresh:
        cached = _load_approval_from_file()
        if cached:
            return cached

    with _approval_lock:
        # lock 획득 후 재확인 — 다른 Worker가 이미 갱신했을 수 있음
        if not force_refresh:
            cached = _load_approval_from_file()
            if cached:
                return cached
        else:
            # 강제 갱신: 캐시 파일 삭제
            if _APPROVAL_FILE.exists():
                try:
                    _APPROVAL_FILE.unlink()
                except Exception:
                    pass

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

# 구독할 실시간 TR_ID 목록
# H0NXCNT0(넥스트레이드 NXT)는 별도 권한 필요 + 미운영 시간대에 연결 강제 종료됨 → 제외
_REALTIME_TR_IDS = ["H0STCNT0"]


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
                need_force = self._invalid_key
                if need_force:
                    self._invalid_key = False
                    logger.info("approval_key 만료 감지 — 강제 재발급 요청")
                try:
                    self._approval_key = get_approval_key(force_refresh=need_force)
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
                    # 재연결 시: 기존 구독 목록을 pending에 복원한 뒤 subscribed 초기화
                    # (flush_pending이 pending을 비워버리므로, subscribed에서 복원해야 재구독됨)
                    prev_codes = {s.split(":")[0] for s in self._subscribed}
                    self._subscribed.clear()
                    self._limit_reached = False  # 재연결 시 한도 플래그 초기화
                    if prev_codes:
                        self._pending_subscribe = getattr(self, "_pending_subscribe", set())
                        self._pending_subscribe.update(prev_codes)
                        logger.info("재연결 — %d개 종목 재구독 예약", len(prev_codes))
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
                # OPSP0011(approval_key 만료)은 키 재발급 후 즉시 재연결
                if "invalid approval_key" in err_msg:
                    backoff = 3
                # "no close frame" 는 KIS가 TCP를 조용히 끊은 것 — DEBUG로 낮춤
                elif "no close frame" in err_msg:
                    logger.debug("KIS WS 연결 종료 (no close frame) — %d초 후 재연결", backoff)
                elif "did not receive a valid HTTP response" in err_msg:
                    logger.debug("KIS WS 연결 실패 (HTTP 응답 없음) — %d초 후 재연결", backoff)
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
                    body    = sys_msg.get("body", {})
                    msg_cd  = body.get("msg_cd", "")
                    rt_cd   = body.get("rt_cd", "")
                    msg1    = body.get("msg1", "")

                    # OPSP0011 만 approval_key 만료로 처리
                    if msg_cd == "OPSP0011":
                        logger.debug("approval_key 만료 감지 (OPSP0011) — 재연결 시 키 재발급 예약")
                        self._invalid_key = True
                        raise ConnectionError("invalid approval_key")

                    # OPSP0008: 구독 한도 초과 — 플래그 세우고 더 이상 구독 시도 안 함
                    if msg_cd == "OPSP0008":
                        logger.info(
                            "KIS WS 구독 한도 초과 (OPSP0008) — 현재 %d개 구독 중 (최대 %d). "
                            "추가 구독 중단. KIS_MAX_SUBSCRIPTIONS 환경변수로 한도를 줄이세요.",
                            len(self._subscribed) // len(_REALTIME_TR_IDS),
                            _MAX_SUBSCRIPTIONS,
                        )
                        self._limit_reached = True
                    elif rt_cd == "1":
                        logger.warning("KIS WS 구독 오류 응답 [%s]: %s", msg_cd, msg1)
                    else:
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
            # 구독 한도 초과 시 남은 pending을 모두 버림
            if getattr(self, "_limit_reached", False):
                pending.clear()
                return
            # 한도 체크: 구독 전 현재 구독 수 확인
            current_count = len(self._subscribed) // max(len(_REALTIME_TR_IDS), 1)
            if current_count >= _MAX_SUBSCRIPTIONS:
                logger.info(
                    "KIS WS 구독 한도 도달 (%d/%d) — 나머지 %d개 종목 구독 생략",
                    current_count, _MAX_SUBSCRIPTIONS, len(pending),
                )
                pending.clear()
                return
            all_done = True
            for tr_id in _REALTIME_TR_IDS:
                sub_key = f"{code}:{tr_id}"
                if sub_key not in self._subscribed:
                    try:
                        msg = _build_subscribe_msg(self._approval_key, code, tr_id=tr_id)
                        await ws.send(msg)
                        self._subscribed.add(sub_key)
                        logger.info("KIS WS 구독: %s [%s]", code, tr_id)
                        await asyncio.sleep(0.05)  # 종목 간 전송 간격 (과부하 방지)
                    except Exception as e:
                        logger.warning("구독 전송 실패 %s [%s]: %s — 해당 종목 구독 건너뜀", code, tr_id, e)
                        # 실패한 sub_key를 subscribed에 추가해 무한 재시도 방지
                        self._subscribed.add(sub_key)
                        all_done = False
                        # WS 연결 자체가 끊긴 경우 즉시 중단
                        if "close frame" in str(e) or "connection" in str(e).lower():
                            return
                    else:
                        all_done = False  # 방금 구독 완료 → pending에서 제거 대기
            if all_done:
                pending.discard(code)
        if not pending:
            pending.clear()


# ── KisWebSocketPool (다중 연결 풀) ──────────────────────────────────────────

class KisWebSocketPool:
    """KisWebSocketManager를 여러 개 생성해 40개 한도를 초과하는 종목을 커버한다.

    초기 종목 목록을 _MAX_SUBSCRIPTIONS 단위로 분할해 각 연결에 분배하고,
    이후 subscribe() 호출 시 여유 있는 연결에 추가하거나 새 연결을 생성한다.
    모든 연결은 공유 _price_store에 체결가를 저장한다.
    """

    def __init__(self, is_mock: bool = False):
        self._is_mock = is_mock
        self._workers: list[KisWebSocketManager] = []

    async def start(self, initial_codes: list[str]) -> None:
        if not initial_codes:
            logger.info("KIS WebSocket Pool: 초기 종목 없음 — subscribe() 호출 시 연결 생성")
            return
        chunks = [
            initial_codes[i: i + _MAX_SUBSCRIPTIONS]
            for i in range(0, len(initial_codes), _MAX_SUBSCRIPTIONS)
        ]
        for chunk in chunks:
            w = KisWebSocketManager(is_mock=self._is_mock)
            self._workers.append(w)
            await w.start(chunk)
        logger.info(
            "KIS WebSocket Pool 시작: %d개 연결, 총 %d개 종목 구독",
            len(self._workers), len(initial_codes),
        )

    async def stop(self) -> None:
        for w in self._workers:
            await w.stop()
        self._workers.clear()

    async def subscribe(self, codes: list[str]) -> None:
        """요청된 코드들을 여유 연결에 분배, 모자라면 새 연결 생성."""
        remaining = list(codes)

        # 기존 workers에 여유 용량 채우기
        for w in self._workers:
            if not remaining:
                break
            current = len(w._subscribed) // max(len(_REALTIME_TR_IDS), 1)
            capacity = _MAX_SUBSCRIPTIONS - current
            if capacity > 0:
                to_sub = remaining[:capacity]
                remaining = remaining[capacity:]
                await w.subscribe(to_sub)

        # 남은 종목은 새 연결 생성
        while remaining:
            chunk = remaining[:_MAX_SUBSCRIPTIONS]
            remaining = remaining[_MAX_SUBSCRIPTIONS:]
            w = KisWebSocketManager(is_mock=self._is_mock)
            self._workers.append(w)
            await w.start(chunk)
            logger.info(
                "KIS WebSocket Pool: 새 연결 추가 (총 %d개 연결)",
                len(self._workers),
            )

    @property
    def worker_count(self) -> int:
        return len(self._workers)

    @property
    def total_subscribed(self) -> int:
        return sum(
            len(w._subscribed) // max(len(_REALTIME_TR_IDS), 1)
            for w in self._workers
        )


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
