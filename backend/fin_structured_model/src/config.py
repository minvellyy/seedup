import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    dart_api_key: str = os.getenv("DART_API_KEY", "")
    fs_div: str = os.getenv("FS_DIV", "CONSOL").upper()
    data_dir: str = os.getenv("DATA_DIR", "./data")

SETTINGS = Settings()