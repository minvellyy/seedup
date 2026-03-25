"""
database_sqlite.py
-------------------
방화벽 밖 컴퓨터에서 seedup_export.db (SQLite3) 를 사용할 때
import 경로와 위치에 상관없이 사용할 수 있도록 경로 처리 개선.

사용 예:
    from database_sqlite import get_db, engine
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import os

from dotenv import load_dotenv

# .env 파일 탐색: 현재 폴더 → 상위 폴더 → ...
def find_dotenv(start_path: Path) -> Path | None:
    for p in [start_path] + list(start_path.parents):
        candidate = p / ".env"
        if candidate.exists():
            return candidate
    return None

_here = Path(__file__).resolve().parent
_dotenv = find_dotenv(_here)
if _dotenv:
    load_dotenv(dotenv_path=_dotenv)

# SQLITE_PATH 환경변수 → 없으면 같은 폴더의 seedup_export.db
_default = str(_here / "seedup_export.db")
SQLITE_PATH = os.getenv("SQLITE_PATH", _default)

DATABASE_URL = f"sqlite:///{SQLITE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # FastAPI 멀티스레드 대응
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
