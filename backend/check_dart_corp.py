"""DART corp_code로 업종명 조회 테스트"""
import requests, os, pandas as pd
from dotenv import load_dotenv
load_dotenv()

DART_KEY = os.getenv('DART_API_KEY')
print(f"DART_KEY: {'설정됨' if DART_KEY else '없음'}")

# universe parquet에서 corp_code 가져오기
u = pd.read_parquet('fin_structured_model/data/processed/universe_k200_k150_fixed.parquet')
print("universe 컬럼:", u.columns.tolist())
print("샘플:")
print(u.head(3).to_string())

# 삼성전자 corp_code 확인
samsung = u[u['ticker'].astype(str).str.zfill(6) == '005930']
if not samsung.empty:
    corp_code = str(samsung.iloc[0].get('corp_code', '')).zfill(8)
    print(f"\n삼성전자 corp_code: {corp_code}")
    
    r = requests.get('https://opendart.fss.or.kr/api/company.json',
        params={'crtfc_key': DART_KEY, 'corp_code': corp_code}, timeout=10)
    print(f"상태코드: {r.status_code}")
    data = r.json()
    print(f"DART status: {data.get('status')}, message: {data.get('message')}")
    if data.get('status') == '000':
        for k in ['stock_name', 'induty_code', 'corp_cls', 'est_dt']:
            print(f"  {k}: {data.get(k)}")
