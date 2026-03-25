"""user_holdings 테이블 구조 확인"""
import pymysql
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent / '.env')

conn = pymysql.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    db=os.getenv("DB_NAME"),
    charset='utf8mb4'
)

cursor = conn.cursor()
cursor.execute("DESCRIBE user_holdings")
columns = cursor.fetchall()

print("=" * 80)
print("user_holdings 테이블 구조")
print("=" * 80)
for col in columns:
    print(f"{col[0]:20s} | {col[1]:20s} | NULL: {col[2]:3s} | Key: {col[3]:3s}")

print("\n" + "=" * 80)
print("purchase_date 컬럼 상세:")
for col in columns:
    if col[0] == 'purchase_date':
        print(f"  Type: {col[1]}")
        print(f"  NULL 허용: {col[2]}")
        print(f"  Default: {col[4]}")
        if col[2] == 'NO':
            print("\n  ⚠️  purchase_date는 NOT NULL입니다. NULL 허용으로 변경해야 합니다.")
        else:
            print("\n  ✅ purchase_date는 NULL 허용입니다.")

cursor.close()
conn.close()
