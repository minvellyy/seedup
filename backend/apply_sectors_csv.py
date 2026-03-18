"""induty_codes.csv로 instruments sector 일괄 업데이트 (DART API 재호출 없음)"""
import pandas as pd
import pymysql, os, time
from dotenv import load_dotenv
import sys
sys.path.insert(0, '.')
from update_sectors_dart import induty_to_sector

load_dotenv()

def get_conn():
    return pymysql.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )

df = pd.read_csv('induty_codes.csv', dtype=str)
df['new_sector'] = df['induty_code'].apply(induty_to_sector)

print(f"총 {len(df)}개 종목, 매핑 성공: {df['new_sector'].notna().sum()}개")

conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT stock_code, sector FROM instruments WHERE asset_type='STOCK'")
db_sectors = {r['stock_code']: r['sector'] for r in cur.fetchall()}
conn.close()

changes = []
for _, row in df.iterrows():
    new_sector = row['new_sector']
    if not new_sector:
        continue
    old_sector = db_sectors.get(row['ticker'], '')
    if new_sector != old_sector:
        changes.append((new_sector, row['ticker']))

print(f"변경 대상: {len(changes)}개")

# 한 건씩 retry 로직 포함하여 업데이트
updated = 0
for i, (new_sector, ticker) in enumerate(changes):
    for attempt in range(3):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE instruments SET sector=%s WHERE stock_code=%s",
                        (new_sector, ticker))
            conn.commit()
            conn.close()
            updated += 1
            break
        except pymysql.err.OperationalError as e:
            if e.args[0] == 1213:  # deadlock
                time.sleep(0.5)
                continue
            raise
    if (i+1) % 50 == 0:
        print(f"  {i+1}/{len(changes)} 완료...")

print(f"\n✅ 완료: {updated}개 업종 업데이트")
