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

# ── 멀티 appkey 목록 로드 ────────────────────────────────────────────────────
# .env에 등록된 appkey 쌍을 순서대로 읽음:
#   APP_KEY   / APP_SECRET    (기존 단일 키, 항상 사용)
#   APP_KEY_2 / APP_SECRET_2  (추가 키)
#   APP_KEY_3 / APP_SECRET_3
#   ...최대 APP_KEY_5 / APP_SECRET_5
#
# appkey 1개 = WS 연결 1개 = 최대 40종목
# 예: 3개 등록 시 최대 120종목 WS 실시간, 나머지는 REST 폴링
def _load_appkey_pairs() -> list:
    """등록된 (appkey, appsecret) 쌍 목록 반환."""
    pairs = []
    # 첫 번째 키 (APP_KEY / APP_SECRET 또는 APP_KEY_1 / APP_SECRET_1)
    k1 = os.getenv("APP_KEY", "").strip() or os.getenv("APP_KEY_1", "").strip()
    s1 = os.getenv("APP_SECRET", "").strip() or os.getenv("APP_SECRET_1", "").strip()
    if k1 and s1:
        pairs.append((k1, s1))
    # APP_KEY_2 ~ APP_KEY_5
    for n in range(2, 6):
        k = os.getenv(f"APP_KEY_{n}", "").strip()
        s = os.getenv(f"APP_SECRET_{n}", "").strip()
        if k and s:
            pairs.append((k, s))
    return pairs

_APPKEY_PAIRS: list = _load_appkey_pairs()  # [(appkey, appsecret), ...]

# ── 전역 상태 ──────────────────────────────────────────────────────────────────
_price_store: Dict[str, Dict] = {}   # { "005930": {"current_price": 75000, ...} }
_price_queues: Dict[str, Set] = {}    # { stock_code: {asyncio.Queue, ...} }  fan-out용
_manager: Optional["KisWebSocketManager"] = None
_managers: list = []                 # 멀티 appkey 시 복수 manager 목록
_ws_available: bool = True           # False = WS 포기, REST 폴링 사용 중
_ws_connect_lock: Optional[asyncio.Lock] = None  # 워커 간 동시 로그인 방지


def _fanout_price_update(stock_code: str, data: Dict) -> None:
    """해당 종목을 구독 중인 SSE 큐들로 최신 가격을 push."""
    queues = _price_queues.get(stock_code)
    if not queues:
        return
    for queue in list(queues):
        try:
            queue.put_nowait({"code": stock_code, "data": data})
        except asyncio.QueueFull:
            pass


def _normalize_code_list(codes: list) -> list[str]:
    """코드 목록을 6자리 숫자 문자열로 정규화/중복제거한다."""
    if not codes:
        return []
    seen = set()
    normalized: list[str] = []
    for raw in codes:
        code = str(raw).strip()
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


def _get_connect_lock() -> asyncio.Lock:
    """모든 워커가 공유하는 연결 직렬화 Lock."""
    global _ws_connect_lock
    if _ws_connect_lock is None:
        _ws_connect_lock = asyncio.Lock()
    return _ws_connect_lock


# ── Approval Key ──────────────────────────────────────────────────────────────
# KIS WebSocket 전용 인증키 (access_token과 별도로 발급)
# appkey별로 캐시: { appkey_str: {"key": str, "expires_at": float} }
_approval_key_cache: Dict = {}
_approval_key_lock = threading.Lock()


