from dotenv import load_dotenv
import os, pymysql, sys
sys.path.insert(0, '.')
load_dotenv()
conn = pymysql.connect(
    host=os.getenv('DB_HOST'), port=3306,
    user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'),
    db=os.getenv('DB_NAME'), charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)
cur = conn.cursor()

print("=== risk_type 분포 ===")
cur.execute("SELECT risk_type, market, asset_type, count(*) as cnt FROM universe_items WHERE active=1 GROUP BY risk_type, market, asset_type ORDER BY risk_type, market")
for r in cur.fetchall():
    print(r)

print("\n=== 샘플 종목 ===")
cur.execute("""
    SELECT u.risk_type, u.market, i.name, i.stock_code, i.last_price
    FROM universe_items u
    JOIN instruments i ON u.instrument_id=i.instrument_id
    WHERE u.active=1 AND u.asset_type='STOCK'
    LIMIT 8
""")
for r in cur.fetchall():
    print(r)

print("\n=== survey_questions ===")
cur.execute("SELECT id, code, question_text FROM survey_questions ORDER BY order_no")
for r in cur.fetchall():
    print(r)

print("\n=== user 1의 survey_answers ===")
cur.execute("SELECT sa.question_id, sq.code, sa.value_text, sa.value_number, sa.value_choice FROM survey_answers sa JOIN survey_questions sq ON sa.question_id=sq.id WHERE sa.user_id=1")
for r in cur.fetchall():
    print(r)

conn.close()
print("Done")
