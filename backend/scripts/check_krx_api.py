"""KRX REST API로 업종 분류 확인"""
import requests
import json

# KRX 업종 분류 API (data.krx.co.kr)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "http://data.krx.co.kr/",
}

# KOSDAQ 전체 종목 + 업종 조회
payload = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT03901",
    "mktId": "KSQ",  # KOSDAQ
    "trdDd": "20260314",
    "money": "1",
    "csvxls_isNo": "false",
}

url = "http://data.krx.co.kr/comm/bld/mdcstat/resource/MDCSTAT03901.cmd"
try:
    r = requests.post(url, data=payload, headers=headers, timeout=15)
    data = r.json()
    print("KRX KOSDAQ 업종 조회 성공")
    print("키:", list(data.keys()))
    if 'OutBlock_1' in data:
        items = data['OutBlock_1']
        print(f"종목 수: {len(items)}")
        print("첫 3개:", items[:3])
except Exception as e:
    print(f"실패: {e}")

# 다른 엔드포인트 시도
print("\n--- 방법 2: 종목현황 API ---")
payload2 = {
    "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
    "mktId": "KSQ",
    "trdDd": "20260314",
    "csvxls_isNo": "false",
}
url2 = "http://data.krx.co.kr/comm/bld/mdcstat/resource/MDCSTAT01901.cmd"
try:
    r2 = requests.post(url2, data=payload2, headers=headers, timeout=15)
    data2 = r2.json()
    print("키:", list(data2.keys()))
    if 'OutBlock_1' in data2:
        items2 = data2['OutBlock_1']
        print(f"종목 수: {len(items2)}")
        print("첫 1개:", items2[0] if items2 else '없음')
except Exception as e:
    print(f"실패: {e}")
