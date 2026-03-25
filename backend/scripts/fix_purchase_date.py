"""purchase_date를 NULL 허용으로 변경하는 간단한 스크립트"""
import pymysql
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent / '.env')

try:
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        charset='utf8mb4'
    )
    
    cursor = conn.cursor()
    
    # ALTER 실행
    cursor.execute("""
        ALTER TABLE user_holdings 
        MODIFY COLUMN purchase_date DATE NULL
    """)
    conn.commit()
    
    print("purchase_date 컬럼이 NULL 허용으로 변경되었습니다!")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ 오류: {e}")
