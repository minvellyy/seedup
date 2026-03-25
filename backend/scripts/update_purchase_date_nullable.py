"""매입일 컬럼을 NULL 허용으로 변경"""
import pymysql
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent / '.env')

def update_purchase_date_nullable():
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
        
        print("1. 현재 purchase_date 컬럼 구조 확인...")
        cursor.execute("DESCRIBE user_holdings")
        columns = cursor.fetchall()
        
        for col in columns:
            if col[0] == 'purchase_date':
                print(f"   - {col}")
                
        print("\n2. purchase_date 컬럼을 NULL 허용으로 변경 중...")
        cursor.execute("""
            ALTER TABLE user_holdings 
            MODIFY COLUMN purchase_date DATE NULL
        """)
        conn.commit()
        print("   ✅ 변경 완료!")
        
        print("\n3. 변경 후 컬럼 구조 확인...")
        cursor.execute("DESCRIBE user_holdings")
        columns = cursor.fetchall()
        
        for col in columns:
            if col[0] == 'purchase_date':
                print(f"   - {col}")
                if col[2] == 'YES':
                    print("   ✅ NULL 허용으로 변경됨!")
                else:
                    print("   ⚠️  여전히 NOT NULL 상태")
        
        cursor.close()
        conn.close()
        
        print("\n완료! 이제 매입일 없이도 보유 주식을 등록할 수 있습니다.")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    update_purchase_date_nullable()
