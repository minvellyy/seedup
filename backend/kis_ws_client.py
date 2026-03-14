"""키움증권 Open Trading API 실시간 WebSocket 관리자.

한국투자증권(KIS) WebSocket에서 키움증권 WebSocket으로 교체.
함수/클래스 인터페이스 동일 유지 — 기존 import 변경 불필요.

WebSocket URL: wss://api.kiwoom.com/ws
인증: Authorization: Bearer {token} 헤더 (연결 시)
구독 TR: 0B (주식체결 실시간)
구독 메시지: {"trnm": "REG", "grp_no": "1", "refresh": "1",
              "data": [{"item": ["005930"], "type": ["0B"]}]}
응답 필드: 10=현재가, 11=전일대비, 12=등락율, 13=누적거래량
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Set

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

logger = logging.getLogger("kiwoom_ws")

# ── 환경 변수 ─────────────────────────────────────────────────────────────────
# 키움 WebSocket 1연결당 최대 구독 종목 수 (필요 시 .env에서 조정)
_MAX_SUBSCRIPTIONS = int(os.getenv("KIS_MAX_SUBSCRIPTIONS", "100"))

# 키움 WebSocket URL
_WS_URL = "wss://api.kiwoom.com:10000/api/dostk/websocket"

# ── 전역 상태 ──────────────────────────────────────────────────────────────────
_price_store: Dict[str, Dict] = {}   # { "005930": {"current_price": 75000, ...} }
_manager: Optional["KiwoomWebSocketManager"] = None
_ws_available: bool = True           # False = WS 포기, REST 폴링 사용 중
_ws_connect_lock: Optional[asyncio.Lock] = None  # 워커 간 동시 로그인 방지


def _get_connect_lock() -> asyncio.Lock:
    """모든 워커가 공유하는 연결 직렬화 Lock — 동시 로그인으로 인한 연결 충돌 방지."""
    global _ws_connect_lock
    if _ws_connect_lock is None:
        _ws_connect_lock = asyncio.Lock()
    return _ws_connect_lock


# ── 토큰 — kis_client 와 공유 (APP KEY 당 유효 토큰 1개 제한 대응) ─────────────

def _get_token() -> str:
    """kis_client._get_token()을 위임 호출 — 동일 캐시/토큰 공유."""
    from kis_client import _get_token as _client_get_token
    return _client_get_token()


# ── 구독 메시지 생성 ───────────────────────────────────────────────────────────

_REALTIME_TR_IDS = ["0B"]   # 0B=주식체결, 0A=주식기세, 0H=주식예상체결


def _build_subscribe_msg(token: str, stock_code: str, tr_type: str = "3") -> str:
    """키움 WS 구독 메시지 생성 (공식 문서 기준).

    trnm: REG=구독등록, UNREG=해제
    refresh: 1=기존등록유지
    type: 0B=주식체결, 0A=주식기세
    인증(token)은 연결 헤더에서 처리되므로 메시지 본문에는 포함하지 않음.
    """
    trnm = "REG" if tr_type != "4" else "UNREG"
    return json.dumps({
        "trnm":    trnm,
        "grp_no": "1",
        "refresh": "1",
        "data": [{"item": [stock_code], "type": ["0B"]}],
    })


# ── 데이터 파싱 ────────────────────────────────────────────────────────────────

def _parse_realtime(msg: str) -> Optional[Dict]:
    """키움 0B 실시간 체결 메시지 파싱.

    공식 문서 응답 필드:
        10 = 현재가
        11 = 전일대비
        12 = 등락율
        13 = 누적거래량
        302 = 종목명
        9081 = 거래소구분 (1:KRX, 2:NXT)

    예시 응답:
    {
      "trnm": "REAL",
      "grp_no": "1",
      "data": [{"item_cd": "005930", "values": {"10": "75000", "11": "500",
                                                 "12": "0.67", "13": "1234567"}}]
    }
    """
    try:
        data = json.loads(msg)
        trnm = data.get("trnm", "")

        # 실시간 데이터 응답만 처리
        if trnm not in ("REAL", "RSPN", ""):
            return None

        entries = data.get("data", [])
        if not entries:
            return None

        row = entries[0] if isinstance(entries, list) else entries
        code = str(row.get("item_cd", "") or row.get("stk_cd", "")).strip()
        if not code:
            return None

        # values가 별도 dict인 경우와 flat인 경우 모두 처리
        vals = row.get("values", row)

        def _fv(k: str) -> float:
            v = str(vals.get(k, 0) or 0).replace(",", "").replace("+", "")
            try:
                return float(v)
            except ValueError:
                return 0.0

        price = abs(_fv("10"))   # 하락 시 음수로 오는 경우 대비
        return {
            "stock_code":    code,
            "current_price": price,
            "change":        _fv("11"),
            "change_rate":   _fv("12"),
            "volume":        int(abs(_fv("13"))),
        }
    except Exception as e:
        logger.debug("파싱 오류: %s", e)
    return None


# ── KiwoomWebSocketManager ────────────────────────────────────────────────────

class KiwoomWebSocketManager:
    """키움 WebSocket 연결을 유지하며 실시간 체결가를 _price_store에 저장한다."""

    def __init__(self, is_mock: bool = False):
        self._ws_url      = _WS_URL
        self._token: Optional[str] = None
        self._subscribed:   Set[str] = set()
        self._running       = False
        self._task: Optional[asyncio.Task] = None

    # ── 공개 API ──────────────────────────────────────────────────────────────

    async def start(self, initial_codes: list[str]) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop(initial_codes))
        logger.info("키움 WebSocket 백그라운드 태스크 시작")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def subscribe(self, codes: list[str]) -> None:
        new_codes = [c for c in codes if f"{c}:vi0002" not in self._subscribed]
        if new_codes:
            self._pending_subscribe = getattr(self, "_pending_subscribe", set())
            self._pending_subscribe.update(new_codes)

    # ── 내부 루프 ─────────────────────────────────────────────────────────────

    async def _run_loop(self, initial_codes: list[str]) -> None:
        import websockets  # lazy import
        from websockets.exceptions import InvalidStatus

        self._pending_subscribe: Set[str] = set(initial_codes)
        backoff = 5
        consecutive_500 = 0
        _MAX_CONSECUTIVE_500 = 5   # 500 연속 5회 → 포기 (포털 설정 문제)

        while self._running:
            if not self._pending_subscribe and not self._subscribed:
                await asyncio.sleep(5)
                continue

            # 동시 로그인 방지: 워커들이 순서대로 연결하도록 직렬화
            _lock = _get_connect_lock()
            await _lock.acquire()
            _lock_released = False

            try:
                self._token = _get_token()

                logger.info("키움 WS 연결 시도: %s", self._ws_url)
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=None,
                    close_timeout=10,
                ) as ws:
                    # 연결 후 로그인 TR 전송 (키움 WS 인증 방식)
                    await ws.send(json.dumps({"trnm": "LOGIN", "token": self._token}))
                    try:
                        login_raw = await asyncio.wait_for(ws.recv(), timeout=10)
                        login_resp = json.loads(login_raw)
                        rc = str(login_resp.get("return_code", "0"))
                        if rc != "0":
                            raise ConnectionError(f"WS 로그인 실패: {login_resp.get('return_msg', '')}")
                        logger.info("키움 WS 로그인 성공")
                    except asyncio.TimeoutError:
                        logger.warning("WS 로그인 응답 타임아웃 — 계속 진행")
                    prev_codes = {s.split(":")[0] for s in self._subscribed}
                    self._subscribed.clear()
                    if prev_codes:
                        self._pending_subscribe.update(prev_codes)
                        logger.info("재연결 — %d개 종목 재구독 예약", len(prev_codes))
                    self._ws = ws
                    backoff = 5

                    # 로그인 완료 후 락 해제 — 다음 워커가 순차적으로 연결 가능
                    await asyncio.sleep(1.0)
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
                            "키움 WS HTTP 500 연속 %d회 — REST 폴링으로 전환합니다. "
                            "(포털 WebSocket 권한 또는 서버 상태 확인 필요)",
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
                        "키움 WS HTTP 500 (%d/%d) — 포털 WebSocket 권한 확인 필요: %s",
                        consecutive_500, _MAX_CONSECUTIVE_500, body[:200],
                    )
                else:
                    consecutive_500 = 0
                    logger.warning(
                        "키움 WS HTTP %d 거부 → %s — %d초 후 재연결",
                        e.response.status_code, body[:200], backoff,
                    )
                    # 인증 오류면 kis_client 토큰 캐시 강제 무효화
                    if e.response.status_code in (401, 403):
                        from kis_client import _get_token as _ct, _token_cache as _cc, _TOKEN_FILE as _cf
                        _cc["token"] = None
                        _cc["expires_at"] = 0.0
                        try:
                            if _cf.exists():
                                _cf.unlink()
                        except Exception:
                            pass

                if not self._running:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            except Exception as e:
                err_msg = str(e)
                if "no close frame" in err_msg:
                    logger.debug("키움 WS 연결 종료 — %d초 후 재연결", backoff)
                else:
                    logger.warning("키움 WS 연결 오류: %s — %d초 후 재연결", e, backoff)
                if not self._running:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            else:
                # 정상 종료(예외 없음) — 즉시 재연결하면 동시 로그인 재발
                if self._running:
                    logger.debug("키움 WS 연결 종료 — %d초 후 재연결", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
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

            # PINGPONG 처리 (문자열 형식)
            if raw in ("PINGPONG", "ping", "pong"):
                try:
                    await ws.send("PINGPONG")
                except Exception:
                    pass
                continue

            if raw.startswith("{"):
                try:
                    sys_msg = json.loads(raw)
                    trnm    = sys_msg.get("trnm", "")

                    if trnm == "PING":
                        # 키움 공식 PING: 수신한 메시지를 그대로 echo
                        try:
                            await ws.send(raw)
                        except Exception:
                            pass
                        continue

                    if trnm == "REAL":
                        # 실시간 체결 데이터
                        parsed = _parse_realtime(raw)
                        if parsed:
                            _price_store[parsed["stock_code"]] = parsed
                            logger.debug("수신 %s: %s", parsed["stock_code"], parsed["current_price"])
                        continue

                    if trnm in ("RSPN", "LOGIN"):
                        # 구독/로그인 응답
                        return_code = str(sys_msg.get("return_code", "0"))
                        msg = sys_msg.get("return_msg", "")
                        if return_code != "0":
                            # 토큰 만료
                            if "token" in msg.lower() or "인증" in msg:
                                logger.info("토큰 만료 감지 — 재연결 예약")
                                raise ConnectionError("token_expired")
                            logger.warning("키움 WS 응답 오류 [%s]: %s", trnm, msg)
                        continue

                except (ConnectionError, asyncio.CancelledError):
                    raise
                except Exception:
                    pass
                continue

            # JSON이 아닌 텍스트 메시지 (fallback)
            parsed = _parse_realtime(raw)
            if parsed:
                _price_store[parsed["stock_code"]] = parsed

    async def _sender_loop(self, ws) -> None:
        last_ping = asyncio.get_event_loop().time()
        while self._running:
            try:
                await self._flush_pending(ws)
            except Exception:
                break  # ConnectionClosed 포함 모든 연결 오류 → 루프 종료
            now = asyncio.get_event_loop().time()
            if now - last_ping >= 30:
                try:
                    await ws.send("PINGPONG")
                    last_ping = now
                except Exception:
                    break
            await asyncio.sleep(0.5)

    async def _flush_pending(self, ws) -> None:
        try:
            from websockets.exceptions import ConnectionClosed as _WsCC
        except ImportError:
            _WsCC = Exception  # type: ignore[misc,assignment]

        pending: Set[str] = getattr(self, "_pending_subscribe", set())
        for code in list(pending):
            current_count = len(self._subscribed)
            if current_count >= _MAX_SUBSCRIPTIONS:
                logger.info("키움 WS 구독 한도 (%d) 도달 — 나머지 %d개 생략", _MAX_SUBSCRIPTIONS, len(pending))
                pending.clear()
                return
            sub_key = f"{code}:vi0002"
            if sub_key not in self._subscribed:
                try:
                    msg = _build_subscribe_msg(self._token, code)
                    await ws.send(msg)
                    self._subscribed.add(sub_key)
                    logger.debug("키움 WS 구독: %s", code)
                    await asyncio.sleep(0.05)
                except _WsCC:
                    # 연결이 끊어짐 — 상위(_sender_loop)가 잡아서 루프 종료 처리
                    raise
                except Exception as e:
                    # transport 오류 등 연결 문제 — DEBUG 로그 후 상위에 전달
                    logger.debug("구독 전송 실패 %s: %s", code, e)
                    raise
            pending.discard(code)


# KIS 코드와의 하위 호환을 위해 KisWebSocketManager도 동일 클래스로 노출
KisWebSocketManager = KiwoomWebSocketManager


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
        await asyncio.sleep(0.08)   # 키움 rate limit 대응


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


# ── WebSocket Pool ─────────────────────────────────────────────────────────────

class KisWebSocketPool:
    """KiwoomWebSocketManager 여러 개를 생성해 대량 종목을 커버한다."""

    def __init__(self, is_mock: bool = False):
        self._is_mock = is_mock
        self._workers: list[KiwoomWebSocketManager] = []

    async def start(self, initial_codes: list[str]) -> None:
        if not initial_codes:
            return
        for i in range(0, len(initial_codes), _MAX_SUBSCRIPTIONS):
            chunk = initial_codes[i: i + _MAX_SUBSCRIPTIONS]
            w = KiwoomWebSocketManager(is_mock=self._is_mock)
            self._workers.append(w)
            await w.start(chunk)
        logger.info("키움 WebSocket Pool 시작: %d개 연결, 총 %d개 종목", len(self._workers), len(initial_codes))

    async def stop(self) -> None:
        for w in self._workers:
            await w.stop()
        self._workers.clear()

    async def subscribe(self, codes: list[str]) -> None:
        remaining = list(codes)
        for w in self._workers:
            if not remaining:
                break
            current = len(w._subscribed)
            capacity = _MAX_SUBSCRIPTIONS - current
            if capacity > 0:
                await w.subscribe(remaining[:capacity])
                remaining = remaining[capacity:]
        while remaining:
            chunk = remaining[:_MAX_SUBSCRIPTIONS]
            remaining = remaining[_MAX_SUBSCRIPTIONS:]
            w = KiwoomWebSocketManager(is_mock=self._is_mock)
            self._workers.append(w)
            await w.start(chunk)

    @property
    def worker_count(self) -> int:
        return len(self._workers)

    @property
    def total_subscribed(self) -> int:
        return sum(len(w._subscribed) for w in self._workers)


# ── 전역 접근자 ───────────────────────────────────────────────────────────────

async def init_manager(initial_codes: list[str], is_mock: bool = False) -> None:
    """FastAPI startup_event에서 1회 호출.
    키움 연결당 최대 100종목 제한 대응 — 100개 초과 시 Pool로 다수 연결 생성.
    """
    global _manager
    if len(initial_codes) <= _MAX_SUBSCRIPTIONS:
        _manager = KiwoomWebSocketManager(is_mock=is_mock)
        await _manager.start(initial_codes)
    else:
        pool = KisWebSocketPool(is_mock=is_mock)
        await pool.start(initial_codes)
        _manager = pool  # type: ignore[assignment]


async def add_poll_codes(codes: list[str]) -> None:
    """REST 폴링 대상 종목 추가 (WS 비활성 상태일 때 사용)."""
    _rest_poll_codes.update(codes)
    if not _ws_available:
        await _start_rest_polling([])


def get_manager() -> Optional[KiwoomWebSocketManager]:
    return _manager


def get_price_store() -> Dict[str, Dict]:
    """SSE 엔드포인트 등에서 최신 체결가 참조용."""
    return _price_store
