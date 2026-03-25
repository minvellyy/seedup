import pymysql, os
from dotenv import load_dotenv
load_dotenv()
conn = pymysql.connect(
    host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT', 3306)),
    user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), db=os.getenv('DB_NAME'),
    charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
)
cur = conn.cursor()

# sector 분포
cur.execute("SELECT sector, COUNT(*) as cnt FROM instruments WHERE asset_type='STOCK' GROUP BY sector ORDER BY cnt DESC LIMIT 25")
print("[ instruments sector 분포 ]")
for r in cur.fetchall():
    print(f"  {str(r['sector']):<30} {r['cnt']:>4}개")

# 376300
cur.execute("SELECT stock_code, name, sector, exchange FROM instruments WHERE stock_code='376300'")
row = cur.fetchone()
print('\n376300:', row)

# sector null/empty 개수
cur.execute("SELECT COUNT(*) as cnt FROM instruments WHERE asset_type='STOCK' AND (sector IS NULL OR sector='')")
r = cur.fetchone()
print(f"\nsector 없는 종목: {r['cnt']}개")

# 전체 STOCK 종목 수
cur.execute("SELECT COUNT(*) as cnt FROM instruments WHERE asset_type='STOCK'")
r = cur.fetchone()
print(f"전체 STOCK 종목 수: {r['cnt']}개")

conn.close()