def _get_approval_key(force_refresh: bool = False, appkey: str = "", appsecret: str = "") -> str:
    """KIS WebSocket approval_key 발급 (24시간 유효).

    appkey/appsecret을 명시하면 해당 키로 발급, 없으면 기본 APP_KEY 사용.
    """
    _appkey    = appkey    or os.getenv("APP_KEY", "").strip()
    _appsecret = appsecret or os.getenv("APP_SECRET", "").strip()
    _cache_key = _appkey  # appkey별로 캐시 분리

    now = time.time()
    if not force_refresh and _approval_key_cache.get(_cache_key, {}).get("key") \
            and _approval_key_cache[_cache_key]["expires_at"] > now + 60:
        return _approval_key_cache[_cache_key]["key"]

    with _approval_key_lock:
        now = time.time()
        if not force_refresh and _approval_key_cache.get(_cache_key, {}).get("key") \
                and _approval_key_cache[_cache_key]["expires_at"] > now + 60:
            return _approval_key_cache[_cache_key]["key"]

        resp = requests.post(
            f"{_BASE_URL}/oauth2/Approval",
            json={
                "grant_type": "client_credentials",
                "appkey":     _appkey,
                "secretkey":  _appsecret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        key = data.get("approval_key", "")
        if not key:
            raise ValueError(f"approval_key 발급 실패: {data}")
        _approval_key_cache[_cache_key] = {"key": key, "expires_at": now + 86400}
        logger.info("KIS WebSocket approval_key 발급 완료 (appkey: ...%s)", _appkey[-6:])
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

    def __init__(self, is_mock: bool = False, appkey: str = "", appsecret: str = ""):
        self._ws_url        = "ws://openskh.koreainvestment.com:31000" if is_mock else _WS_URL
        self._appkey        = appkey    or os.getenv("APP_KEY", "").strip()
        self._appsecret     = appsecret or os.getenv("APP_SECRET", "").strip()
        self._approval_key: Optional[str] = None
        self._subscribed:          Set[str] = set()
        self._pending_subscribe:   Set[str] = set()
        self._pending_unsubscribe: Set[str] = set()
        self._subscribe_event              = asyncio.Event()
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
            self._pending_subscribe.update(new_codes)
            self._subscribe_event.set()  # idle 중인 _run_loop 즉시 깨우기

    async def unsubscribe(self, codes: list[str]) -> None:
        """구독 해제 요청 — _flush_pending에서 WS 메시지 전송 처리."""
        for code in codes:
            self._pending_unsubscribe.add(code)
            self._pending_subscribe.discard(code)  # 미전송 구독 요청도 취소

    # ── 내부 루프 ─────────────────────────────────────────────────────────────

    async def _run_loop(self, initial_codes: list[str]) -> None:
        import websockets  # lazy import
        from websockets.exceptions import InvalidStatus

        self._pending_subscribe.update(initial_codes)
        self._already_in_use    = False   # ALREADY IN USE 감지 플래그
        backoff = 15  # 초기 backoff 15초: KIS 서버 세션 정리 시간 확보
        consecutive_500 = 0
        consecutive_already_in_use = 0   # ALREADY IN USE 연속 횟수 (지수 백오프용)
        _MAX_CONSECUTIVE_500 = 5   # 500 연속 5회 → 포기 (포털 설정 문제)
        _is_first_connect = True

        while self._running:
            if not self._pending_subscribe and not self._subscribed:
                # 구독 요청이 올 때까지 최대 5초 대기 (이벤트로 즉시 깨어남)
                try:
                    await asyncio.wait_for(self._subscribe_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                self._subscribe_event.clear()
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
                    _get_approval_key, force_key_refresh, self._appkey, self._appsecret
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
                    # consecutive_already_in_use는 여기서 리셋하지 않음:
                    # TCP 연결 성공이어도 구독 응답에서 ALREADY IN USE가 다시 올 수 있음.
                    # 카운터는 ALREADY IN USE 없이 정상 완료된 경우에만 초기화 (else 블록).

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
                if self._already_in_use:
                    # ALREADY IN USE: KIS appkey 세션이 서버에 살아있음.
                    # 새 approval_key를 발급해도 appkey 자체가 락되어 있으므로 충분히 대기해야 함.
                    # 대기 시간: 90→180→300초 (90초 기준 지수 백오프, 최대 5분)
                    consecutive_already_in_use += 1
                    wait = min(90 * (2 ** (consecutive_already_in_use - 1)), 300)
                    logger.info(
                        "KIS WS ALREADY IN USE (%d회) — appkey 세션 해제 대기 %d초 후 재접속",
                        consecutive_already_in_use, wait,
                    )
                    if not self._running:
                        break
                    await asyncio.sleep(wait)
                else:
                    # 일반 연결 오류: ALREADY IN USE가 아니었으므로 카운터 초기화
                    consecutive_already_in_use = 0
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
                        # _sender_loop가 break으로 종료할 경우에도 여기로 옴
                        # (gather에 예외가 전파되지 않는 경우)
                        consecutive_already_in_use += 1
                        wait = min(90 * (2 ** (consecutive_already_in_use - 1)), 300)
                        logger.info(
                            "KIS WS ALREADY IN USE (%d회) — appkey 세션 해제 대기 %d초 후 재접속",
                            consecutive_already_in_use, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        consecutive_already_in_use = 0
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
                    _fanout_price_update(parsed["stock_code"], parsed)

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

        # ① 구독 해제 먼저 처리 (tr_type="2")
        pending_unsub: Set[str] = self._pending_unsubscribe
        for code in list(pending_unsub):
            if code in self._subscribed:
                try:
                    msg = _build_subscribe_msg(self._approval_key, code, tr_type="2")
                    await ws.send(msg)
                    self._subscribed.discard(code)
                    logger.debug("KIS WS 구독 해제: %s", code)
                    await asyncio.sleep(0.05)
                except _WsCC:
                    raise
                except Exception as e:
                    logger.debug("구독 해제 전송 실패 %s: %s", code, e)
            pending_unsub.discard(code)

        # ② 구독 등록 처리 (tr_type="1")
        pending: Set[str] = self._pending_subscribe
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
            parsed = {
                "stock_code":    code,
                "current_price": data.get("current_price", 0),
                "change":        data.get("change", 0),
                "change_rate":   data.get("change_rate", 0),
                "volume":        data.get("volume", 0),
            }
            _price_store[code] = parsed
            _fanout_price_update(code, parsed)
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


# ── SSE fan-out 헬퍼 ─────────────────────────────────────────────────────────

def register_queue(codes: list, queue) -> None:
    """SSE 연결 시 호출 — 해당 종목 가격 업데이트를 queue로 수신 등록."""
    for code in _normalize_code_list(codes):
        if code not in _price_queues:
            _price_queues[code] = set()
        _price_queues[code].add(queue)


def unregister_queue(codes: list, queue) -> list:
    """SSE 연결 해제 시 호출 — queue 제거. 구독자 수가 0이 된 코드 목록 반환."""
    empty_codes: list = []
    for code in _normalize_code_list(codes):
        if code in _price_queues:
            _price_queues[code].discard(queue)
            if not _price_queues[code]:
                del _price_queues[code]
                empty_codes.append(code)
    return empty_codes


async def subscribe_codes(codes: list) -> None:
    """SSE 연결 시 호출 — 가용 WS managers에 codes를 분산 구독."""
    remaining = _normalize_code_list(codes)
    for mgr in _managers:
        if not remaining:
            break
        available = _MAX_SUBSCRIPTIONS - len(mgr._subscribed)
        if available > 0:
            chunk = remaining[:available]
            remaining = remaining[available:]
            await mgr.subscribe(chunk)
    if remaining:
        # 모든 WS 슬롯 소진 → REST 폴링으로 처리
        asyncio.get_event_loop().create_task(_start_rest_polling(remaining))


async def unsubscribe_codes(codes: list) -> None:
    """SSE 연결 해제 시 호출 — 구독자 없어진 codes를 WS managers에서 해제."""
    codes = _normalize_code_list(codes)
    for mgr in get_all_managers():
        targets = [c for c in codes if c in mgr._subscribed]
        if targets:
            await mgr.unsubscribe(targets)


# ── 전역 접근자 ───────────────────────────────────────────────────────────────
# KIS는 appkey당 WebSocket 연결을 1개만 허용합니다.
# 따라서 단일 KisWebSocketManager(Singleton)로 최대 40종목만 구독하고,
# 나머지 종목은 REST 폴링(_start_rest_polling)으로 처리합니다.

async def init_manager(initial_codes: list[str], is_mock: bool = False) -> None:
    """FastAPI startup_event에서 1회 호출.

    등록된 appkey 수만큼 WS 연결을 생성해 종목을 분산 구독합니다.
    - appkey 1개당 최대 _MAX_SUBSCRIPTIONS(40)개 WS 구독
    - appkey 3개 등록 시: 최대 120종목 WS, 나머지 REST 폴링
    - .env에 APP_KEY_2/APP_SECRET_2 등을 추가하면 자동으로 활용됩니다.
    """
    global _manager, _managers

    pairs = _APPKEY_PAIRS
    if not pairs:
        logger.warning("APP_KEY/APP_SECRET 미설정 — WS 연결 생략")
        await _start_rest_polling(initial_codes)
        return

    total_ws_slots = len(pairs) * _MAX_SUBSCRIPTIONS
    ws_codes_all   = initial_codes[:total_ws_slots]
    poll_codes     = initial_codes[total_ws_slots:]

    _managers = []
    for idx, (appkey, appsecret) in enumerate(pairs):
        chunk_start = idx * _MAX_SUBSCRIPTIONS
        chunk_end   = chunk_start + _MAX_SUBSCRIPTIONS
        chunk       = ws_codes_all[chunk_start:chunk_end]
        mgr = KisWebSocketManager(is_mock=is_mock, appkey=appkey, appsecret=appsecret)
        await mgr.start(chunk)
        _managers.append(mgr)
        logger.info(
            "KIS WS 연결 %d/%d 시작 (appkey: ...%s): %d개 종목",
            idx + 1, len(pairs), appkey[-6:], len(chunk),
        )

    # 하위 호환: _manager는 첫 번째 manager를 가리킴
    _manager = _managers[0] if _managers else None

    if poll_codes:
        logger.info("나머지 %d개 종목은 REST 폴링으로 처리", len(poll_codes))
        await _start_rest_polling(poll_codes)
    logger.info(
        "KIS WS 초기화 완료: appkey %d개 × 최대 %d종목 = WS %d종목, REST %d종목",
        len(pairs), _MAX_SUBSCRIPTIONS, len(ws_codes_all), len(poll_codes),
    )


async def add_poll_codes(codes: list[str]) -> None:
    """REST 폴링 대상 종목 추가 (WS 비활성 상태일 때 사용)."""
    _rest_poll_codes.update(codes)
    if not _ws_available:
        await _start_rest_polling([])


def get_manager() -> Optional[KisWebSocketManager]:
    """하위 호환용 — 첫 번째 manager 반환."""
    return _manager


def get_all_managers() -> list:
    """모든 WS manager 목록 반환 (shutdown 등에 사용)."""
    return _managers if _managers else ([_manager] if _manager else [])


def get_price_store() -> Dict[str, Dict]:
    """SSE 엔드포인트 등에서 최신 체결가 참조용."""
    return _price_store
