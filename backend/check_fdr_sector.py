"""FinanceDataReader로 KRX 업종 데이터 확인"""
import FinanceDataReader as fdr
import pandas as pd

# KRX 전체 종목 리스트 (업종 포함)
print("=== KOSPI 종목 리스트 ===")
try:
    kospi = fdr.StockListing('KOSPI')
    print("컬럼:", kospi.columns.tolist())
    print(kospi.head(3).to_string())
    print(f"\n총 {len(kospi)}개")
except Exception as e:
    print(f"KOSPI 실패: {e}")

print("\n=== KOSDAQ 종목 리스트 ===")
try:
    kosdaq = fdr.StockListing('KOSDAQ')
    print("컬럼:", kosdaq.columns.tolist())
    print(kosdaq.head(3).to_string())
    print(f"\n총 {len(kosdaq)}개")
    # 376300 확인
    row = kosdaq[kosdaq['Code'] == '376300']
    if not row.empty:
        print(f"\n376300 디어유: {row.to_dict('records')}")
    # 업종 분포
    if 'Sector' in kosdaq.columns:
        print("\n업종 분포:")
        print(kosdaq['Sector'].value_counts().head(20))
    elif 'Industry' in kosdaq.columns:
        print("\nIndustry 분포:")
        print(kosdaq['Industry'].value_counts().head(20))
except Exception as e:
    print(f"KOSDAQ 실패: {e}")

print("\n=== KRX 전체 ===")
try:
    krx = fdr.StockListing('KRX')
    print("컬럼:", krx.columns.tolist())
    print(krx.head(3).to_string())
except Exception as e:
    print(f"KRX 실패: {e}")
