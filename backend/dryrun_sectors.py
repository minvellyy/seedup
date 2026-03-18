"""induty_codes.csv로 매핑 결과 미리 확인 (dry-run)"""
import pandas as pd
import sys
sys.path.insert(0, '.')
from update_sectors_dart import induty_to_sector

df = pd.read_csv('induty_codes.csv', dtype=str)
df['new_sector'] = df['induty_code'].apply(induty_to_sector)

print(f"총 {len(df)}개 종목")
print(f"매핑 성공: {df['new_sector'].notna().sum()}개")
print(f"매핑 실패(None): {df['new_sector'].isna().sum()}개\n")

print("=== new_sector 분포 ===")
print(df['new_sector'].value_counts().to_string())

print("\n=== 매핑 실패 종목 ===")
failed = df[df['new_sector'].isna()]
print(failed[['ticker','name','induty_code']].to_string())

# 기존 WICS IT 종목이 어떻게 바뀌는지
import pymysql, os
from dotenv import load_dotenv
load_dotenv()
conn = pymysql.connect(host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT',3306)),
    user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), db=os.getenv('DB_NAME'),
    charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()
cur.execute("SELECT stock_code, sector FROM instruments WHERE asset_type='STOCK'")
db_sectors = {r['stock_code']: r['sector'] for r in cur.fetchall()}
conn.close()

df['old_sector'] = df['ticker'].map(db_sectors)
changed = df[df['old_sector'] != df['new_sector']].dropna(subset=['new_sector'])
print(f"\n=== 변경될 종목 ({len(changed)}개) ===")
print(changed[['ticker','name','induty_code','old_sector','new_sector']].to_string())
