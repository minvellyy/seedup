#!/usr/bin/env python3
"""
챗봇 테이블 수동 수정 스크립트
"""
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    conn = pymysql.connect(
        host=os.getenv('DB_HOST'), 
        port=3306,
        user=os.getenv('DB_USER'), 
        password=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'), 
        charset='utf8mb4'
    )

    cur = conn.cursor()

    print('=== 현재 chat_messages 테이블 구조 ===')
    try:
        cur.execute('DESCRIBE chat_messages')
        columns = cur.fetchall()
        print('현재 컬럼들:')
        for col in columns:
            print(f'  - {col[0]}: {col[1]} ({col[2]})')
        
        # session_id 컬럼 존재 여부 확인
        column_names = [col[0] for col in columns]
        if 'session_id' not in column_names:
            print('\n❌ session_id 컬럼이 없습니다!')
            
            print('\n🔧 session_id 컬럼을 추가합니다...')
            
            # session_id 컬럼 추가
            cur.execute('ALTER TABLE chat_messages ADD COLUMN session_id VARCHAR(255)')
            print('✅ session_id 컬럼 추가됨')
            
            # 인덱스 추가 (성능 향상)
            cur.execute('ALTER TABLE chat_messages ADD INDEX idx_session_id (session_id)')
            print('✅ session_id 인덱스 추가됨')
            
            # 외래 키 제약조건 추가 (선택사항)
            try:
                cur.execute('''
                    ALTER TABLE chat_messages 
                    ADD CONSTRAINT fk_chat_messages_session_id 
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
                    ON DELETE CASCADE
                ''')
                print('✅ 외래 키 제약조건 추가됨')
            except Exception as fk_error:
                print(f'⚠️  외래 키 추가 실패 (무시 가능): {fk_error}')
            
            conn.commit()
            
            print('\n=== 수정된 chat_messages 테이블 구조 ===')
            cur.execute('DESCRIBE chat_messages')
            updated_columns = cur.fetchall()
            for col in updated_columns:
                print(f'  - {col[0]}: {col[1]} ({col[2]})')
                
        else:
            print('✅ session_id 컬럼이 이미 존재합니다.')
            
    except Exception as e:
        print(f'❌ 오류: {e}')
        conn.rollback()
    finally:
        conn.close()
        
    print('\n✅ 완료! 이제 챗봇 테스트를 다시 실행하세요: python test_chatbot.py')

if __name__ == '__main__':
    main()