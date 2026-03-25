
#!/usr/bin/env python3
"""
챗봇 API 테스트 스크립트
"""
import requests
import json
from typing import Dict, Any

# FastAPI 서버 URL
BASE_URL = "http://127.0.0.1:8000"

def test_chatbot_api(user_id: int, message: str, session_id: str = None) -> Dict[str, Any]:
    """챗봇 API 테스트"""
    url = f"{BASE_URL}/api/chat/send"
    
    payload = {
        "user_id": user_id,
        "message": message,
        "session_id": session_id
    }
    
    print(f"\n🚀 API 요청:")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(url, json=payload, timeout=60)  # 30초 → 60초로 증가
        
        print(f"\n📊 응답:")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 성공!")
            print(f"Session ID: {result.get('session_id', 'N/A')}")
            print(f"메시지 길이: {len(result.get('message', ''))}")
            print(f"응답 내용: {result.get('message', 'N/A')[:200]}...")
            return result
        else:
            print(f"❌ 실패!")
            print(f"Response: {response.text}")
            return {"error": True, "message": response.text}
            
    except requests.exceptions.ConnectionError:
        print("❌ 연결 실패: FastAPI 서버가 실행 중인지 확인하세요 (python main.py)")
        return {"error": True, "message": "Connection failed"}
    except Exception as e:
        print(f"❌ 오류: {e}")
        return {"error": True, "message": str(e)}

def main():
    print("=" * 60)
    print("🤖 챗봇 API 테스트 시작")
    print("=" * 60)
    
    # 서버 상태 확인
    try:
        health_response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ 서버 상태: 정상")
        else:
            print(f"⚠️  서버 상태: {health_response.status_code}")
    except:
        print("❌ 서버가 실행되지 않거나 연결할 수 없습니다.")
        print("서버를 먼저 실행하시기 바랍니다: python main.py")
        return
    
    print("\n" + "=" * 60)
    print("🧪 테스트 1: 실제 사용자 (user_id=1)")
    print("=" * 60)
    
    result1 = test_chatbot_api(
        user_id=1,
        message="안녕하세요! 삼성전자에 대해 분석해주세요."
    )
    
    print("\n" + "=" * 60)
    print("🧪 테스트 2: 게스트 사용자 (user_id=999999)")
    print("=" * 60)
    
    result2 = test_chatbot_api(
        user_id=999999,
        message="포트폴리오 추천 받을 수 있나요?"
    )
    
    print("\n" + "=" * 60)
    print("🧪 테스트 3: 세션 연속성 테스트 (같은 세션에 두 번째 메시지)")
    print("=" * 60)
    
    if not result1.get("error") and result1.get("session_id"):
        session_id = result1["session_id"]
        result3 = test_chatbot_api(
            user_id=1,
            message="추가로 현대차 분석도 부탁드립니다.",
            session_id=session_id
        )
    else:
        print("⚠️  첫 번째 테스트가 실패해서 세션 연속성 테스트를 건너뜁니다.")
    
    print("\n" + "=" * 60)
    print("🧪 테스트 4: 잘못된 user_id")
    print("=" * 60)
    
    result4 = test_chatbot_api(
        user_id=99999,  # 존재하지 않는 사용자
        message="안녕하세요"
    )
    
    print("\n" + "=" * 60)
    print("📋 테스트 요약")
    print("=" * 60)
    
    tests = [
        ("실제 사용자 테스트", result1),
        ("게스트 사용자 테스트", result2),
        ("잘못된 사용자 테스트", result4)
    ]
    
    for test_name, result in tests:
        if result.get("error"):
            print(f"❌ {test_name}: 실패")
        else:
            print(f"✅ {test_name}: 성공")
    
    print("\n💡 문제가 있다면:")
    print("1. FastAPI 서버가 실행 중인지 확인 (python main.py)")
    print("2. OpenAI API 키가 .env에 올바르게 설정되었는지 확인")
    print("3. MySQL 데이터베이스 연결 상태 확인")
    print("4. 사용자 ID=1이 users 테이블에 존재하는지 확인")

if __name__ == '__main__':
    main()