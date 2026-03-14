"""한국투자증권(KIS) 실시간 WebSocket 관리자.

WebSocket URL (실거래): ws://ops.koreainvestment.com:21000
WebSocket URL (모의투자): ws://openskh.koreainvestment.com:31000
인증: approval_key (POST /oauth2/Approval로 발급, access_token과 별도)
구독 TR: H0STCNT0 (주식체결 실시간)
구독 메시지:
  {"header": {"approval_key": "...", "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
   "body":   {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}}}
응답 형식: 0|H0STCNT0|001|종목코드^체결시간^현재가^전일대비부호^전일대비^등락율^...^누적거래량^...
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import threading
from pathlib import Path
from typing import Dict, Optional, Set

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

logger = logging.getLogger("kis_ws")

# ── 환경 변수 ─────────────────────────────────────────────────────────────────
# KIS WebSocket 1연결당 최대 구독 종목 수 (필요 시 .env에서 조정)
_MAX_SUBSCRIPTIONS = int(os.getenv("KIS_MAX_SUBSCRIPTIONS", "40"))

# KIS WebSocket URL (실거래 / 모의투자)
IS_MOCK = os.getenv("KIS_MOCK", "false").lower() == "true"
if IS_MOCK:
    _BASE_URL = "https://openapivts.koreainvestment.com:29443"
    _WS_URL   = "ws://openskh.koreainvestment.com:31000"
else:
    _BASE_URL = "https://openapi.koreainvestment.com:9443"
    _WS_URL   = "ws://ops.koreainvestment.com:21000"

# ── 전역 상태 ──────────────────────────────────────────────────────────────────
_price_store: Dict[str, Dict] = {}   # { "005930": {"current_price": 75000, ...} }
_manager: Optional["KisWebSocketManager"] = None
_ws_available: bool = True           # False = WS 포기, REST 폴링 사용 중
_ws_connect_lock: Optional[asyncio.Lock] = None  # 워커 간 동시 로그인 방지


def _get_connect_lock() -> asyncio.Lock:
    """모든 워커가 공유하는 연결 직렬화 Lock."""
    global _ws_connect_lock
    if _ws_connect_lock is None:
        _ws_connect_lock = asyncio.Lock()
    return _ws_connect_lock


# ── Approval Key ──────────────────────────────────────────────────────────────
# KIS WebSocket 전용 인증키 (access_token과 별도로 발급)
_approval_key_cache: Dict = {"key": None, "expires_at": 0.0}
_approval_key_lock = threading.Lock()


def _get_approval_key(force_refresh: bool = False) -> str:
    """KIS WebSocket approval_key 발급 (24시간 유효)."""
    now = time.time()
    if not force_refresh and _approval_key_cache["key"] and _approval_key_cache["expires_at"] > now + 60:
        return _approval_key_cache["key"]

    with _approval_key_lock:
        now = time.time()
        if not force_refresh and _approval_key_cache["key"] and _approval_key_cache["expires_at"] > now + 60:
            return _approval_key_cache["key"]

        resp = requests.post(
            f"{_BASE_URL}/oauth2/Approval",
            json={
                "grant_type": "client_credentials",
                "appkey":     os.getenv("APP_KEY", "").strip(),
                "secretkey":  os.getenv("APP_SECRET", "").strip(),
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        key = data.get("approval_key", "")
        if not key:
            raise ValueError(f"approval_key 발급 실패: {data}")
        _approval_key_cache["key"] = key
        _approval_key_cache["expires_at"] = now + 86400  # 24시간
        logger.info("KIS WebSocket approval_key 발급 완료")
        return key


# ── 구독/해제 메시지 생성 ─────────────────────────────────────────────────────

def _build_subscribe_msg(approval_key: str, stock_code: str, tr_type: str = "1") -> str:
    """KIS WS 구독 메시지 생성.

    tr_type: "1"=구독등록, "2"=구독해제
    TR ID: H0STCNT0 = 주식체결 실시간 (실거래/모의 공통)
    """
    return json.dumps({
        "header": {
            "approval_key": approval_key,
            "custtype":     "P",
            "tr_type":      tr_type,
            "content-type": "utf-8",
        },
        "body": {
            "input": {
                "tr_id":  "H0STCNT0",
                "tr_key": stock_code,
            },
        },
    })


# ── 데이터 파싱 ────────────────────────────────────────────────────────────────

def _parse_realtime(msg: str) -> Optional[Dict]:
    """KIS H0STCNT0 실시간 체결 메시지 파싱.

    응답 형식: 0|H0STCNT0|001|데이터필드들^...
    주요 필드 (0-index, ^구분):
        0  : MKSC_SHRN_ISCD  — 종목코드
        1  : STCK_CNTG_HOUR  — 체결시간
        2  : STCK_PRPR       — 현재가
        3  : PRDY_VRSS_SIGN  — 전일대비부호 (1:상한, 2:상승, 3:보합, 4:하한, 5:하락)
        4  : PRDY_VRSS       — 전일대비
        5  : PRDY_CTRT       — 전일대비율
        13 : ACML_VOL        — 누적거래량
    """
    try:
        # 시스템 메시지(JSON) 제외
        if not msg or msg.startswith("{"):
            return None

        parts = msg.split("|")
        if len(parts) < 4:
            return None

        # parts[0]="0", parts[1]=TR_ID, parts[2]=건수, parts[3]=데이터
        tr_id = parts[1].strip()
        if tr_id != "H0STCNT0":
            return None

        fields = parts[3].split("^")
        if len(fields) < 14:
            return None

        code = fields[0].strip()
        if not code:
            return None

        def _fv(idx: int) -> float:
            v = str(fields[idx]).replace(",", "").replace("+", "").strip()
            try:
                return float(v) if v else 0.0
            except ValueError:
                return 0.0

        price = abs(_fv(2))
        # 전일대비부호: 4=하한, 5=하락 → 음수
        sign = fields[3].strip()
        change = _fv(4)
        change_rate = _fv(5)
        if sign in ("4", "5"):
            change = -abs(change)
            change_rate = -abs(change_rate)

        return {
            "stock_code":    code,
            "current_price": price,
            "change":        change,
            "change_rate":   change_rate,
            "volume":        int(abs(_fv(13))),
        }
    except Exception as e:
        logger.debug("파싱 오류: %s", e)
    return None


# ── KisWebSocketManager ────────────────────────────────────────────────────────────────

class KisWebSocketManager:
    """KIS WebSocket 연결을 유지하며 실시간 체결가를 _price_store에 저장한다."""

    def __init__(self, is_mock: bool = False):
        self._ws_url        = "ws://openskh.koreainvestment.com:31000" if is_mock else _WS_URL
        self._approval_key: Optional[str] = None
        self._subscribed:   Set[str] = set()
        self._running       = False
        self._task: Optional[asyncio.Task] = None

    # ── 공개 API ──────────────────────────────────────────────────────────────

    async def start(self, initial_codes: list[str]) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop(initial_codes))
        logger.info("KIS WebSocket 백그라운드 태스크 시작")

    async def stop(self) -> None:
        self._running = False
        if hasattr(self, "_ws") and self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def subscribe(self, codes: list[str]) -> None:
        new_codes = [c for c in codes if c not in self._subscribed]
        if new_codes:
            self._pending_subscribe = getattr(self, "_pending_subscribe", set())
            self._pending_subscribe.update(new_codes)

    # ── 내부 루프 ─────────────────────────────────────────────────────────────

    async def _run_loop(self, initial_codes: list[str]) -> None:
        import websockets  # lazy import
        from websockets.exceptions import InvalidStatus

        self._pending_subscribe: Set[str] = set(initial_codes)
        self._already_in_use    = False   # ALREADY IN USE 감지 플래그
        backoff = 15  # 초기 backoff 15초: KIS 서버 세션 정리 시간 확보
        consecutive_500 = 0
        _MAX_CONSECUTIVE_500 = 5   # 500 연속 5회 → 포기 (포털 설정 문제)
        _is_first_connect = True

        while self._running:
            if not self._pending_subscribe and not self._subscribed:
                await asyncio.sleep(5)
                continue

            # 동시 로그인 방지: 워커들이 순서대로 연결하도록 직렬화
            _lock = _get_connect_lock()
            await _lock.acquire()
            _lock_released = False

            try:
                # 재접속 시 또는 ALREADY IN USE 발생 시 approval_key 강제 갱신
                force_key_refresh = not _is_first_connect or self._already_in_use
                self._already_in_use = False
                self._approval_key = await asyncio.to_thread(
                    _get_approval_key, force_key_refresh
                )
                _is_first_connect = False

                logger.info("KIS WS 연결 시도: %s", self._ws_url)
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=None,
                    close_timeout=10,
                ) as ws:
                    # KIS WS는 추가 로그인 TR 불필요 — approval_key는 구독 메시지에 포함
                    prev_codes = set(self._subscribed)
                    self._subscribed.clear()
                    if prev_codes:
                        self._pending_subscribe.update(prev_codes)
                        logger.info("재연결 — %d개 종목 재구독 예약", len(prev_codes))
                    self._ws = ws
                    backoff = 15

                    await asyncio.sleep(0.5)
                    _lock.release()
                    _lock_released = True

                    recv_task   = asyncio.create_task(self._recv_loop(ws))
                    sender_task = asyncio.create_task(self._sender_loop(ws))
                    try:
                        await asyncio.gather(recv_task, sender_task)
                    except Exception:
                        recv_task.cancel()
                        sender_task.cancel()
                        raise

            except InvalidStatus as e:
                # HTTP 수준 거부 — 응답 본문 로깅으로 정확한 원인 확인
                try:
                    body = e.response.body.decode("utf-8", errors="replace")
                except Exception:
                    body = str(e)

                if e.response.status_code == 500:
                    consecutive_500 += 1
                    if consecutive_500 >= _MAX_CONSECUTIVE_500:
                        logger.error(
                            "KIS WS HTTP 500 연속 %d회 — REST 폴링으로 전환합니다.",
                            consecutive_500,
                        )
                        global _ws_available
                        _ws_available = False
                        self._running = False
                        asyncio.get_event_loop().create_task(
                            _start_rest_polling(list(self._pending_subscribe))
                        )
                        break
                    logger.warning(
                        "KIS WS HTTP 500 (%d/%d): %s",
                        consecutive_500, _MAX_CONSECUTIVE_500, body[:200],
                    )
                else:
                    consecutive_500 = 0
                    logger.warning(
                        "KIS WS HTTP %d 거부: %s — %d초 후 재연결",
                        e.response.status_code, body[:200], backoff,
                    )
                    # approval_key 무효화
                    if e.response.status_code in (401, 403):
                        _approval_key_cache["key"] = None
                        _approval_key_cache["expires_at"] = 0.0

                if not self._running:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
            except Exception as e:
                err_msg = str(e)
                if "no close frame" in err_msg:
                    logger.debug("KIS WS 연결 종료 — %d초 후 재연결", backoff)
                else:
                    logger.warning("KIS WS 연결 오류: %s — %d초 후 재연결", e, backoff)
                if not self._running:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)
            else:
                if self._running:
                    if self._already_in_use:
                        logger.info("KIS WS ALREADY IN USE 대기 — 30초 후 재접속")
                        await asyncio.sleep(30)  # KIS 서버 세션 해제 대기
                        # backoff 는 초기화하지 않음 — 다음 실패 시 정상 증가
                    else:
                        logger.debug("KIS WS 연결 종료 — %d초 후 재연결", backoff)
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 120)
            finally:
                # 락이 아직 해제되지 않았다면 (연결/로그인 실패 등) 여기서 해제
                if not _lock_released:
                    try:
                        _lock.release()
                    except RuntimeError:
                        pass

    async def _recv_loop(self, ws) -> None:
        async for raw in ws:
            if not self._running:
                break

            if isinstance(raw, str) and raw.startswith("{"):
                try:
                    sys_msg = json.loads(raw)
                    hdr = sys_msg.get("header", {})
                    tr_id = hdr.get("tr_id", "")

                    if tr_id == "PINGPONG":
                        # KIS 서버 PINGPONG을 그대로 echo
                        try:
                            await ws.send(raw)
                        except Exception:
                            pass
                        continue

                    # 구독 응답 확인
                    body = sys_msg.get("body", {})
                    rt_cd = str(body.get("rt_cd", "0"))
                    if rt_cd != "0":
                        msg_text = body.get("msg1", "")
                        logger.warning("KIS WS 구독 응답 오류 [%s]: %s", tr_id, msg_text)
                        if "ALREADY IN USE" in msg_text.upper():
                            # appkey 중복 사용 → 즉시 연결 종료 (30초 대기는 _run_loop에서 처리)
                            logger.warning("KIS WS ALREADY IN USE — 연결 즉시 종료, 재접속 대기 중...")
                            self._already_in_use = True
                            try:
                                await ws.close()
                            except Exception:
                                pass
                            return  # _recv_loop 종료 → _sender_loop도 곧 ConnectionClosed로 종료됨
                    continue

                except (ConnectionError, asyncio.CancelledError):
                    raise
                except Exception:
                    pass
                continue

            # 실시간 체결 데이터 파싱 (pipe 형식)
            if isinstance(raw, str):
                parsed = _parse_realtime(raw)
                if parsed:
                    _price_store[parsed["stock_code"]] = parsed
                    logger.debug("수신 %s: %s", parsed["stock_code"], parsed["current_price"])

    async def _sender_loop(self, ws) -> None:
        while self._running:
            try:
                await self._flush_pending(ws)
            except Exception:
                break  # ConnectionClosed 포함 모든 연결 오류 → 루프 종료
            await asyncio.sleep(0.5)

    async def _flush_pending(self, ws) -> None:
        try:
            from websockets.exceptions import ConnectionClosed as _WsCC
        except ImportError:
            _WsCC = Exception  # type: ignore[misc,assignment]

        pending: Set[str] = getattr(self, "_pending_subscribe", set())
        for code in list(pending):
            if len(self._subscribed) >= _MAX_SUBSCRIPTIONS:
                logger.info("KIS WS 구독 한도 (%d) 도달", _MAX_SUBSCRIPTIONS)
                pending.clear()
                return
            if code not in self._subscribed:
                try:
                    msg = _build_subscribe_msg(self._approval_key, code)
                    await ws.send(msg)
                    self._subscribed.add(code)
                    logger.debug("KIS WS 구독: %s", code)
                    await asyncio.sleep(0.05)
                except _WsCC:
                    raise
                except Exception as e:
                    logger.debug("구독 전송 실패 %s: %s", code, e)
                    raise
            pending.discard(code)


# 하위 호환 (키움에서 교체된 코드와의 호환)
KiwoomWebSocketManager = KisWebSocketManager


# ── REST 폴링 폴백 ─────────────────────────────────────────────────────────────

_rest_polling_task: Optional[asyncio.Task] = None
_rest_poll_codes:   Set[str] = set()
_REST_POLL_INTERVAL = int(os.getenv("REST_POLL_INTERVAL", "10"))  # 초


async def _rest_poll_once(codes: list[str]) -> None:
    """kis_client.get_current_price 를 사용해 가격을 _price_store에 갱신."""
    try:
        from kis_client import get_current_price
    except ImportError:
        logger.error("REST 폴링: kis_client import 실패")
        return

    for code in codes:
        try:
            data = await asyncio.to_thread(get_current_price, code)
            _price_store[code] = {
                "stock_code":    code,
                "current_price": data.get("current_price", 0),
                "change":        data.get("change", 0),
                "change_rate":   data.get("change_rate", 0),
                "volume":        data.get("volume", 0),
            }
        except Exception as e:
            logger.debug("REST 폴링 오류 [%s]: %s", code, e)
        await asyncio.sleep(0.08)   # KIS rate limit 대응


async def _start_rest_polling(initial_codes: list[str]) -> None:
    global _rest_polling_task, _rest_poll_codes
    _rest_poll_codes.update(initial_codes)

    if _rest_polling_task and not _rest_polling_task.done():
        logger.info("REST 폴링 이미 실행 중 (%d개 종목)", len(_rest_poll_codes))
        return

    async def _loop():
        logger.info("REST 폴링 시작: %d개 종목, %d초 간격", len(_rest_poll_codes), _REST_POLL_INTERVAL)
        while True:
            codes = list(_rest_poll_codes)
            if codes:
                await _rest_poll_once(codes)
            await asyncio.sleep(_REST_POLL_INTERVAL)

    _rest_polling_task = asyncio.create_task(_loop())


# ── 전역 접근자 ───────────────────────────────────────────────────────────────
# KIS는 appkey당 WebSocket 연결을 1개만 허용합니다.
# 따라서 단일 KisWebSocketManager(Singleton)로 최대 40종목만 구독하고,
# 나머지 종목은 REST 폴링(_start_rest_polling)으로 처리합니다.

async def init_manager(initial_codes: list[str], is_mock: bool = False) -> None:
    """FastAPI startup_event에서 1회 호출.

    KIS WebSocket은 appkey당 1연결만 허용하므로 단일 Singleton 연결을 사용합니다.
    - 상위 _MAX_SUBSCRIPTIONS(40)개 종목만 WebSocket 구독
    - 나머지 종목은 REST 폴링으로 처리
    """
    global _manager

    ws_codes   = initial_codes[:_MAX_SUBSCRIPTIONS]
    poll_codes = initial_codes[_MAX_SUBSCRIPTIONS:]

    _manager = KisWebSocketManager(is_mock=is_mock)
    await _manager.start(ws_codes)

    if ws_codes:
        logger.info("KIS WebSocket 단일 연결 시작: %d개 종목 구독", len(ws_codes))
    if poll_codes:
        logger.info("나머지 %d개 종목은 REST 폴링으로 처리", len(poll_codes))
        await _start_rest_polling(poll_codes)


async def add_poll_codes(codes: list[str]) -> None:
    """REST 폴링 대상 종목 추가 (WS 비활성 상태일 때 사용)."""
    _rest_poll_codes.update(codes)
    if not _ws_available:
        await _start_rest_polling([])


def get_manager() -> Optional[KisWebSocketManager]:
    return _manager


def get_price_store() -> Dict[str, Dict]:
    """SSE 엔드포인트 등에서 최신 체결가 참조용."""
    return _price_store
