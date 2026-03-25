"""bucket 분류 결과 미리보기 (DB 수정 없음)"""
from __future__ import annotations
import os, math
from datetime import date, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import pymysql

load_dotenv()

CORE_FIXED = {
    "005930","000660","066570","009150","035420","035720",
    "373220","006400","051910","096770","003670",
    "207940","068270","128940",
    "005380","000270","012330",
    "005490",
    "105560","055550","086790","316140","000810","005830","032830",
    "012450","079550","047810","329180","010120","267260",
    "028260","090430","033780","003230","097950",
    "030200","017670","015760",
    "034730","003550","000150","402340","011170","003490","005940","006800",
}
VOL_CORE_THRESHOLD = 0.35

conn = pymysql.connect(
    host=os.getenv("DB_HOST","localhost"), port=int(os.getenv("DB_PORT",3306)),
    user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
    db=os.getenv("DB_NAME"), charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
)
cur = conn.cursor()
cur.execute("""
    SELECT u.id, u.instrument_id, u.market, i.stock_code, i.name
    FROM universe_items u JOIN instruments i ON u.instrument_id=i.instrument_id
    WHERE u.active=1 AND u.asset_type='STOCK'
""")
rows = cur.fetchall()
iids = [r["instrument_id"] for r in rows]
ph = ",".join(["%s"]*len(iids))
cutoff = (date.today()-timedelta(days=395)).isoformat()
cur.execute(f"SELECT instrument_id, close FROM market_prices WHERE instrument_id IN ({ph}) AND price_date>=%s AND close>0 ORDER BY instrument_id,price_date", iids+[cutoff])
price_hist = defaultdict(list)
for r in cur.fetchall(): price_hist[r["instrument_id"]].append(float(r["close"]))
conn.close()

def calc_vol(ps):
    if len(ps)<20: return None
    dr=[ps[i]/ps[i-1]-1 for i in range(1,len(ps))]
    n=len(dr); mn=sum(dr)/n
    return math.sqrt(sum((r-mn)**2 for r in dr)/max(n-1,1))*math.sqrt(252)

core_list, growth_list = [], []
for row in rows:
    sc, mkt = row["stock_code"], row["market"]
    vol = calc_vol(price_hist.get(row["instrument_id"],[]))
    if sc in CORE_FIXED:
        reason = "고정리스트"
        bucket = "CORE"
    elif mkt == "KOSPI":
        if vol is None or vol <= VOL_CORE_THRESHOLD:
            reason = f"KOSPI+변동성{vol*100:.0f}%" if vol else "KOSPI+데이터부족"
            bucket = "CORE"
        else:
            reason = f"KOSPI고변동성{vol*100:.0f}%"
            bucket = "GROWTH"
    else:
        if vol is not None and vol < 0.25:
            reason = f"KOSDAQ저변동{vol*100:.0f}%"
            bucket = "CORE"
        else:
            reason = f"KOSDAQ{'+변동성'+str(round((vol or 0)*100))+'%' if vol else ''}"
            bucket = "GROWTH"

    entry = f"  {sc}  {row['name']:<22} {mkt:<8} vol={str(round((vol or 0)*100))+'%':<6}  {reason}"
    if bucket=="CORE": core_list.append(entry)
    else: growth_list.append(entry)

print(f"=== CORE ({len(core_list)}개) ===")
for e in sorted(core_list): print(e)
print(f"\n=== GROWTH ({len(growth_list)}개, 상위 30개) ===")
for e in sorted(growth_list)[:30]: print(e)
