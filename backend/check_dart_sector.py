"""DART API로 KRX 실제 업종명 조회 테스트"""
import requests, os
from dotenv import load_dotenv
load_dotenv()

DART_KEY = os.getenv('DART_API_KEY')

# 삼성전자(005930) DART 기업코드
# corp_code는 DART 고유 코드, 종목코드(stock_code)와 다름
# company.json은 corp_code로 조회
# 하지만 stock_code로도 조회 가능: ?stock_code=005930

r = requests.get('https://opendart.fss.or.kr/api/company.json',
    params={'crtfc_key': DART_KEY, 'stock_code': '005930'}, timeout=10)
data = r.json()
print("삼성전자 DART 응답 키:", list(data.keys()))
print("삼성전자:", {k: data.get(k) for k in ['stock_name','induty_code','est_dt','corp_cls','adres']})

print()
# 디어유(376300)
r2 = requests.get('https://opendart.fss.or.kr/api/company.json',
    params={'crtfc_key': DART_KEY, 'stock_code': '376300'}, timeout=10)
data2 = r2.json()
print("디어유 DART 응답:", {k: data2.get(k) for k in ['stock_name','induty_code','est_dt','corp_cls']})

print()
# 기계/장비 종목 샘플 - 실제 테스트용으로 KOSDAQ 기계/장비 기업 하나
# 현재 DB에서 "IT"로 분류된 종목 가져오기
import pymysql
conn = pymysql.connect(host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT',3306)),
    user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), db=os.getenv('DB_NAME'),
    charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()
cur.execute("SELECT stock_code, name, sector FROM instruments WHERE sector='IT' LIMIT 5")
it_stocks = cur.fetchall()
conn.close()

print("DB의 IT 종목 샘플:")
for s in it_stocks:
    r3 = requests.get('https://opendart.fss.or.kr/api/company.json',
        params={'crtfc_key': DART_KEY, 'stock_code': s['stock_code']}, timeout=10)
    d3 = r3.json()
    status = d3.get('status')
    induty = d3.get('induty_code', 'N/A')
    name_dart = d3.get('stock_name', 'N/A')
    print(f"  {s['stock_code']} {s['name']}: DART 업종코드={induty}, status={status}")
