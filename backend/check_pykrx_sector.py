"""pykrx로 업종 데이터 가져오기 - 다양한 방법 시도"""
from pykrx import stock
import pandas as pd

# 최근 거래일 찾기
from datetime import datetime, timedelta
base = datetime(2026, 3, 14)
for i in range(14):
    dt = base - timedelta(days=i)
    d = dt.strftime('%Y%m%d')
    try:
        tickers = stock.get_market_ticker_list(d, market='KOSDAQ')
        if len(tickers) > 0:
            print(f"거래일 확인: {d}, KOSDAQ 종목수: {len(tickers)}")
            valid_date = d
            valid_tickers = tickers
            break
    except:
        pass
else:
    print("유효한 거래일 없음")
    exit()

# 개별 종목 업종 확인
# pykrx stock.get_market_ticker_name 은 이름만
# KRX 업종 코드는 get_market_ticker_list의 sector 파라미터
print("\n--- 업종별 종목 조회 ---")
try:
    # KRX 업종 목록 (KOSDAQ)
    df = stock.get_market_sector_classifications(valid_date, market='KOSDAQ')
    print("컬럼:", df.columns.tolist())
    print(df.head())
except Exception as e:
    print(f"sector_classifications 실패: {e}")

# 대신 개별 종목 기업 개요로 업종 확인
print("\n--- 개별 종목 업종 확인 (sample) ---")
sample_codes = ['376300', '005930', '000660']
for code in sample_codes:
    try:
        name = stock.get_market_ticker_name(code)
        print(f"{code} ({name}): ", end='')
        # 업종 정보
        try:
            sector = stock.get_market_ticker_list(valid_date, market='KOSDAQ')
            if code in sector:
                print(f"KOSDAQ 포함")
        except:
            pass
        # 시가총액 정보에 업종 있나?
        info = stock.get_market_cap(valid_date, valid_date, code)
        print(f"시가총액: {info}")
    except Exception as e:
        print(f"오류: {e}")
