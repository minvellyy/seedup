"""
보유 주식 테이블 생성 및 API 구현
"""
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_holdings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    stock_code VARCHAR(20) NOT NULL,
    stock_name VARCHAR(100) NOT NULL,
    broker VARCHAR(50),
    account_number VARCHAR(100),
    shares INT NOT NULL,
    purchase_price DECIMAL(15, 2) NOT NULL,
    purchase_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

from dotenv import load_dotenv
import os
import pymysql

load_dotenv()

print("=" * 80)
print("보유 주식 테이블 생성")
print("=" * 80)

conn = pymysql.connect(
    host=os.getenv('DB_HOST'),
    port=3306,
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    db=os.getenv('DB_NAME'),
    charset='utf8mb4'
)

try:
    cur = conn.cursor()
    
    print("\n1. user_holdings 테이블 생성 중...")
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    print("✅ 테이블 생성 완료!")
    
    # 테이블 구조 확인
    print("\n2. 생성된 테이블 구조:")
    print("-" * 80)
    cur.execute("DESCRIBE user_holdings")
    for row in cur.fetchall():
        print(f"  {row}")
    
    print("\n" + "=" * 80)
    print("완료! 이제 보유 주식 API를 사용할 수 있습니다.")
    print("=" * 80)
    
except Exception as e:
    print(f"\n❌ 오류 발생: {e}")
    conn.rollback()
finally:
    conn.close()
