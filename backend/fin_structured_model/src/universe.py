from __future__ import annotations
import zipfile
import requests
import pandas as pd
from io import BytesIO
from pathlib import Path
from .config import SETTINGS
from .utils import ensure_dir

DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

def download_corp_codes(save_path: Path) -> Path:
    """
    Download DART corpCode.xml (zipped). Extract corpCode.xml.
    """
    if not SETTINGS.dart_api_key:
        raise ValueError("DART_API_KEY is missing in .env")

    params = {"crtfc_key": SETTINGS.dart_api_key}
    r = requests.get(DART_CORP_CODE_URL, params=params, timeout=60)
    r.raise_for_status()

    z = zipfile.ZipFile(BytesIO(r.content))
    members = z.namelist()
    # Usually includes "CORPCODE.xml" or similar
    xml_name = [m for m in members if m.lower().endswith(".xml")][0]
    out_dir = ensure_dir(save_path.parent)
    xml_path = out_dir / "corpCode.xml"
    with z.open(xml_name) as f:
        xml_path.write_bytes(f.read())
    return xml_path

def parse_corp_codes(xml_path: Path) -> pd.DataFrame:
    """
    Parse corpCode.xml into DataFrame with columns:
    corp_code, corp_name, stock_code, modify_date
    """
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_path.read_bytes())
    rows = []
    for item in root.findall("list"):
        rows.append({
            "corp_code": (item.findtext("corp_code") or "").strip(),
            "corp_name": (item.findtext("corp_name") or "").strip(),
            "stock_code": (item.findtext("stock_code") or "").strip(),
            "modify_date": (item.findtext("modify_date") or "").strip(),
        })
    df = pd.DataFrame(rows)
    # Listed firms have 6-digit stock_code
    df = df[df["stock_code"].str.len() == 6].copy()
    df.rename(columns={"stock_code": "ticker"}, inplace=True)
    return df

def load_universe_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)

def save_universe_parquet(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_parquet(path, index=False)