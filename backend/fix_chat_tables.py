#!/usr/bin/env python3
"""
채팅 테이블 구조 확인 및 수정 스크립트
"""
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    # DB 연결
    conn = pymysql.connect(
        host=os.getenv('DB_HOST'), 
        port=3306,
        user=os.getenv('DB_USER'), 
        password=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'), 
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

    cur = conn.cursor()

    print('=== chat_sessions 테이블 구조 ===')
    try:
        cur.execute('DESCRIBE chat_sessions')
        sessions_columns = cur.fetchall()
        if sessions_columns:
            for col in sessions_columns:
                print(f"- {col['Field']}: {col['Type']} {col['Null']} {col['Key']}")
        else:
            print("❌ chat_sessions 테이블이 존재하지 않습니다.")
    except Exception as e:
        print(f"❌ chat_sessions 조회 오류: {e}")

    print('\n=== chat_messages 테이블 구조 ===')
    try:
        cur.execute('DESCRIBE chat_messages')
        messages_columns = cur.fetchall()
        if messages_columns:
            for col in messages_columns:
                print(f"- {col['Field']}: {col['Type']} {col['Null']} {col['Key']}")
            
            # session_id 컬럼 존재 여부 확인
            column_names = [col['Field'] for col in messages_columns]
            if 'session_id' not in column_names:
                print('\n❌ session_id 컬럼이 누락되었습니다!')
                print('\n💡 다음 SQL을 실행하여 컬럼을 추가하시겠습니까?')
                print('ALTER TABLE chat_messages ADD COLUMN session_id VARCHAR(255);')
                print('ALTER TABLE chat_messages ADD INDEX idx_session_id (session_id);')
                
                response = input('\n컬럼을 추가하시겠습니까? (y/N): ')
                if response.lower() == 'y':
                    try:
                        print('\n🔧 session_id 컬럼 추가 중...')
                        cur.execute('ALTER TABLE chat_messages ADD COLUMN session_id VARCHAR(255)')
                        cur.execute('ALTER TABLE chat_messages ADD INDEX idx_session_id (session_id)')
                        conn.commit()
                        print('✅ session_id 컬럼이 추가되었습니다!')
                        
                        # 수정된 테이블 구조 확인
                        print('\n=== 수정된 chat_messages 테이블 구조 ===')
                        cur.execute('DESCRIBE chat_messages')
                        updated_columns = cur.fetchall()
                        for col in updated_columns:
                            print(f"- {col['Field']}: {col['Type']} {col['Null']} {col['Key']}")
                            
                    except Exception as e:
                        print(f'❌ 컬럼 추가 실패: {e}')
                        conn.rollback()
                else:
                    print('컬럼 추가를 취소했습니다.')
            else:
                print('✅ session_id 컬럼이 존재합니다.')
        else:
            print("❌ chat_messages 테이블이 존재하지 않습니다.")
    except Exception as e:
        print(f"❌ chat_messages 조회 오류: {e}")

    print('\n=== 외래 키 제약조건 확인 ===')
    try:
        cur.execute("""
            SELECT 
                CONSTRAINT_NAME,
                TABLE_NAME,
                COLUMN_NAME,
                REFERENCED_TABLE_NAME,
                REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
            WHERE REFERENCED_TABLE_SCHEMA = %s 
            AND TABLE_NAME IN ('chat_sessions', 'chat_messages')
            AND REFERENCED_TABLE_NAME IS NOT NULL
        """, (os.getenv('DB_NAME'),))
        
        fk_constraints = cur.fetchall()
        if fk_constraints:
            for fk in fk_constraints:
                print(f"- {fk['TABLE_NAME']}.{fk['COLUMN_NAME']} -> {fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}")
        else:
            print("외래 키 제약조건이 없습니다.")
    except Exception as e:
        print(f"❌ 외래 키 조회 오류: {e}")

    conn.close()
    print('\n✅ 완료')

if __name__ == '__main__':
    main()