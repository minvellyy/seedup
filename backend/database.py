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
    pool_pre_ping=True
)
# 4. 세션 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
