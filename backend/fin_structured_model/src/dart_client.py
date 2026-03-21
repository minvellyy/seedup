from __future__ import annotations
import requests
import pandas as pd
from .config import SETTINGS

FNLTT_CORE_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

REPRT = {"Q1":"11013", "H1":"11012", "Q3":"11014", "FY":"11011"}

def fetch_core_financials(corp_code: str, year: int, reprt_code: str) -> pd.DataFrame:
    if not SETTINGS.dart_api_key:
        raise ValueError("DART_API_KEY is missing in .env")

    def _call(fs_div_value: str):
        params = {
            "crtfc_key": SETTINGS.dart_api_key,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": reprt_code,
            "fs_div": fs_div_value,   # 'CFS' or 'OFS'
        }
        r = requests.get(FNLTT_CORE_URL, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    # 1) 연결 우선
    data = _call("CFS")
    if data.get("status") == "000":
        df = pd.DataFrame(data.get("list", []))
        df["corp_code"] = corp_code
        df["bsns_year"] = year
        df["reprt_code"] = reprt_code
        df["fs_div"] = "CFS"
        return df

    # 2) 연결이 데이터 없음이면 개별로 폴백
    if data.get("status") == "013":
        data2 = _call("OFS")
        if data2.get("status") == "000":
            df = pd.DataFrame(data2.get("list", []))
            df["corp_code"] = corp_code
            df["bsns_year"] = year
            df["reprt_code"] = reprt_code
            df["fs_div"] = "OFS"
            return df

        return pd.DataFrame([{
            "status": data2.get("status"),
            "message": data2.get("message"),
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": reprt_code,
            "fs_div": "OFS",
        }])

    # 3) 그 외 에러(파라미터/제한 등)
    return pd.DataFrame([{
        "status": data.get("status"),
        "message": data.get("message"),
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": reprt_code,
        "fs_div": "CFS",
    }])