"""
간단한 데이터베이스 테이블 생성 스크립트
"""
import os
import sys

# 현재 디렉토리를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import sqlite3
    
    # SQLite 데이터베이스 파일 경로
    db_path = "seedup.db"  # 기존 데이터베이스 파일
    
    print(f"데이터베이스 파일: {db_path}")
    print(f"파일 존재 여부: {os.path.exists(db_path)}")
    
    # 데이터베이스 연결
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 기존 테이블 목록 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = [row[0] for row in cursor.fetchall()]
    print(f"기존 테이블: {existing_tables}")
    
    # chat_sessions 테이블 생성
    create_sessions_table = """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        title TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    
    # chat_messages 테이블 생성  
    create_messages_table = """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        extra_data TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
    )
    """
    
    # 테이블 생성 실행
    print("chat_sessions 테이블 생성 중...")
    cursor.execute(create_sessions_table)
    
    print("chat_messages 테이블 생성 중...")
    cursor.execute(create_messages_table)
    
    # 커밋
    conn.commit()
    
    # 생성된 테이블 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    final_tables = [row[0] for row in cursor.fetchall()]
    print(f"최종 테이블 목록: {final_tables}")
    
    # 챗봇 테이블 확인
    chatbot_tables = ['chat_sessions', 'chat_messages']
    for table in chatbot_tables:
        if table in final_tables:
            print(f"✅ {table} 테이블 생성 완료")
        else:
            print(f"❌ {table} 테이블 생성 실패")
    
    conn.close()
    print("🎉 데이터베이스 테이블 생성 완료!")
    
except Exception as e:
    print(f"❌ 오류 발생: {str(e)}")
    import traceback
    traceback.print_exc()