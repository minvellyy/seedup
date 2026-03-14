from fastapi import FastAPI, BackgroundTasks
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import importlib

# 우리가 만든 모듈들 임포트 (파일명이 숫자로 시작해 importlib 사용)
crawler_module = importlib.import_module("01_naver_report_crawler")
parser_module = importlib.import_module("02_report_information_extractor")
embedding_module = importlib.import_module("03_chroma_db_loader")

download_all_naver_reports = crawler_module.download_all_naver_reports
run_parser = parser_module.run_parser
run_embedding = embedding_module.run_embedding

def execute_etl_pipeline(days: int):
    """크롤링 -> 파싱 -> 임베딩을 순차적으로 실행하는 ETL 워크플로우"""
    print(f"\n=============================================")
    print(f"🚀 [ETL 파이프라인 시작] 기준: 최근 {days}일 ({datetime.now()})")
    print(f"=============================================")
    
    try:
        # 1. 크롤링 (기간 설정)
        download_all_naver_reports(base_dir="reports", days_to_fetch=days)
        
        # 2. PDF -> JSON 파싱
        run_parser()
        
        # 3. Chroma DB 임베딩 및 적재
        run_embedding()
        
        print(f"\n✅ [ETL 파이프라인 완료] DB 업데이트 성공 ({datetime.now()})")
    except Exception as e:
        print(f"\n❌ [ETL 파이프라인 실패]: {e}")

# FastAPI 수명주기(Lifespan) 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    
    # 자동화 로직: 매일 아침 08:00에 1일 치 신규 리포트만 업데이트
    scheduler.add_job(
        execute_etl_pipeline, 
        'cron', 
        hour=8, 
        minute=0, 
        args=[1], 
        id="daily_report_update"
    )
    scheduler.start()
    print("⏰ 일일 리포트 업데이트 스케줄러 시작 완료 (매일 08:00)")
    
    yield  # FastAPI 서버 동작 구간
    
    scheduler.shutdown()
    print("⏰ 스케줄러 종료")

# FastAPI 앱 생성
app = FastAPI(lifespan=lifespan, title="Portfolio Agent Backend")

@app.get("/")
def read_root():
    return {"status": "Backend Pipeline is running"}

@app.post("/api/init-db")
def initialize_database(background_tasks: BackgroundTasks):
    """
    초기 DB 구축용 엔드포인트. (최초 1회 실행)
    호출 시 백그라운드에서 30일 치 데이터를 수집하고 적재합니다.
    """
    background_tasks.add_task(execute_etl_pipeline, days=30)
    return {
        "message": "초기 30일치 데이터 수집 및 DB 임베딩 작업이 백그라운드에서 시작되었습니다."
    }