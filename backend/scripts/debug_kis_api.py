#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KIS API 상세 디버깅 스크립트
"""

import sys
import json
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def debug_kis_api_call():
    """KIS API 호출 상세 디버깅"""
    print("=" * 60)
    print("🔍 KIS API 호출 상세 디버깅")
    print("=" * 60)
    
    try:
        import requests
        import os
        from dotenv import load_dotenv
        
        # 환경변수 로드
        env_file = Path(__file__).parent / ".env"
        load_dotenv(env_file)
        
        # 환경변수 확인
        app_key = os.getenv("APP_KEY", "").strip()
        app_secret = os.getenv("APP_SECRET", "").strip()
        is_mock = os.getenv("KIS_MOCK", "false").lower() == "true"
        
        if is_mock:
            base_url = "https://openapivts.koreainvestment.com:29443"
            print("🏦 모드: 모의투자")
        else:
            base_url = "https://openapi.koreainvestment.com:9443"
            print("🏦 모드: 실거래")
        
        print(f"🌐 Base URL: {base_url}")
        print(f"🔑 APP_KEY: {app_key[:10]}***{app_key[-5:]}")
        
        # Step 1: 토큰 발급
        print("\n--- Step 1: 토큰 발급 ---")
        token_url = f"{base_url}/oauth2/tokenP"
        token_data = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        }
        
        print(f"🔗 Token URL: {token_url}")
        print(f"📝 Request Data: {json.dumps(token_data, indent=2)}")
        
        token_response = requests.post(token_url, json=token_data, timeout=10)
        print(f"📊 Token Response Status: {token_response.status_code}")
        
        if token_response.status_code != 200:
            print(f"❌ 토큰 발급 실패")
            print(f"응답 내용: {token_response.text}")
            return False
        
        token_result = token_response.json()
        access_token = token_result.get("access_token")
        print(f"✅ 토큰 발급 성공: {access_token[:10]}***{access_token[-10:]}")
        
        # Step 2: 현재가 조회
        print("\n--- Step 2: 현재가 조회 ---")
        quote_url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        
        headers = {
            "authorization": f"Bearer {access_token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": "FHKST01010100",
            "content-type": "application/json; charset=utf-8",
        }
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": "005930",
        }
        
        print(f"🔗 Quote URL: {quote_url}")
        print(f"📝 Headers:")
        for key, value in headers.items():
            if key == "authorization":
                print(f"  {key}: Bearer {access_token[:10]}***{access_token[-10:]}")
            elif key in ["appkey", "appsecret"]:
                print(f"  {key}: {value[:10]}***{value[-5:]}")
            else:
                print(f"  {key}: {value}")
        
        print(f"📝 Params: {json.dumps(params, indent=2)}")
        
        # 실제 API 호출
        print("\n🚀 API 호출 중...")
        quote_response = requests.get(quote_url, headers=headers, params=params, timeout=10)
        
        print(f"📊 Quote Response Status: {quote_response.status_code}")
        print(f"📊 Response Headers: {dict(quote_response.headers)}")
        
        # 응답 내용 출력 (성공/실패 관계없이)
        try:
            response_json = quote_response.json()
            print(f"📄 Response JSON:")
            print(json.dumps(response_json, indent=2, ensure_ascii=False))
        except:
            print(f"📄 Response Text: {quote_response.text}")
        
        if quote_response.status_code == 200:
            print("✅ 현재가 조회 성공!")
            return True
        else:
            print(f"❌ 현재가 조회 실패: HTTP {quote_response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 전체 오류: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

def test_kis_connection():
    """기본 연결 테스트"""
    print("=" * 60)
    print("🌐 KIS 서버 연결 테스트")
    print("=" * 60)
    
    import requests
    import os
    from dotenv import load_dotenv
    
    env_file = Path(__file__).parent / ".env"
    load_dotenv(env_file)
    
    is_mock = os.getenv("KIS_MOCK", "false").lower() == "true"
    
    if is_mock:
        base_url = "https://openapivts.koreainvestment.com:29443"
    else:
        base_url = "https://openapi.koreainvestment.com:9443"
    
    try:
        # 간단한 ping 테스트 (토큰 발급 엔드포인트로)
        response = requests.get(f"{base_url}/oauth2/tokenP", timeout=5)
        print(f"✅ 서버 연결 가능: {base_url}")
        print(f"📊 응답 코드: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ 서버 연결 실패: {e}")
        return False

if __name__ == "__main__":
    print("🔧 KIS API 상세 디버깅 시작")
    print()
    
    # 기본 연결 테스트
    if test_kis_connection():
        # 상세 API 호출 디버깅
        debug_kis_api_call()
    else:
        print("\n⚠️ 기본 서버 연결이 실패하여 추가 테스트를 진행할 수 없습니다.")