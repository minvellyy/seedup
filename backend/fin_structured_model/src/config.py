import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# fin_structured_model/ 안에 .env가 없으면 상위 backend/.env를 사용
_local_env = Path(__file__).resolve().parent.parent / ".env"
_backend_env = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_local_env if _local_env.exists() else _backend_env)

@dataclass(frozen=True)
class Settings:
    dart_api_key: str = os.getenv("DART_API_KEY", "")
    fs_div: str = os.getenv("FS_DIV", "CONSOL").upper()
    data_dir: str = os.getenv("DATA_DIR", "./data")

SETTINGS = Settings()