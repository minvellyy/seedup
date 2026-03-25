import os
import sys

# ── Windows curl_cffi KeyboardInterrupt 팝업 억제 ────────────────────────────
# curl_cffi 0.7.0 미만에서 Ctrl+C 종료 시 CFFI 콜백 안으로 KeyboardInterrupt가
# 전달되어 Windows 에러 다이얼로그가 뜨는 버그. unraisablehook으로 억제한다.
if sys.platform == "win32":
    _orig_unraisablehook = sys.unraisablehook

    def _suppress_curl_cffi_interrupt(unraisable):
        if unraisable.exc_type is KeyboardInterrupt:
            obj_str = str(getattr(unraisable, "object", "") or "")
            if "curl" in obj_str.lower() or "buffer_callback" in obj_str.lower():
                return
        _orig_unraisablehook(unraisable)

    sys.unraisablehook = _suppress_curl_cffi_interrupt

# ── CrewAI 종료 노이즈 근본 억제 ─────────────────────────────────────────────
# 1) CrewAI EventBus mismatch 경고를 SILENT로 설정 (Rich console 직접 출력 방지)
try:
    from crewai.events.event_context import EventContextConfig, MismatchBehavior
    import crewai.events.event_context as _ec_module
    _ec_module._default_config = EventContextConfig(
        mismatch_behavior=MismatchBehavior.SILENT,
        empty_pop_behavior=MismatchBehavior.SILENT,
    )
except Exception:
    pass

# 2) CrewAI handle_unknown_error 패치 — 서버 종료 관련 에러는 출력하지 않음
_SHUTDOWN_ERROR_MARKERS = (
    "cannot schedule new futures after shutdown",
    "shutdown",
    "Event loop is closed",
    "cancelled",
)
try:
    import crewai.utilities.agent_utils as _agent_utils
    _orig_handle_unknown_error = _agent_utils.handle_unknown_error

    def _patched_handle_unknown_error(printer, exception, verbose=True):
        err_msg = str(exception).lower()
        if any(m in err_msg for m in _SHUTDOWN_ERROR_MARKERS):
            return  # 서버 종료 관련 에러는 무시
        _orig_handle_unknown_error(printer, exception, verbose)

    _agent_utils.handle_unknown_error = _patched_handle_unknown_error
except Exception:
    pass

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import engine, get_db, SessionLocal
from typing import Optional, Dict, Any
import asyncio
import hashlib
import json
import logging
import sys
import uvicorn
from datetime import datetime

