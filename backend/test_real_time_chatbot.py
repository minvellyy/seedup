#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
실시간 데이터 통합 챗봇 테스트
"""

import json
import requests
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

BASE_URL = "http://localhost:8000"

def test_real_time_data_integration():
    """실시간 데이터가 포함된 챗봇 응답 테스트"""
    print("🚀 실시간 데이터 통합 챗봇 테스트 시작")
    print("=" * 60)
    
    # 테스트 케이스: 삼성전자 관련 질문
    test_cases = [
        {
            "name": "삼성전자 현재가 문의",
            "user_id": 10,
            "message": "삼성전자 현재 주가가 얼마에요?"
        },
        {
            "name": "삼성전자 분석 요청",
            "user_id": 10,
            "message": "삼성전자 분석해주세요"
        },
        {
            "name": "게스트 사용자 - 삼성전자 문의",
            "user_id": 999,  # 게스트 사용자
            "message": "삼성전자 어떤가요?"
        },
        {
            "name": "카카오 관련 문의",
            "user_id": 10,
            "message": "카카오 주식 지금 어떤가요?"
        },
        {
            "name": "일반 투자 질문 (실시간 데이터 불필요)",
            "user_id": 10,
            "message": "주식 투자 처음하려는데 어떻게 해야 할까요?"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📝 테스트 {i}: {test_case['name']}")
        print(f"사용자 ID: {test_case['user_id']}")
        print(f"메시지: {test_case['message']}")
        print("-" * 40)
        
        try:
            # 챗봇 API 호출
            response = requests.post(
                f"{BASE_URL}/chatbot/chat",
                json={
                    "user_id": test_case["user_id"],
                    "message": test_case["message"]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 성공 (상태코드: {response.status_code})")
                print(f"🤖 챗봇 응답:")
                print(result.get("response", "응답 없음"))
                
                # 실시간 데이터 포함 여부 확인
                response_text = result.get("response", "")
                if any(keyword in response_text for keyword in ["현재가", "종가", "₩", "원", "%", "급등", "급락"]):
                    print("📊 실시간 데이터 포함 확인됨")
                else:
                    print("ℹ️ 실시간 데이터 미포함 (일반 답변)")
                    
            else:
                print(f"❌ 실패 (상태코드: {response.status_code})")
                print(f"오류 내용: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 요청 오류: {e}")
        
        print()
    
    print("=" * 60)
    print("🎯 실시간 데이터 통합 테스트 완료")

def test_kis_connection():
    """KIS API 연결 상태 확인"""
    print("\n🔗 KIS API 연결 테스트")
    print("-" * 40)
    
    try:
        # KIS 연결 상태 확인 엔드포인트 (있다면)
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            print("✅ 백엔드 서버 연결 정상")
        else:
            print(f"⚠️ 백엔드 서버 응답 이상: {response.status_code}")
    except Exception as e:
        print(f"❌ 서버 연결 실패: {e}")

if __name__ == "__main__":
    test_kis_connection()
    test_real_time_data_integration()