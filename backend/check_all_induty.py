"""DART induty_code 분포 확인 - 전체 universe"""
import requests, os, pandas as pd, time
from dotenv import load_dotenv
from collections import Counter
load_dotenv()

DART_KEY = os.getenv('DART_API_KEY')

u = pd.read_parquet('fin_structured_model/data/processed/universe_k200_k150_fixed.parquet')
u['ticker'] = u['ticker'].astype(str).str.zfill(6)
u['corp_code'] = u['corp_code'].astype(str).str.zfill(8)

results = []
print(f"총 {len(u)}개 종목 조회 중...")
for i, row in u.iterrows():
    try:
        r = requests.get('https://opendart.fss.or.kr/api/company.json',
            params={'crtfc_key': DART_KEY, 'corp_code': row['corp_code']}, timeout=10)
        d = r.json()
        if d.get('status') == '000':
            results.append({
                'ticker': row['ticker'],
                'name': row['name'],
                'exchange': row['exchange'],
                'induty_code': d.get('induty_code'),
                'corp_cls': d.get('corp_cls'),
            })
        else:
            results.append({'ticker': row['ticker'], 'name': row['name'],
                            'exchange': row['exchange'], 'induty_code': None, 'corp_cls': None})
        time.sleep(0.05)
    except Exception as e:
        results.append({'ticker': row['ticker'], 'name': row['name'],
                        'exchange': row['exchange'], 'induty_code': None, 'corp_cls': None})

    if (i+1) % 50 == 0:
        print(f"  {i+1}/{len(u)} 완료...")

df = pd.DataFrame(results)
print(f"\n=== induty_code 분포 ({len(df)}개) ===")
print(df['induty_code'].value_counts().head(30))
print(f"\n조회 실패: {df['induty_code'].isna().sum()}개")

# 샘플 - IT 종목 확인
df.to_csv('induty_codes.csv', index=False, encoding='utf-8-sig')
print("\ninduty_codes.csv 저장 완료")