# ── Windows ProactorEventLoop ConnectionResetError 노이즈 억제 ────────────────
if sys.platform == "win32":
    import asyncio
    _orig_call_exception_handler = asyncio.BaseEventLoop.call_exception_handler

    def _silent_exception_handler(self, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return  # WinError 10054 노이즈 무시
        _orig_call_exception_handler(self, context)

    asyncio.BaseEventLoop.call_exception_handler = _silent_exception_handler
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("main")

# ── 서버 종료 시 CrewAI 관련 노이즈 로그 필터 ────────────────────────────────
_SHUTDOWN_NOISE = (
    "cannot schedule new futures after shutdown",
    "Event pairing mismatch",
)

class _ShutdownNoiseFilter(logging.Filter):
    """서버 종료(Ctrl+C) 중 CrewAI/asyncio에서 발생하는 예상된 에러 로그를 억제한다."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(noise in msg for noise in _SHUTDOWN_NOISE)

# root 로거와 CrewAI 관련 로거에 필터 적용
for _logger_name in ("root", "", "crewai", "CrewAIEventsBus"):
    logging.getLogger(_logger_name).addFilter(_ShutdownNoiseFilter())

from routers import survey, dashboard, recommendations
from routers.instruments import router as instruments_router
from models import Base, SurveyQuestion
os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")

# 종목/포트폴리오 추천 라우터 (core 패키지 없이도 서버 기동 가능)
try:
    from routers.stocks import router as stocks_router
    from routers.portfolio import router as portfolio_router
    _RECOMMEND_ROUTERS_AVAILABLE = True
except Exception as _e:
    print(f"[WARNING] 추천 라우터 로드 실패: {_e}")
    _RECOMMEND_ROUTERS_AVAILABLE = False

# CrewAI 분석 라우터 (crewai 패키지 없이도 서버 기동 가능)
try:
    from routers.analysis import router as analysis_router
    _ANALYSIS_ROUTER_AVAILABLE = True
except Exception as _e:
    print(f"[WARNING] 분석 라우터 로드 실패: {_e}")
    _ANALYSIS_ROUTER_AVAILABLE = False

# 뉴스 RAG 라우터 (chromadb / news_model 패키지 없이도 서버 기동 가능)
try:
    from routers.news import router as news_router
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _NEWS_ROUTER_AVAILABLE = True
except Exception as _e:
    print(f"[WARNING] 뉴스 라우터 로드 실패: {_e}")
    _NEWS_ROUTER_AVAILABLE = False

# ESG 분석 라우터 (esg_model / rag_worker 없이도 서버 기동 가능)
try:
    from routers.esg import router as esg_router
    _ESG_ROUTER_AVAILABLE = True
except Exception as _e:
    print(f"[WARNING] ESG 라우터 로드 실패: {_e}")
    _ESG_ROUTER_AVAILABLE = False

# 증권사 리포트 RAG 라우터 (reports_model / rag_worker 없이도 서버 기동 가능)
try:
    from routers.reports import router as reports_router
    _REPORTS_ROUTER_AVAILABLE = True
except Exception as _e:
    print(f"[WARNING] 리포트 라우터 로드 실패: {_e}")
    _REPORTS_ROUTER_AVAILABLE = False

from routers.chatbot import router as chatbot_router
from routers.terms import router as terms_router

# Pydantic 모델 정의
class SignupRequest(BaseModel):
    email: str
    password: str
    username: str
    name: Optional[str] = ""
    phone: Optional[str] = ""
    dob: Optional[str] = ""

class LoginRequest(BaseModel):
    username: str
    password: str

class SurveyRequest(BaseModel):
    user_id: int
    survey_data: Dict[str, Any]

# 유틸리티 함수
def hash_password(password):
    """비밀번호 해싱 - SHA256 사용"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_survey_questions():
    """설문 질문 초기화 - Raw SQL 사용"""
    db = SessionLocal()
    try:
        # 이미 데이터가 있는지 확인
        result = db.execute(text('SELECT COUNT(*) FROM survey_questions'))
        count = result.fetchone()[0]
        if count > 0:
            print(f"Survey questions already exist ({count} questions), skipping initialization")
            return
        
        print("Initializing survey questions with Raw SQL...")
        
        # Raw SQL로 직접 삽입
        questions_sql = [
            ("INVEST_GOAL", "투자 목적은 무엇인가요?", "TEXT", None, 1),
            ("TARGET_HORIZON", "목표 시점은 언제인가요?", "TEXT", None, 2),
            ("TARGET_AMOUNT", "목표 금액은 어느 정도인가요?", "NUMBER", None, 3),
            ("CONTRIBUTION_TYPE", "선호하는 투자 방식을 선택해 주세요", "SINGLE_CHOICE", '["LUMP_SUM", "DCA"]', 4),
            ("LUMP_SUM_AMOUNT", "일시금 금액", "NUMBER", None, 5),
            ("MONTHLY_AMOUNT", "월 투자 가능 금액", "NUMBER", None, 6),
            ("MAX_HOLDINGS", "최대 몇 개의 종목을 보유하고 싶으신가요?", "NUMBER", None, 7),
            ("DIVIDEND_PREF", "배당 선호 정도는?", "SINGLE_CHOICE", '["HIGH", "MID", "LOW"]', 8),
            ("ACCOUNT_TYPE", "계좌 유형", "TEXT", None, 9)
        ]
        
        for code, question_text, answer_type, options_json, order_no in questions_sql:
            db.execute(
                text('''
                    INSERT INTO survey_questions (code, question_text, answer_type, options_json, order_no, created_at, updated_at)
                    VALUES (:code, :question_text, :answer_type, :options_json, :order_no, NOW(), NOW())
                '''),
                {
                    'code': code,
                    'question_text': question_text,
                    'answer_type': answer_type,
                    'options_json': options_json,
                    'order_no': order_no
                }
            )
        
        db.commit()
        print(f"Survey questions initialized successfully! Total: {len(questions_sql)} questions")
    except Exception as e:
        print(f"Error initializing survey questions: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

app = FastAPI(title="SeedUp API Server")

# ── DB 실시간 가격 동기화 백그라운드 태스크 ─────────────────────────────────

# WebSocket price_store → DB 동기화 간격 (초, 기본 60초)
_DB_SYNC_INTERVAL = int(os.getenv("DB_PRICE_SYNC_INTERVAL", "60"))
# REST API 전체 종목 갱신 간격 (초, 기본 5분)
_DB_FULL_SYNC_INTERVAL = int(os.getenv("DB_FULL_PRICE_SYNC_INTERVAL", str(5 * 60)))


async def _db_price_sync_loop() -> None:
    """WebSocket _price_store → instruments.last_price 주기적 벌크 업데이트 (60초 주기)."""
    from kis_ws_client import get_price_store

    while True:
        await asyncio.sleep(_DB_SYNC_INTERVAL)
        try:
            store = get_price_store()
            if not store:
                continue

            today = datetime.now().strftime("%Y-%m-%d")
            updated = 0
            for code, price_data in store.items():
                for attempt in range(3):
                    db = SessionLocal()
                    try:
                        db.execute(
                            text(
                                """
                                UPDATE instruments
                                   SET last_price      = :price,
                                       last_price_date = :date
                                 WHERE stock_code = :code
                                """
                            ),
                            {
                                "price": price_data["current_price"],
                                "date":  today,
                                "code":  code,
                            },
                        )
                        db.commit()
                        updated += 1
                        break
                    except Exception as e:
                        db.rollback()
                        from pymysql.err import OperationalError as PyMySQLOperationalError
                        if attempt < 2 and hasattr(e, 'orig') and isinstance(e.orig, PyMySQLOperationalError) and e.orig.args[0] == 1213:
                            await asyncio.sleep(0.1 * (attempt + 1))
                        else:
                            logger.error("DB 가격 동기화 오류: %s", e)
                            break
                    finally:
                        db.close()
            logger.info("DB 가격 동기화 완료 (WS): %d개 종목", updated)
        except Exception as e:
            logger.error("DB 가격 동기화 루프 오류: %s", e)


async def _db_full_price_sync(skip_ws_codes: set = None) -> int:
    """KIS REST API로 모든 ACTIVE 종목의 현재가를 조회해 DB를 갱신한다.

    skip_ws_codes: WebSocket으로 이미 수신 중인 종목코드 집합 (선택)
    Returns: 업데이트된 종목 수
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from kis_client import get_current_price

    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT stock_code FROM instruments WHERE asset_type IN ('STOCK', 'ETF') AND price_status = 'ACTIVE'")
        ).fetchall()
    finally:
        db.close()

    all_codes = [r[0] for r in rows if r[0]]
    # WebSocket 수신 중인 종목은 건너뜀 (이미 60초 루프에서 갱신)
    if skip_ws_codes:
        target_codes = [c for c in all_codes if c not in skip_ws_codes]
    else:
        target_codes = all_codes

    if not target_codes:
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    results: dict = {}

    # KIS REST API rate limit 대응: 초당 최대 ~10건 (100ms 간격)
    # 1423종목 기준 약 2~3분 소요 (백그라운드 작업이므로 허용)
    _RATE_LIMIT_DELAY = float(os.getenv("KIS_REST_RATE_DELAY", "0.1"))  # 초
    _BATCH_SIZE = int(os.getenv("KIS_REST_BATCH_SIZE", "3"))            # 동시 요청 수
    _BATCH_PAUSE = float(os.getenv("KIS_REST_BATCH_PAUSE", "0.35"))     # 배치 간 대기(초)

    logger.info("DB 전체 가격 갱신 시작: %d개 종목 (배치=%d, 간격=%.2fs)", len(target_codes), _BATCH_SIZE, _BATCH_PAUSE)

    with ThreadPoolExecutor(max_workers=_BATCH_SIZE) as pool:
        for batch_start in range(0, len(target_codes), _BATCH_SIZE):
            if not target_codes:
                break
            batch = target_codes[batch_start: batch_start + _BATCH_SIZE]
            future_map = {pool.submit(get_current_price, code): code for code in batch}
            for fut in as_completed(future_map):
                code = future_map[fut]
                try:
                    data = fut.result()
                    results[code] = data["current_price"]
                except Exception as e:
                    logger.debug("REST 가격 조회 실패 [%s]: %s", code, e)
            # 배치 간 대기: KIS 초당 요청 제한(EGW00201) 방지
            await asyncio.sleep(_BATCH_PAUSE)

    if not results:
        return 0

    db = SessionLocal()
    try:
        for code, price in results.items():
            db.execute(
                text(
                    """
                    UPDATE instruments
                       SET last_price      = :price,
                           last_price_date = :date
                     WHERE stock_code = :code
                    """
                ),
                {"price": price, "date": today, "code": code},
            )
        db.commit()
        logger.info("DB 전체 가격 갱신 완료 (REST): %d / %d개 종목", len(results), len(target_codes))
        return len(results)
    except Exception as e:
        db.rollback()
        logger.error("DB 전체 가격 갱신 오류: %s", e)
        return 0
    finally:
        db.close()


async def _db_full_price_sync_loop() -> None:
    """REST API로 WS 미구독 종목(STOCK+ETF)을 주기적으로 갱신 (기본 3시간 주기).
    
    NOTE: 시작 직후 즉시 실행을 비활성화했습니다. KIS API 호출량이 많아 500 오류가 발생할 수 있습니다.
    필요시 주기적 갱신만 사용하거나, 더 긴 간격으로 설정하세요.
    """
    from kis_ws_client import get_price_store

    # 서버 시작 직후 즉시 실행하지 않음 (KIS API 500 오류 방지)
    logger.info("DB 전체 가격 갱신: 첫 실행은 %d초 후에 시작됩니다.", _DB_FULL_SYNC_INTERVAL)

    while True:
        await asyncio.sleep(_DB_FULL_SYNC_INTERVAL)
        try:
            ws_codes = set(get_price_store().keys())
            await _db_full_price_sync(skip_ws_codes=ws_codes)
        except Exception as e:
            logger.error("DB 전체 가격 갱신 루프 오류: %s", e)


async def _discover_new_etfs_loop() -> None:
    """pykrx로 KRX 신규 상장 ETF를 주기적으로 발견해 DB에 등록.\n\n    - 시작 시 30초 후 즉시 1회 실행
    - 이후 매일 1회 (기본 24시간, DB_ETF_DISCOVER_INTERVAL 환경변수로 조정)
    """
    _DISCOVER_INTERVAL = int(os.getenv("DB_ETF_DISCOVER_INTERVAL", str(24 * 3600)))

    await asyncio.sleep(30)
    while True:
        try:
            logger.info("ETF 목록 조회 시작 (네이버 금융)...")
            loop = asyncio.get_event_loop()
            from kis_client import get_etf_list_from_krx
            krx_etfs = await loop.run_in_executor(None, get_etf_list_from_krx)

            if not krx_etfs:
                logger.debug("KRX ETF 목록 비어 있음 — 다음 주기에 재실행")
            else:
                db = SessionLocal()
                try:
                    existing = {r[0] for r in db.execute(
                        text("SELECT stock_code FROM instruments WHERE asset_type = 'ETF'")
                    ).fetchall()}

                    new_etfs = [e for e in krx_etfs if e["stock_code"] not in existing]
                    today = datetime.now().strftime("%Y-%m-%d")

                    added = 0
                    for etf in new_etfs:
                        try:
                            # KIS REST로 현재가 조회
                            from kis_client import get_current_price
                            price_data = await loop.run_in_executor(None, get_current_price, etf["stock_code"])
                            price = price_data["current_price"]
                        except Exception:
                            price = 0.0

                        db.execute(
                            text("""
                                INSERT INTO instruments
                                    (stock_code, name, exchange, asset_type, price_status,
                                     last_price, last_price_date)
                                VALUES
                                    (:code, :name, :exchange, 'ETF', 'ACTIVE',
                                     :price, :date)
                            """),
                            {
                                "code":     etf["stock_code"],
                                "name":     etf["name"] or etf["stock_code"],
                                "exchange": etf["exchange"],
                                "price":    price,
                                "date":     today,
                            },
                        )
                        added += 1
                        await asyncio.sleep(0.1)  # KIS rate limit 방지

                    db.commit()
                    if added:
                        logger.info("신규 ETF %d개 DB 등록 완료", added)
                    else:
                        logger.info("KRX ETF 확인 완료 — 신규 상장 없음 (DB: %d개)", len(existing))
                except Exception as e:
                    db.rollback()
                    logger.error("ETF 발견 오류: %s", e)
                finally:
                    db.close()
        except Exception as e:
            logger.error("ETF 발견 루프 오류: %s", e)

        await asyncio.sleep(_DISCOVER_INTERVAL)


# 앱 시작 시 설문 질문 초기화
@app.on_event("startup")
async def startup_event():
    print("="*60)
    print("Starting up application...")
    print("="*60)
    try:
        # 테이블 생성
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully!")
        
        # 설문 질문 초기화
        print("Initializing survey questions...")
        init_survey_questions()

        # KIS WebSocket 실시간 스트리밍 초기화
        print("Initializing KIS WebSocket manager...")
        try:
            from kis_ws_client import init_manager
            import os

            # DB instruments 테이블에서 ACTIVE 종목코드 전체 로드
            initial_codes: list = []
            try:
                db_session = SessionLocal()
                rows = db_session.execute(
                    text("""
                        SELECT i.stock_code
                        FROM instruments i
                        LEFT JOIN (
                            SELECT stock_code, COUNT(*) AS hold_count
                            FROM user_holdings
                            GROUP BY stock_code
                        ) uh ON uh.stock_code = i.stock_code
                        WHERE i.asset_type = 'STOCK' AND i.price_status = 'ACTIVE'
                        ORDER BY COALESCE(uh.hold_count, 0) DESC
                    """)
                ).fetchall()
                db_session.close()
                initial_codes = [r[0] for r in rows if r[0]]
                print(f"DB에서 {len(initial_codes)}개 ACTIVE 종목 로드 완료")
            except Exception as db_err:
                print(f"DB 종목 로드 실패 (빈 목록으로 시작): {db_err}")

            is_mock = os.getenv("KIS_MOCK", "false").lower() == "true"
            # KIS 서버가 이전 세션을 정리할 시간 확보 (ALREADY IN USE 방지)
            _ws_startup_delay = int(os.getenv("KIS_WS_STARTUP_DELAY", "20"))
            if _ws_startup_delay > 0:
                print(f"KIS WebSocket 연결 전 {_ws_startup_delay}초 대기 (이전 세션 정리)...")
                await asyncio.sleep(_ws_startup_delay)
            await init_manager(initial_codes, is_mock=is_mock)
            print(f"KIS WebSocket manager initialized! ({len(initial_codes)}개 종목 구독 등록)")
        except Exception as ws_err:
            print(f"KIS WebSocket init skipped: {ws_err}")

        # RAG Worker 통합 스케줄러 (뉴스 08:00 / 리포트 ETL 08:05)
        if _NEWS_ROUTER_AVAILABLE or _REPORTS_ROUTER_AVAILABLE:
            try:
                import threading
                _rag_scheduler = BackgroundScheduler()

                # 뉴스 daily_batch — 매일 08:00
                if _NEWS_ROUTER_AVAILABLE:
                    from rag_worker.scheduler import run_news_daily_batch
                    _rag_scheduler.add_job(
                        lambda: threading.Thread(target=run_news_daily_batch, daemon=True).start(),
                        trigger=CronTrigger(hour=8, minute=0),
                        id="daily_news_update",
                        replace_existing=True,
                    )
                    print("✅ 뉴스 스케줄러 등록 (매일 08:00)")

                    # 서버가 08:00 이후에 켜진 경우 당일치 즉시 실행 (임시 비활성화)
                    # from datetime import datetime as _dt
                    # _now = _dt.now()
                    # if _now.hour >= 8:
                    #     print(f"⚡ 서버 시작 시각 {_now:%H:%M} — 당일 뉴스 배치 즉시 실행")
                    #     threading.Thread(target=run_news_daily_batch, daemon=True).start()

                # 리포트 ETL — 매일 08:05
                if _REPORTS_ROUTER_AVAILABLE:
                    from rag_worker.scheduler import run_reports_etl
                    _rag_scheduler.add_job(
                        lambda: threading.Thread(target=run_reports_etl, daemon=True).start(),
                        trigger=CronTrigger(hour=8, minute=5),
                        id="daily_reports_etl",
                        replace_existing=True,
                    )
                    print("✅ 리포트 ETL 스케줄러 등록 (매일 08:05)")

                    # 서버가 08:05 이후에 켜진 경우 당일치 즉시 실행 (임시 비활성화)
                    # from datetime import datetime as _dt
                    # _now = _dt.now()
                    # if _now.hour > 8 or (_now.hour == 8 and _now.minute >= 5):
                    #     print(f"⚡ 서버 시작 시각 {_now:%H:%M} — 당일 리포트 ETL 즉시 실행")
                    #     threading.Thread(target=run_reports_etl, daemon=True).start()

                _rag_scheduler.start()
                app.state.rag_scheduler = _rag_scheduler
                print("✅ RAG Worker 스케줄러 시작")
            except Exception as sched_err:
                print(f"RAG Worker 스케줄러 시작 실패: {sched_err}")
        # DB 가격 동기화 백그라운드 태스크 시작
        asyncio.create_task(_db_price_sync_loop())          # WS 40종목: 60초 주기
        asyncio.create_task(_db_full_price_sync_loop())     # REST 전체: 3시간 주기 + 시작 즉시 1회
        asyncio.create_task(_discover_new_etfs_loop())      # 신규 ETF 발견: 24시간 주기 + 시작 30초 후
        print("DB 가격 동기화 백그라운드 태스크 시작 완료")

        print("Application startup complete!")
    except Exception as e:
        print(f"Error during startup: {str(e)}")
        import traceback
        traceback.print_exc()
    print("="*60)


@app.on_event("shutdown")
async def shutdown_event():
    print("="*60)
    print("Shutting down application...")
    # RAG 스케줄러 정리
    if hasattr(app.state, "rag_scheduler"):
        try:
            app.state.rag_scheduler.shutdown(wait=False)
            print("RAG 스케줄러 종료 완료")
        except Exception as e:
            print(f"RAG 스케줄러 종료 오류: {e}")
    # KIS WebSocket 정리
    try:
        from kis_ws_client import get_manager
        mgr = get_manager()
        if mgr:
            await mgr.close()
            print("KIS WebSocket 종료 완료")
    except Exception:
        pass
    print("Shutdown complete.")
    print("="*60)


# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/admin/sync-prices")
async def sync_prices_now():
    """instruments 테이블 가격을 즉시 동기화 (수동 트리거).

    - WS price_store에 있는 종목: 즉시 DB 반영
    - 나머지 전체 종목: KIS REST API로 일괄 조회 후 DB 반영
    백그라운드로 실행되며 즉시 응답을 반환합니다.
    """
    from kis_ws_client import get_price_store
    store = get_price_store()
    today = datetime.now().strftime("%Y-%m-%d")

    # WS 종목 즉시 반영
    ws_updated = 0
    if store:
        db = SessionLocal()
        try:
            for code, price_data in store.items():
                db.execute(
                    text(
                        "UPDATE instruments SET last_price = :price, last_price_date = :date WHERE stock_code = :code"
                    ),
                    {"price": price_data["current_price"], "date": today, "code": code},
                )
                ws_updated += 1
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            db.close()

    # REST 전체 종목 백그라운드로 실행
    ws_codes = set(store.keys())
    asyncio.create_task(_db_full_price_sync(skip_ws_codes=ws_codes))

    return {
        "message": "WS 종목 즉시 반영, REST 전체 종목 갱신은 백그라운드 실행 중",
        "ws_updated": ws_updated,
        "rest_target": "나머지 ACTIVE 종목 (백그라운드)",
        "date": today,
    }

@app.get('/api/check_username')
async def check_username(username: str = Query(..., description="Username to check"), db: Session = Depends(get_db)):
    """username(ID) 중복체크"""
    username = username.strip()
    if not username:
        raise HTTPException(status_code=400, detail={'success': False, 'message': 'username is required'})

    try:
        result = db.execute(text('SELECT id FROM users WHERE username = :username'), {'username': username})
        user = result.fetchone()
        return {'success': True, 'exists': bool(user)}
    except Exception as e:
        print(f"Error in check_username: {str(e)}")
        raise HTTPException(status_code=500, detail={'success': False, 'message': 'error checking username'})

@app.post('/api/signup')
async def signup(data: SignupRequest, db: Session = Depends(get_db)):
    """회원가입 API"""
    try:
        print(f"[SIGNUP] 회원가입 요청 받음: {data.email}, {data.username}")
        
        email = data.email.strip()
        password = data.password
        username = data.username.strip()
        name = data.name.strip() if data.name else ""
        phone = data.phone.strip() if data.phone else ""
        dob = data.dob.strip() if data.dob else ""

        print(f"[SIGNUP] 데이터 정리 완료 - email: {email}, username: {username}")

        # 이메일 검증
        if '@' not in email:
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'message': '유효한 이메일을 입력해주세요.'}
            )

        # 비밀번호 길이 검증
        if len(password) < 6:
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'message': '비밀번호는 6자 이상이어야 합니다.'}
            )

        # username 검증
        if not username:
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'message': 'ID를 입력해주세요.'}
            )

        print(f"[SIGNUP] 유효성 검증 통과")

        # 비밀번호 해싱
        hashed_password = hash_password(password)
        print(f"[SIGNUP] 비밀번호 해싱 완료")

        try:
            # 이미 존재하는 username 또는 email 확인
            result = db.execute(
                text('SELECT id FROM users WHERE username = :username OR email = :email'),
                {'username': username, 'email': email}
            )
            existing = result.fetchone()
            if existing:
                print(f"[SIGNUP] 중복 사용자 발견 - username: {username}, email: {email}")
                raise HTTPException(
                    status_code=409,
                    detail={'success': False, 'message': '이미 사용 중인 이메일 또는 ID 입니다.'}
                )

            print(f"[SIGNUP] DB에 사용자 삽입 시도")
            db.execute(
                text('''
                    INSERT INTO users (email, username, name, phone, birth_date, password)
                    VALUES (:email, :username, :name, :phone, :dob, :password)
                '''),
                {'email': email, 'username': username, 'name': name, 'phone': phone, 'dob': dob, 'password': hashed_password}
            )
            db.commit()

            # MySQL에서 마지막 삽입된 ID 가져오기
            result = db.execute(text('SELECT LAST_INSERT_ID()'))
            user_id = result.fetchone()[0]
            
            print(f"[SIGNUP] 회원가입 성공 - user_id: {user_id}")

            return {
                'success': True,
                'message': '회원가입이 완료되었습니다.',
                'user_id': user_id,
                'email': email,
                'username': username,
                'name': name
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            print(f"[SIGNUP] DB Error: {str(e)}")
            raise HTTPException(
                status_code=409,
                detail={'success': False, 'message': '이미 가입된 이메일 또는 ID입니다.'}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SIGNUP ERROR] {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': f'회원가입 중 오류가 발생했습니다: {str(e)}'}
        )

@app.post('/api/login')
async def login(data: LoginRequest, db: Session = Depends(get_db)):
    """로그인 API"""
    try:
        username = data.username.strip()
        password = data.password

        # username으로 사용자 검색
        result = db.execute(
            text('SELECT id, email, username, password, investment_type, name FROM users WHERE username = :username'),
            {'username': username}
        )
        user = result.fetchone()

        if user:
            # 비밀번호 검증 - SHA256 해시 비교
            password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            if password_hash == user[3]:  # user[3]은 password 컬럼
                print(f"로그인 성공 - user_id: {user[0]}, username: {user[2]}")
                return {
                    'success': True,
                    'message': '로그인되었습니다.',
                    'user_id': user[0],
                    'email': user[1],
                    'username': user[2],
                    'investment_type': user[4],  # 투자성향 추가
                    'name': user[5] if len(user) > 5 else None  # 이름 추가
                }
        
        # 사용자가 없거나 비밀번호가 일치하지 않는 경우
        raise HTTPException(
            status_code=401,
            detail={'success': False, 'message': 'ID 또는 비밀번호가 일치하지 않습니다.'}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in login: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': '로그인 중 오류가 발생했습니다.'}
        )

@app.get('/api/users/{user_id}')
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """사용자 정보 조회 API"""
    try:
        result = db.execute(
            text('SELECT id, email, username, name, phone, created_at FROM users WHERE id = :user_id'),
            {'user_id': user_id}
        )
        user = result.fetchone()

        if user:
            # 일시투자금(LUMP_SUM_AMOUNT) 설문 답변 조회
            lump_sum_result = db.execute(
                text('''
                    SELECT sa.value_number FROM survey_answers sa
                    JOIN survey_questions sq ON sa.question_id = sq.id
                    WHERE sa.user_id = :user_id AND sq.code = 'LUMP_SUM_AMOUNT'
                '''),
                {'user_id': user_id}
            )
            lump_sum_row = lump_sum_result.fetchone()
            lump_sum_amount = lump_sum_row[0] if lump_sum_row else None

            user_data = {
                'id': user[0],
                'email': user[1],
                'username': user[2],
                'name': user[3],
                'phone': user[4],
                'created_at': str(user[5]),
                'lump_sum_amount': lump_sum_amount,
            }
            print(f"[GET_USER] user_id: {user_id}, phone: {user[4]}, data: {user_data}")
            return {
                'success': True,
                'user': user_data
            }
        else:
            raise HTTPException(
                status_code=404,
                detail={'success': False, 'message': '사용자를 찾을 수 없습니다.'}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_user: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': '사용자 조회 중 오류가 발생했습니다.'}
        )

@app.put('/api/users/{user_id}')
async def update_user(user_id: int, data: dict, db: Session = Depends(get_db)):
    """사용자 정보 수정 API"""
    try:
        print(f"[UPDATE_USER] user_id: {user_id}, data: {data}")
        
        # 업데이트할 필드 준비
        update_fields = []
        params = {'user_id': user_id}
        
        if 'name' in data:
            update_fields.append('name = :name')
            params['name'] = data['name']
            print(f"[UPDATE_USER] name 업데이트: {data['name']}")
        
        if 'phone' in data:
            update_fields.append('phone = :phone')
            params['phone'] = data['phone']
            print(f"[UPDATE_USER] phone 업데이트: {data['phone']}")
        
        if 'email' in data:
            update_fields.append('email = :email')
            params['email'] = data['email']
            print(f"[UPDATE_USER] email 업데이트: {data['email']}")
        
        # 비밀번호 변경 처리
        if 'newPassword' in data and data['newPassword']:
            print(f"[UPDATE_USER] 비밀번호 변경 요청")
            import hashlib
            # SHA256 해시 사용 (로그인과 동일한 방식)
            password_hash = hashlib.sha256(data['newPassword'].encode('utf-8')).hexdigest()
            update_fields.append('password = :password')
            params['password'] = password_hash
        
        # lump_sum_amount는 survey_answers 테이블에 별도 저장
        lump_sum_amount = data.get('lump_sum_amount')

        if not update_fields and lump_sum_amount is None:
            print(f"[UPDATE_USER] 업데이트할 필드 없음")
            return {'success': True, 'message': '업데이트할 정보가 없습니다.'}

        if update_fields:
            # SQL 쿼리 실행
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = :user_id"
            print(f"[UPDATE_USER] SQL: {query}")
            print(f"[UPDATE_USER] Params: {params}")
            db.execute(text(query), params)

        if lump_sum_amount is not None:
            # LUMP_SUM_AMOUNT 질문 ID 조회
            q_result = db.execute(
                text("SELECT id FROM survey_questions WHERE code = 'LUMP_SUM_AMOUNT'")
            )
            q_row = q_result.fetchone()
            if q_row:
                question_id = q_row[0]
                existing = db.execute(
                    text('SELECT id FROM survey_answers WHERE user_id = :user_id AND question_id = :question_id'),
                    {'user_id': user_id, 'question_id': question_id}
                ).fetchone()
                if existing:
                    db.execute(
                        text('UPDATE survey_answers SET value_number = :val, updated_at = NOW() WHERE user_id = :user_id AND question_id = :question_id'),
                        {'val': float(lump_sum_amount), 'user_id': user_id, 'question_id': question_id}
                    )
                else:
                    db.execute(
                        text('INSERT INTO survey_answers (user_id, question_id, value_number, created_at, updated_at) VALUES (:user_id, :question_id, :val, NOW(), NOW())'),
                        {'user_id': user_id, 'question_id': question_id, 'val': float(lump_sum_amount)}
                    )
                print(f"[UPDATE_USER] lump_sum_amount 업데이트: {lump_sum_amount}")

        db.commit()

        print(f"[UPDATE_USER] 성공!")

        return {
            'success': True,
            'message': '사용자 정보가 성공적으로 수정되었습니다.'
        }
    
    except Exception as e:
        db.rollback()
        print(f"[UPDATE_USER] Error: {str(e)}")
        print(f"[UPDATE_USER] Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': f'사용자 정보 수정 중 오류: {str(e)}'}
        )

@app.post('/api/survey')
async def save_survey(data: dict, db: Session = Depends(get_db)):
    """설문조사 답변 저장 API"""
    try:
        print("="*50)
        print(f"[DEBUG] Received raw payload: {data}")
        print(f"[DEBUG] Payload type: {type(data)}")
        user_id = data.get("user_id")
        answers = data.get("answers", [])
        
        print(f"[DEBUG] Extracted user_id: {user_id} (type: {type(user_id)})")
        print(f"[DEBUG] Extracted answers: {answers}")
        print("="*50)

        if not user_id or not answers:
            print(f"[ERROR] Validation failed - user_id: {user_id}, answers length: {len(answers)}")
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "user_id와 answers는 필수입니다."}
            )

        # user_id 검증: users 테이블에 존재하는지 확인
        result = db.execute(text('SELECT id FROM users WHERE id = :user_id'), {'user_id': user_id})
        user_exists = result.fetchone()
        
        if not user_exists:
            print(f"[ERROR] User validation failed - user_id {user_id} does not exist")
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": f"유효하지 않은 사용자 ID입니다: {user_id}"}
            )
        
        print(f"[DEBUG] User validation passed - user_id {user_id} exists")

        try:
            for idx, answer in enumerate(answers):
                print(f"\n[DEBUG] Processing answer {idx + 1}/{len(answers)}: {answer}")
                question_id = answer.get("question_id")
                question_code = answer.get("question_code")
                value_text = answer.get("value_text")
                value_number = answer.get("value_number")
                value_choice = answer.get("value_choice")
                
                print(f"[DEBUG] question_code: {question_code}, question_id: {question_id}")
                print(f"[DEBUG] value_text: {value_text}, value_number: {value_number}, value_choice: {value_choice}")

                # question_id 또는 question_code로 질문 찾기
                if question_code:
                    print(f"[DEBUG] Searching by question_code: {question_code}")
                    result = db.execute(
                        text('SELECT id, answer_type, options_json FROM survey_questions WHERE code = :code'),
                        {'code': question_code}
                    )
                elif question_id:
                    print(f"[DEBUG] Searching by question_id: {question_id}")
                    result = db.execute(
                        text('SELECT id, answer_type, options_json FROM survey_questions WHERE id = :question_id'),
                        {'question_id': question_id}
                    )
                else:
                    print(f"[ERROR] No question_id or question_code provided")
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "message": "question_id 또는 question_code가 필요합니다."}
                    )
                
                question_row = result.fetchone()
                print(f"[DEBUG] Question found: {question_row}")

                if not question_row:
                    print(f"[ERROR] Question not found for code/id: {question_code or question_id}")
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "message": f"Invalid question_id/code: {question_id or question_code}"}
                    )

                q_id, answer_type, options_json = question_row
                print(f"[DEBUG] Question details - id: {q_id}, type: {answer_type}, options: {options_json}")

                q_id, answer_type, options_json = question_row
                print(f"[DEBUG] Question details - id: {q_id}, type: {answer_type}, options: {options_json}")

                # 타입 검증 및 값 매핑
                print(f"[DEBUG] Validating answer type: {answer_type}")
                if answer_type == "TEXT":
                    if value_text is None or value_text == "":
                        print(f"[ERROR] TEXT type question missing value_text")
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"TEXT 타입의 질문에 value_text가 필요합니다. (question_id: {q_id})"}
                        )
                    print(f"[DEBUG] TEXT validation passed")
                elif answer_type == "NUMBER":
                    if value_number is None:
                        print(f"[ERROR] NUMBER type question missing value_number")
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"NUMBER 타입의 질문에 value_number가 필요합니다. (question_id: {q_id})"}
                        )
                    print(f"[DEBUG] NUMBER validation passed, value: {value_number}")
                elif answer_type == "SINGLE_CHOICE":
                    if value_choice is None or value_choice == "":
                        print(f"[ERROR] SINGLE_CHOICE type question missing value_choice")
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"SINGLE_CHOICE 타입의 질문에 value_choice가 필요합니다. (question_id: {q_id})"}
                        )
                    # options_json 파싱
                    try:
                        valid_options = json.loads(options_json) if options_json else []
                    except json.JSONDecodeError:
                        valid_options = []
                    
                    print(f"[DEBUG] Checking if '{value_choice}' in {valid_options}")
                    if value_choice not in valid_options:
                        print(f"[ERROR] Invalid choice value")
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"SINGLE_CHOICE 타입의 질문에 유효하지 않은 값입니다. (question_id: {q_id}, value: {value_choice}, valid_options: {valid_options})"}
                        )
                    print(f"[DEBUG] SINGLE_CHOICE validation passed")
                else:
                    print(f"[ERROR] Unknown answer type: {answer_type}")
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "message": f"알 수 없는 answer_type: {answer_type}"}
                    )

                # Insert new row for each answer
                print(f"[DEBUG] Inserting answer - user_id: {user_id}, question_id: {q_id}, value_text: {value_text}, value_number: {value_number}, value_choice: {value_choice}")
                db.execute(
                    text('''
                        INSERT INTO survey_answers (user_id, question_id, value_text, value_number, value_choice, created_at, updated_at)
                        VALUES (:user_id, :question_id, :value_text, :value_number, :value_choice, NOW(), NOW())
                    '''),
                    {
                        'user_id': user_id,
                        'question_id': q_id,
                        'value_text': value_text,
                        'value_number': value_number,
                        'value_choice': value_choice
                    }
                )

            db.commit()
            print(f"Survey answers saved for user_id: {user_id}")

            return {
                "success": True,
                "message": "설문조사 답변이 저장되었습니다."
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            print(f"Error saving survey answers: {str(e)}")
            raise

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error in save_survey: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "설문조사 저장 중 오류가 발생했습니다."}
        )

@app.post('/api/logout')
async def logout():
    """로그아웃 API"""
    # 클라이언트 측에서 localStorage를 클리어하므로 서버에서는 로그만 남김
    print(f"[LOGOUT] 로그아웃 요청")
    return {
        'success': True,
        'message': '로그아웃되었습니다.'
    }

@app.post('/api/init-survey-questions')
async def manual_init_survey_questions(db: Session = Depends(get_db)):
    """설문 질문 수동 초기화 API - Raw SQL 사용"""
    try:
        # 기존 데이터 확인
        result = db.execute(text('SELECT COUNT(*) FROM survey_questions'))
        count = result.fetchone()[0]
        if count > 0:
            return {
                'success': True,
                'message': '설문 질문이 이미 존재합니다.',
                'count': count
            }
        
        # Raw SQL로 설문 질문 생성
        questions_sql = [
            ("INVEST_GOAL", "투자 목적은 무엇인가요?", "TEXT", None, 1),
            ("TARGET_HORIZON", "목표 시점은 언제인가요?", "TEXT", None, 2),
            ("TARGET_AMOUNT", "목표 금액은 어느 정도인가요?", "NUMBER", None, 3),
            ("CONTRIBUTION_TYPE", "선호하는 투자 방식을 선택해 주세요", "SINGLE_CHOICE", '["LUMP_SUM", "DCA"]', 4),
            ("LUMP_SUM_AMOUNT", "일시금 금액", "NUMBER", None, 5),
            ("MONTHLY_AMOUNT", "월 투자 가능 금액", "NUMBER", None, 6),
            ("MAX_HOLDINGS", "최대 몇 개의 종목을 보유하고 싶으신가요?", "NUMBER", None, 7),
            ("DIVIDEND_PREF", "배당 선호 정도는?", "SINGLE_CHOICE", '["HIGH", "MID", "LOW"]', 8),
            ("ACCOUNT_TYPE", "계좌 유형", "TEXT", None, 9)
        ]
        
        for code, question_text, answer_type, options_json, order_no in questions_sql:
            db.execute(
                text('''
                    INSERT INTO survey_questions (code, question_text, answer_type, options_json, order_no, created_at, updated_at)
                    VALUES (:code, :question_text, :answer_type, :options_json, :order_no, NOW(), NOW())
                '''),
                {
                    'code': code,
                    'question_text': question_text,
                    'answer_type': answer_type,
                    'options_json': options_json,
                    'order_no': order_no
                }
            )
        
        db.commit()
        
        return {
            'success': True,
            'message': '설문 질문이 성공적으로 생성되었습니다.',
            'count': len(questions_sql)
        }
    except Exception as e:
        db.rollback()
        print(f"Error initializing survey questions: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': f'설문 질문 초기화 중 오류가 발생했습니다: {str(e)}'}
        )

@app.get('/api/survey-questions')
async def get_survey_questions(db: Session = Depends(get_db)):
    """설문 질문 목록 조회 API - Raw SQL 사용"""
    try:
        result = db.execute(text('SELECT id, code, question_text, answer_type, options_json, order_no FROM survey_questions ORDER BY order_no'))
        questions = result.fetchall()
        
        return {
            'success': True,
            'count': len(questions),
            'questions': [
                {
                    'id': q[0],
                    'code': q[1],
                    'question_text': q[2],
                    'answer_type': q[3],
                    'options_json': q[4],
                    'order_no': q[5]
                }
                for q in questions
            ]
        }
    except Exception as e:
        print(f"Error getting survey questions: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': f'설문 질문 조회 중 오류가 발생했습니다: {str(e)}'}
        )

class InvestmentTypeRequest(BaseModel):
    user_id: int
    investment_type: str

@app.post('/api/users/{user_id}/investment-type')
async def update_investment_type(user_id: int, data: InvestmentTypeRequest, db: Session = Depends(get_db)):
    """사용자 투자성향 저장 API"""
    try:
        # user_id 검증
        result = db.execute(
            text('SELECT id FROM users WHERE id = :user_id'),
            {'user_id': user_id}
        )
        user = result.fetchone()
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail={'success': False, 'message': '사용자를 찾을 수 없습니다.'}
            )
        
        # 투자성향 업데이트
        db.execute(
            text('UPDATE users SET investment_type = :investment_type WHERE id = :user_id'),
            {'investment_type': data.investment_type, 'user_id': user_id}
        )
        db.commit()
        
        print(f"투자성향 저장 성공 - user_id: {user_id}, investment_type: {data.investment_type}")
        return {
            'success': True,
            'message': '투자성향이 저장되었습니다.',
            'investment_type': data.investment_type
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating investment type: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': '투자성향 저장 중 오류가 발생했습니다.'}
        )

@app.get('/api/health')
async def health():
    """헬스 체크 API"""
    return {
        'status': 'healthy',
        'message': 'SeedUp API Server is running'
    }

from routers.stream import router as stream_router
from routers.holdings import router as holdings_router
from routers.inquiry import router as inquiry_router

# Include routers
app.include_router(survey.router, prefix="/survey", tags=["Survey"])
app.include_router(dashboard.router)
app.include_router(recommendations.router)
app.include_router(instruments_router)   # /api/instruments/stocks, /etfs
app.include_router(stream_router)        # /api/stream/prices
app.include_router(holdings_router, prefix="/api")  # /api/holdings
app.include_router(inquiry_router)       # /api/inquiries

app.include_router(chatbot_router)  # 챗봇 라우터 등록
app.include_router(terms_router, prefix="/api/v1")  # 전문용어 추출 라우터

# 종목/포트폴리오 추천 라우터 등록 (/api/v1/stocks, /api/v1/portfolio)
if _RECOMMEND_ROUTERS_AVAILABLE:
    app.include_router(stocks_router, prefix="/api/v1")
    app.include_router(portfolio_router, prefix="/api/v1")

if _ANALYSIS_ROUTER_AVAILABLE:
    app.include_router(analysis_router, prefix="/api/v1")
if _ESG_ROUTER_AVAILABLE:
    app.include_router(esg_router, prefix="/api/v1")
if _REPORTS_ROUTER_AVAILABLE:
    app.include_router(reports_router, prefix="/api/v1")

if _NEWS_ROUTER_AVAILABLE:
    app.include_router(news_router, prefix="/api/v1")


@app.on_event("shutdown")
async def shutdown_event():
    for attr in ("rag_scheduler", "news_scheduler"):
        scheduler = getattr(app.state, attr, None)
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)
    print("🛑 RAG Worker 스케줄러 종료")


if __name__ == '__main__':
    # FastAPI 앱 실행
    import uvicorn
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info", timeout_graceful_shutdown=3)
