"""
채팅 세션 데이터베이스 확인 스크립트
"""
import os
import sys
from dotenv import load_dotenv
import pymysql

# 현재 디렉토리를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# .env 파일 로드
load_dotenv()

def check_chat_sessions():
    """채팅 세션 데이터 확인"""
    
    try:
        # MySQL 연결 정보
        config = {
            'host': os.getenv('DB_HOST', '192.168.101.70'),
            'port': int(os.getenv('DB_PORT', '3306')),
            'user': os.getenv('DB_USER', 'developer_team'),
            'password': os.getenv('DB_PASSWORD', '0327'),
            'database': os.getenv('DB_NAME', 'seedup_db'),
            'charset': 'utf8mb4'
        }
        
        print("채팅 세션 데이터 확인 중...")
        print(f"Database: {config['database']}")
        
        # MySQL 연결
        connection = pymysql.connect(**config)
        cursor = connection.cursor()
        
        # 채팅 세션 테이블 확인
        print("\n=== 채팅 세션 테이블 구조 ===")
        cursor.execute("DESCRIBE chat_sessions")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[0]}: {col[1]}")
        
        # 채팅 세션 개수 확인  
        print("\n=== 채팅 세션 데이터 ===")
        cursor.execute("SELECT COUNT(*) FROM chat_sessions")
        session_count = cursor.fetchone()[0]
        print(f"총 세션 개수: {session_count}개")
        
        if session_count > 0:
            # 최근 세션 5개 조회
            print("\n최근 세션 목록:")
            cursor.execute("""
                SELECT id, user_id, title, created_at, updated_at 
                FROM chat_sessions 
                ORDER BY updated_at DESC 
                LIMIT 5
            """)
            sessions = cursor.fetchall()
            for session in sessions:
                print(f"  ID: {session[0][:8]}...")
                print(f"  User ID: {session[1]}")  
                print(f"  Title: {session[2]}")
                print(f"  Created: {session[3]}")
                print(f"  Updated: {session[4]}")
                print("  ---")
        
        # 채팅 메시지 개수 확인
        print("\n=== 채팅 메시지 데이터 ===")
        cursor.execute("SELECT COUNT(*) FROM chat_messages")
        message_count = cursor.fetchone()[0]
        print(f"총 메시지 개수: {message_count}개")
        
        if message_count > 0:
            # 최근 메시지 5개 조회
            print("\n최근 메시지 목록:")
            cursor.execute("""
                SELECT cm.session_id, cm.role, cm.content, cm.created_at, cs.user_id
                FROM chat_messages cm
                LEFT JOIN chat_sessions cs ON cm.session_id = cs.id
                ORDER BY cm.created_at DESC 
                LIMIT 5
            """)
            messages = cursor.fetchall()
            for msg in messages:
                print(f"  Session: {msg[0][:8]}...")
                print(f"  User ID: {msg[4]}")
                print(f"  Role: {msg[1]}")
                print(f"  Content: {msg[2][:50]}...")
                print(f"  Created: {msg[3]}")
                print("  ---")
        
        # 사용자별 세션 개수
        print("\n=== 사용자별 세션 개수 ===")
        cursor.execute("""
            SELECT user_id, COUNT(*) as session_count
            FROM chat_sessions 
            GROUP BY user_id 
            ORDER BY session_count DESC
        """)
        user_sessions = cursor.fetchall()
        for user_stat in user_sessions:
            print(f"  User ID {user_stat[0]}: {user_stat[1]}개 세션")
        
        # 연결 종료
        cursor.close()
        connection.close()
        print("\n✅ 채팅 세션 데이터 확인 완료!")
        
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_chat_sessions()