"""induty_code 분포 분석 및 KRX 업종명 매핑"""
import pandas as pd
import pymysql, os
from dotenv import load_dotenv
load_dotenv()

df = pd.read_csv('induty_codes.csv', dtype=str)
print('induty_code 분포:')
print(df['induty_code'].value_counts().head(30))
col = 'induty_code'
null_cnt = df[col].isna().sum()
print(f'\nnull: {null_cnt}개')

conn = pymysql.connect(host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT',3306)),
    user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), db=os.getenv('DB_NAME'),
    charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()
cur.execute("SELECT stock_code, name, sector FROM instruments WHERE sector='IT'")
it_stocks = {r['stock_code']: r['name'] for r in cur.fetchall()}
conn.close()

it_df = df[df['ticker'].isin(it_stocks.keys())]
print(f'\nWICS IT 종목 {len(it_df)}개의 induty_code:')
print(it_df[['ticker','name','induty_code']].to_string())
