import os
import requests
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("DART_API_KEY")

url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
corp = "00126380"  # 삼성전자
base = {
    "crtfc_key": key,
    "corp_code": corp,
    "bsns_year": "2023",
    "reprt_code": "11011",  # FY
}

def call(params):
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

for fs in ["CFS", "OFS", None]:
    p = base.copy()
    if fs is not None:
        p["fs_div"] = fs
    j = call(p)
    print(f"fs_div={fs} status={j.get('status')} msg={j.get('message')} list_len={len(j.get('list', []))}")