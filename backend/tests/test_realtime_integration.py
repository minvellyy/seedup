#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
실시간 데이터 챗봇 테스트
"""

import sys
import requests
import json
from pathlib import Path

# 현재 디렉토리를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent))

def test_chatbot_realtime():
    """실시간 데이터가 실제로 챗봇에서 작동하는지 테스트"""
    print("=" * 60)
    print("🤖 실시간 데이터 챗봇 테스트")
    print("=" * 60)
    
    # 테스트 메시지들
    test_messages = [
        "삼성전자 현재가 알려줘",
        "지금 어떤 종목을 매수하면 좋을까요?",
        "카카오 주가 어때?"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n📝 테스트 {i}: {message}")
        print("-" * 40)
        
        try:
            # 챗봇 API 호출
            response = requests.post(
                "http://127.0.0.1:8000/api/chat/send",
                json={
                    "user_id": 999999,  # 게스트 사용자 (올바른 ID)
                    "message": message
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"📋 전체 응답: {result}")  # 디버그용
                
                bot_response = result.get("message", "")  # 'response' → 'message'로 수정
                
                print(f"✅ 응답 성공 (길이: {len(bot_response)}자)")
                
                # 실시간 데이터 포함 여부 체크
                realtime_indicators = [
                    "📈 실시간 주가 정보",
                    "192,600원",  # KIS API에서 받은 삼성전자 실제 가격 (업데이트된 값)
                    "현재가",
                    "등락률",
                    "한국투자증권 API"
                ]
                
                found_indicators = []
                for indicator in realtime_indicators:
                    if indicator in bot_response:
                        found_indicators.append(indicator)
                
                if found_indicators:
                    print(f"🎯 실시간 데이터 감지됨: {found_indicators}")
                else:
                    print("⚠️ 실시간 데이터가 응답에 포함되지 않음")
                
                # 응답 일부 출력 (처음 200자)
                print(f"📄 응답 일부: {bot_response[:200]}...")
                
            else:
                print(f"❌ API 호출 실패: {response.status_code}")
                print(f"오류: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 연결 오류: {e}")
        
        print()

def test_direct_api():
    """KIS API 직접 테스트"""
    print("=" * 60)
    print("📡 KIS API 직접 테스트")
    print("=" * 60)
    
    try:
        # 직접 모듈 임포트 테스트
        import kis_client
        
        print("✅ kis_client 모듈 임포트 성공")
        
        # 삼성전자 현재가 조회
        result = kis_client.get_current_price("005930")
        print(f"🎯 삼성전자 현재가 (직접 조회): {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ KIS API 직접 조회 실패: {e}")
        return False

if __name__ == "__main__":
    print("🚀 실시간 데이터 통합 테스트 시작\n")
    
    # 1. KIS API 직접 테스트
    kis_working = test_direct_api()
    
    # 2. 챗봇 실시간 데이터 테스트 
    if kis_working:
        test_chatbot_realtime()
    else:
        print("\n❌ KIS API가 작동하지 않아 챗봇 테스트를 건너뜁니다.")
    
    print("=" * 60)
    print("🎯 테스트 완료")
    print("\n💡 백엔드 재시작 후 다시 테스트해보세요!")