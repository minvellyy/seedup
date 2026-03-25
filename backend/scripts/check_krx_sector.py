"""KRX 업종 분류 확인 - instruments 테이블과 비교"""
from pykrx import stock
import pandas as pd

# 최근 거래일로 시도
for date in ['20260314', '20260313', '20260312', '20260311', '20260307']:
    try:
        df_kospi = stock.get_market_ticker_list(date, market='KOSPI')
        df_kosdaq = stock.get_market_ticker_list(date, market='KOSDAQ')
        print(f"기준일 {date} 사용")
        print(f"KOSPI 종목 수: {len(df_kospi)}, KOSDAQ 종목 수: {len(df_kosdaq)}")
        break
    except Exception as e:
        print(f"{date} 실패: {e}")
        continue

# 각 종목의 업종 정보 가져오기
rows = []
for ticker in list(df_kospi) + list(df_kosdaq):
    try:
        mkt = 'KOSPI' if ticker in df_kospi else 'KOSDAQ'
        info = stock.get_market_ticker_name(ticker)
        rows.append({'ticker': ticker, 'name': info, 'market': mkt})
    except:
        pass

# 업종 정보는 get_market_ohlcv_by_ticker 또는 개별 종목 업종으로
# pykrx의 업종 정보는 sector API로 가져오기
try:
    # 업종 분류 시도
    sector_df_kospi = stock.get_market_sector_classifications(date, market='KOSPI')
    print('\nKOSPI sector 컬럼:', sector_df_kospi.columns.tolist())
    print(sector_df_kospi.head(5))
except Exception as e:
    print(f'\nKOSPI sector 오류: {e}')

try:
    sector_df_kosdaq = stock.get_market_sector_classifications(date, market='KOSDAQ')  
    print('\nKOSDAQ sector 컬럼:', sector_df_kosdaq.columns.tolist())
    print(sector_df_kosdaq.head(5))
except Exception as e:
    print(f'\nKOSDAQ sector 오류: {e}')
