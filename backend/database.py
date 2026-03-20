from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from pathlib import Path
import os

# 1 .env 로드 (backend/.env 절대 경로)
load_dotenv(dotenv_path=Path(__file__).parent / '.env')

# 2. DATABASE_URL 생성
DATABASE_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@" \
               f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# 3. 엔진 생성
engine = create_engine(
    DATABASE_URL,
    echo=False,  # True로 설정하면 모든 SQL 쿼리가 출력됩니다
    pool_pre_ping=True,
    pool_size=20,       # 동시 연결 수 (기본 5 → 20)
    max_overflow=40,    # 초과 허용 연결 수 (기본 10 → 40)
    pool_recycle=3600,  # 1시간마다 연결 재생성 (MySQL 8시간 유휴 후 끊김 방지)
    pool_timeout=30,    # 연결 못 얻으면 30초 후 TimeoutError (무한 대기 방지)
)
# 4. 세션 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
