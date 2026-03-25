#!/usr/bin/env python3
"""
챗봇 API 테스트 스크립트
- 세션 목록 조회 테스트
- 메시지 로드 테스트
"""
import requests
import json

def test_chat_sessions_api():
    """세션 목록 API 테스트"""
    print("=== 채팅 세션 API 테스트 ===")
    
    # 실제 사용자 ID (14) 테스트
    user_id = 14
    url = f"http://localhost:8000/api/chat/sessions?user_id={user_id}"
    
    try:
        print(f"API 요청: {url}")
        response = requests.get(url)
        print(f"응답 상태코드: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"응답 데이터:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            if data.get("success"):
                sessions = data.get("sessions", [])
                print(f"\n✅ 성공! {len(sessions)}개 세션 발견")
                for i, session in enumerate(sessions[:3]):
                    print(f"  {i+1}. {session.get('title', 'No Title')} ({session.get('id', 'No ID')[:8]}...)")
            else:
                print(f"❌ API 실패: {data.get('message')}")
        else:
            print(f"❌ HTTP 오류: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ 연결 오류: {e}")
        
def test_session_messages_api():
    """세션 메시지 API 테스트"""
    print("\n=== 채팅 메시지 API 테스트 ===")
    
    # 최근 세션 ID 사용
    session_id = "e787d153-9a05-44ca-a786-cf9930b67f84"  # 예시
    user_id = 14
    url = f"http://localhost:8000/api/chat/sessions/{session_id}/messages?user_id={user_id}"
    
    try:
        print(f"API 요청: {url}")
        response = requests.get(url)
        print(f"응답 상태코드: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"응답 데이터:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            if data.get("success"):
                messages = data.get("messages", [])
                print(f"\n✅ 성공! {len(messages)}개 메시지 발견")
                for msg in messages:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')[:50] + '...' if len(msg.get('content', '')) > 50 else msg.get('content', '')
                    print(f"  {role}: {content}")
            else:
                print(f"❌ API 실패: {data.get('message')}")
        else:
            print(f"❌ HTTP 오류: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ 연결 오류: {e}")

if __name__ == "__main__":
    print("챗봇 API 테스트 시작!")
    print("=" * 50)
    
    test_chat_sessions_api()
    test_session_messages_api()
    
    print("\n" + "=" * 50)
    print("테스트 완료!")
    print("\n💡 문제 해결 가이드:")
    print("1. 백엔드 서버가 http://localhost:8000 에서 실행중인지 확인")
    print("2. 프론트엔드에서 올바른 사용자 ID가 전달되는지 확인") 
    print("3. 브라우저 개발자도구 > Network 탭에서 API 호출 상태 확인")
    print("4. 브라우저 개발자도구 > Console 탭에서 JavaScript 오류 확인")