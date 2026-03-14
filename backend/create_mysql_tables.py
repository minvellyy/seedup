"""
MySQL 데이터베이스에 챗봇 테이블 생성
"""
import os
import sys
from dotenv import load_dotenv
import pymysql

# 현재 디렉토리를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# .env 파일 로드
load_dotenv()

def create_chatbot_tables():
    """MySQL에 챗봇 테이블 생성"""
    
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
        
        print(f"MySQL 연결 정보:")
        print(f"  Host: {config['host']}:{config['port']}")
        print(f"  Database: {config['database']}")
        print(f"  User: {config['user']}")
        
        # MySQL 연결
        connection = pymysql.connect(**config)
        cursor = connection.cursor()
        
        print("✅ MySQL 연결 성공!")
        
        # 기존 테이블 목록 확인
        cursor.execute("SHOW TABLES")
        existing_tables = [row[0] for row in cursor.fetchall()]
        print(f"기존 테이블: {existing_tables}")
        
        # chat_sessions 테이블 생성
        create_sessions_sql = """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id VARCHAR(255) PRIMARY KEY,
            user_id INT NOT NULL,
            title VARCHAR(255),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_user_id (user_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        
        # chat_messages 테이블 생성
        create_messages_sql = """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            message_metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_session_id (session_id),
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        
        # 테이블 생성 실행
        print("chat_sessions 테이블 생성 중...")
        cursor.execute(create_sessions_sql)
        print("✅ chat_sessions 테이블 완료")
        
        print("chat_messages 테이블 생성 중...")
        cursor.execute(create_messages_sql)
        print("✅ chat_messages 테이블 완료")
        
        # 커밋
        connection.commit()
        
        # 최종 테이블 목록 확인
        cursor.execute("SHOW TABLES")
        final_tables = [row[0] for row in cursor.fetchall()]
        print(f"최종 테이블 목록: {final_tables}")
        
        # 챗봇 테이블 확인
        chatbot_tables = ['chat_sessions', 'chat_messages']
        for table in chatbot_tables:
            if table in final_tables:
                print(f"✅ {table} 테이블 생성 완료")
            else:
                print(f"❌ {table} 테이블 생성 실패")
        
        # 연결 종료
        cursor.close()
        connection.close()
        print("🎉 MySQL 챗봇 테이블 생성 완료!")
        return True
        
    except pymysql.Error as e:
        print(f"❌ MySQL 오류: {str(e)}")
        return False
        
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("MySQL 챗봇 테이블 생성 시작!")
    print("=" * 50)
    
    success = create_chatbot_tables()
    
    print("=" * 50)
    if success:
        print("🎉 챗봇 테이블 생성이 완료되었습니다!")
        print("이제 챗봇을 사용할 수 있습니다.")
    else:
        print("💡 문제 해결:")
        print("- MySQL 서버가 실행 중인지 확인")
        print("- 네트워크 연결 상태 확인")
        print("- 데이터베이스 접근 권한 확인")