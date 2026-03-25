"""
간단한 챗봇 API 테스트
어디서 오류가 발생하는지 단계별로 확인합니다.
"""
import os
import sys
from dotenv import load_dotenv

# 현재 디렉토리를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("1️⃣ 환경 및 패키지 로드 테스트")
print("=" * 50)

# .env 파일 로드
load_dotenv()
print("✅ .env 파일 로드 완료")

# OpenAI API 키 확인
api_key = os.getenv("OPENAI_API_KEY")
print(f"✅ OpenAI API 키: {'설정됨' if api_key and api_key != 'pp_env' else '없음'}")

# 필요한 모듈 import 테스트
try:
    print("\n2️⃣ 모듈 import 테스트")
    print("=" * 50)
    
    import openai
    print("✅ openai 모듈 로드 성공")
    
    from sqlalchemy import create_engine
    print("✅ sqlalchemy 모듈 로드 성공")
    
    import pymysql
    print("✅ pymysql 모듈 로드 성공")
    
    # 내 모듈들 import 테스트
    try:
        from database import engine, SessionLocal
        print("✅ database 모듈 로드 성공")
    except Exception as e:
        print(f"❌ database 모듈 로드 실패: {e}")
        
    try:
        from models import User, ChatSession, ChatMessage
        print("✅ models 모듈 로드 성공")
    except Exception as e:
        print(f"❌ models 모듈 로드 실패: {e}")
        
except Exception as e:
    print(f"❌ 모듈 import 실패: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n3️⃣ 데이터베이스 연결 테스트")
print("=" * 50)

try:
    from database import SessionLocal
    
    # 데이터베이스 세션 생성 테스트
    db = SessionLocal()
    print("✅ 데이터베이스 세션 생성 성공")
    
    # 간단한 쿼리 테스트
    result = db.execute("SELECT 1 as test")
    row = result.fetchone()
    print(f"✅ 데이터베이스 쿼리 테스트 성공: {row}")
    
    db.close()
    print("✅ 데이터베이스 세션 종료 성공")
    
except Exception as e:
    print(f"❌ 데이터베이스 연결 실패: {e}")
    import traceback
    traceback.print_exc()

print("\n4️⃣ OpenAI 클라이언트 테스트")  
print("=" * 50)

try:
    client = openai.OpenAI(api_key=api_key)
    print("✅ OpenAI 클라이언트 생성 성공")
    
    # 간단한 API 호출 테스트
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=10
    )
    
    print("✅ OpenAI API 호출 성공")
    print(f"응답: {response.choices[0].message.content}")
    
except Exception as e:
    print(f"❌ OpenAI 테스트 실패: {e}")
    import traceback
    traceback.print_exc()

print("\n🎯 단계별 테스트 완료")
print("=" * 50)