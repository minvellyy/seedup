#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KIS API 연결 및 기능 테스트 스크립트
"""

import sys
import traceback
from pathlib import Path

# 현재 디렉토리를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent))

def test_kis_import():
    """KIS 클라이언트 모듈 임포트 테스트"""
    print("=" * 60)
    print("🔍 KIS 클라이언트 모듈 임포트 테스트")
    print("=" * 60)
    
    try:
        import kis_client
        print("✅ kis_client 모듈 임포트 성공")
        return True
    except Exception as e:
        print(f"❌ kis_client 모듈 임포트 실패: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

def test_environment_variables():
    """환경변수 설정 확인"""
    print("\n" + "=" * 60)
    print("🔧 환경변수 설정 확인")
    print("=" * 60)
    
    import os
    from dotenv import load_dotenv
    
    # .env 파일 로드
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ .env 파일 로드: {env_file}")
    else:
        print(f"⚠️  .env 파일이 없습니다: {env_file}")
    
    # 필수 환경변수 확인
    required_vars = ["APP_KEY", "APP_SECRET"]
    for var in required_vars:
        value = os.getenv(var, "")
        if value:
            masked = value[:8] + "*" * (len(value) - 16) + value[-8:] if len(value) > 16 else "***"
            print(f"✅ {var}: {masked}")
        else:
            print(f"❌ {var}: 설정되지 않음")
            return False
    
    print(f"🏦 KIS_MOCK: {os.getenv('KIS_MOCK', 'false')}")
    return True

def test_token_generation():
    """KIS API 토큰 발급 테스트"""
    print("\n" + "=" * 60)
    print("🔑 KIS API 토큰 발급 테스트")
    print("=" * 60)
    
    try:
        import kis_client
        
        # 토큰 발급 (kis_client 내부 함수 호출)
        token = kis_client._get_token()
        
        if token:
            masked_token = token[:10] + "*" * 20 + token[-10:]
            print(f"✅ 토큰 발급 성공: {masked_token}")
            return True
        else:
            print("❌ 토큰 발급 실패: 빈 토큰")
            return False
            
    except Exception as e:
        print(f"❌ 토큰 발급 실패: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

def test_stock_price_api():
    """주식 현재가 조회 API 테스트"""
    print("\n" + "=" * 60)
    print("📈 주식 현재가 조회 API 테스트")
    print("=" * 60)
    
    try:
        import kis_client
        
        # 삼성전자 현재가 조회
        stock_code = "005930"
        print(f"🎯 테스트 종목: {stock_code} (삼성전자)")
        
        result = kis_client.get_current_price(stock_code)
        
        if result:
            print("✅ 현재가 조회 성공!")
            print(f"📊 현재가: {result.get('current_price', 'N/A'):,}원")
            print(f"📊 전일종가: {result.get('prev_close', 'N/A'):,}원")
            print(f"📊 등락액: {result.get('change', 'N/A'):,}원")
            print(f"📊 등락률: {result.get('change_rate', 'N/A')}%")
            print(f"📊 거래량: {result.get('volume', 'N/A'):,}주")
            print(f"📊 기준일: {result.get('price_date', 'N/A')}")
            return True
        else:
            print("❌ 현재가 조회 실패: 빈 결과")
            return False
            
    except Exception as e:
        print(f"❌ 현재가 조회 실패: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

def test_multiple_stocks():
    """여러 종목 테스트"""
    print("\n" + "=" * 60)
    print("📊 여러 종목 현재가 테스트")
    print("=" * 60)
    
    stocks = {
        "005930": "삼성전자",
        "000660": "SK하이닉스", 
        "035420": "NAVER",
        "035720": "카카오",
        "207940": "삼성바이오로직스"
    }
    
    try:
        import kis_client
        
        success_count = 0
        for code, name in stocks.items():
            try:
                print(f"\n🔍 {name} ({code}) 조회 중...")
                result = kis_client.get_current_price(code)
                
                if result:
                    print(f"✅ {name}: {result.get('current_price', 'N/A'):,}원")
                    success_count += 1
                else:
                    print(f"❌ {name}: 조회 실패")
                    
            except Exception as e:
                print(f"❌ {name}: {type(e).__name__}: {e}")
        
        print(f"\n📈 성공률: {success_count}/{len(stocks)} ({success_count/len(stocks)*100:.1f}%)")
        return success_count > 0
        
    except Exception as e:
        print(f"❌ 전체 테스트 실패: {type(e).__name__}: {e}")
        return False

def main():
    """메인 테스트 함수"""
    print("🚀 KIS API 연결 테스트 시작")
    print("=" * 60)
    
    test_results = []
    
    # 1. 모듈 임포트 테스트
    test_results.append(("모듈 임포트", test_kis_import()))
    
    if not test_results[0][1]:
        print("\n❌ 모듈 임포트에 실패했습니다. 다른 테스트를 진행할 수 없습니다.")
        return
    
    # 2. 환경변수 테스트
    test_results.append(("환경변수 설정", test_environment_variables()))
    
    if not test_results[1][1]:
        print("\n❌ 환경변수 설정에 문제가 있습니다. API 호출 테스트를 건너뜁니다.")
    else:
        # 3. 토큰 발급 테스트
        test_results.append(("토큰 발급", test_token_generation()))
        
        if test_results[2][1]:
            # 4. 단일 종목 테스트
            test_results.append(("현재가 조회", test_stock_price_api()))
            
            if test_results[3][1]:
                # 5. 다중 종목 테스트
                test_results.append(("다중 종목 테스트", test_multiple_stocks()))
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("📋 테스트 결과 요약")
    print("=" * 60)
    
    for test_name, result in test_results:
        status = "✅ 성공" if result else "❌ 실패"
        print(f"{test_name}: {status}")
    
    success_count = sum(1 for _, result in test_results if result)
    total_count = len(test_results)
    
    print(f"\n🎯 전체 성공률: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
    
    if all(result for _, result in test_results):
        print("\n🎉 모든 테스트가 성공했습니다! KIS API가 정상적으로 연결되었습니다.")
    else:
        print("\n⚠️  일부 테스트가 실패했습니다. 위의 오류 메시지를 확인해주세요.")

if __name__ == "__main__":
    main()