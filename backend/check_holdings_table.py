"""
보유 주식 테이블 확인
"""
from dotenv import load_dotenv
import os
import pymysql

load_dotenv()

conn = pymysql.connect(
    host=os.getenv('DB_HOST'),
    port=3306,
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    db=os.getenv('DB_NAME'),
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)

cur = conn.cursor()

print("=" * 80)
print("보유 주식 관련 테이블 확인")
print("=" * 80)

# 모든 테이블 목록
print("\n1. 전체 테이블 목록:")
print("-" * 80)
cur.execute("SHOW TABLES")
tables = [row[list(row.keys())[0]] for row in cur.fetchall()]
for table in tables:
    print(f"  - {table}")

# user_holdings 테이블 존재 확인
holdings_table_exists = 'user_holdings' in tables

print(f"\n2. user_holdings 테이블 존재 여부: {holdings_table_exists}")
print("-" * 80)

if holdings_table_exists:
    print("\n✅ user_holdings 테이블이 존재합니다.")
    cur.execute("DESCRIBE user_holdings")
    print("\n테이블 구조:")
    for row in cur.fetchall():
        print(f"  {row}")
    
    cur.execute("SELECT COUNT(*) as count FROM user_holdings")
    count = cur.fetchone()['count']
    print(f"\n보유 데이터 개수: {count}개")
    
    if count > 0:
        cur.execute("SELECT * FROM user_holdings LIMIT 5")
        print("\n샘플 데이터 (최대 5개):")
        for row in cur.fetchall():
            print(f"  {row}")
else:
    print("\n❌ user_holdings 테이블이 존재하지 않습니다.")
    print("\n다음 테이블들을 확인합니다:")
    
    # holdings, stock_holdings 등 유사 테이블 확인
    similar_tables = [t for t in tables if 'hold' in t.lower() or 'stock' in t.lower() or 'portfolio' in t.lower()]
    if similar_tables:
        print("\n유사한 테이블:")
        for table in similar_tables:
            print(f"  - {table}")
    else:
        print("  (유사한 테이블 없음)")

conn.close()

print("\n" + "=" * 80)
print("확인 완료")
print("=" * 80)
