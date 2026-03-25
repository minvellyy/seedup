"""
챗봇 데이터베이스 테이블 생성 스크립트
새로 추가된 chat_sessions, chat_messages 테이블을 생성합니다.
"""
import sys
import os

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from database import engine
    from models import Base, ChatSession, ChatMessage
    from sqlalchemy import text
    print("✅ 모듈 import 성공")
except Exception as e:
    print(f"❌ 모듈 import 실패: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def create_chatbot_tables():
    """챗봇 관련 테이블 생성"""
    try:
        print("챗봇 데이터베이스 테이블을 생성합니다...")
        
        # 모든 테이블 생성 (이미 존재하면 무시됨)
        Base.metadata.create_all(bind=engine)
        
        print("✅ 챗봇 테이블 생성 완료!")
        print("  - chat_sessions: 채팅 세션 관리")
        print("  - chat_messages: 채팅 메시지 저장")
        
        # 테이블 존재 확인
        with engine.connect() as conn:
            # 테이블 목록 조회
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
            tables = [row[0] for row in result.fetchall()]
            
            print(f"\n현재 데이터베이스 테이블 목록:")
            for table in tables:
                print(f"  - {table}")
                
            # 챗봇 테이블 확인
            chatbot_tables = ['chat_sessions', 'chat_messages']
            for table in chatbot_tables:
                if table in tables:
                    print(f"✅ {table} 테이블이 성공적으로 생성되었습니다.")
                else:
                    print(f"❌ {table} 테이블 생성에 실패했습니다.")
    
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_chatbot_tables()