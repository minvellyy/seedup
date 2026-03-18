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

# Check if 037170 exists in instruments
cur.execute("SELECT * FROM instruments WHERE stock_code = '037170'")
row = cur.fetchone()
print('instruments 037170:', row)

# Check if in universe_items
cur.execute("""
    SELECT u.* FROM universe_items u
    JOIN instruments i ON u.instrument_id = i.instrument_id
    WHERE i.stock_code = '037170'
""")
row2 = cur.fetchone()
print('universe_items 037170:', row2)

# Show total count of instruments and universe_items
cur.execute("SELECT COUNT(*) as cnt FROM instruments")
print('total instruments:', cur.fetchone()['cnt'])

cur.execute("SELECT COUNT(*) as cnt FROM universe_items WHERE active=1")
print('total active universe_items:', cur.fetchone()['cnt'])

conn.close()
