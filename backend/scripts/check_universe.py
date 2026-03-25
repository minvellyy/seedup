import os
from dotenv import load_dotenv
load_dotenv()
import pymysql

conn = pymysql.connect(
    host=os.getenv('DB_HOST','localhost'),
    port=int(os.getenv('DB_PORT',3306)),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    db=os.getenv('DB_NAME'),
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)
cur = conn.cursor()

cur.execute("SELECT DISTINCT bucket FROM universe_items WHERE bucket IS NOT NULL")
print("buckets:", [r["bucket"] for r in cur.fetchall()])

cur.execute("SELECT DISTINCT risk_type FROM universe_items WHERE risk_type IS NOT NULL")
print("risk_types:", [r["risk_type"] for r in cur.fetchall()])

cur.execute("SELECT DISTINCT market FROM universe_items WHERE market IS NOT NULL")
print("markets:", [r["market"] for r in cur.fetchall()])

cur.execute("SELECT COUNT(*) as c FROM universe_items WHERE active=1")
print("active count:", cur.fetchone()["c"])

cur.execute("SELECT COUNT(*) as c FROM universe_items WHERE active=1 AND asset_type='STOCK'")
print("active STOCK count:", cur.fetchone()["c"])

# Sample a few
cur.execute("SELECT i.stock_code, i.name, u.market, u.bucket, u.risk_type, i.last_price FROM universe_items u JOIN instruments i ON u.instrument_id=i.instrument_id WHERE u.active=1 AND u.asset_type='STOCK' ORDER BY i.last_price DESC LIMIT 20")
for r in cur.fetchall():
    print(r)

conn.close()
