#!/usr/bin/env python3
"""
데이터베이스 테이블 존재 여부 확인 스크립트
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

    print('=== 현재 DB의 모든 테이블 ===')
    cur.execute('SHOW TABLES')
    tables = cur.fetchall()
    table_names = [list(table.values())[0] for table in tables]
    
    for table_name in sorted(table_names):
        print(f'- {table_name}')

    print('\n=== 챗봇 관련 테이블 존재 여부 ===')
    chatbot_tables = ['chat_sessions', 'chat_messages']
    existing_chatbot_tables = []
    
    for table in chatbot_tables:
        if table in table_names:
            print(f'✅ {table} - 존재함')
            existing_chatbot_tables.append(table)
        else:
            print(f'❌ {table} - 존재하지 않음')
    
    print(f'\n=== 요약 ===')
    print(f'전체 테이블 수: {len(table_names)}')
    print(f'챗봇 테이블 존재: {len(existing_chatbot_tables)}/2')
    
    if len(existing_chatbot_tables) == 0:
        print('\n💡 챗봇 테이블이 전혀 없습니다. 테이블 생성이 필요합니다.')
    elif len(existing_chatbot_tables) == 1:
        print('\n💡 챗봇 테이블이 부분적으로만 존재합니다. 누락된 테이블 생성이 필요합니다.')
    else:
        print('\n✅ 챗봇 테이블이 모두 존재합니다.')

    conn.close()

if __name__ == '__main__':
    main()