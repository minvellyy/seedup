import sqlite3

conn = sqlite3.connect('seedup.db')
cursor = conn.cursor()

# users 테이블 스키마 확인
cursor.execute("PRAGMA table_info(users)")
columns = cursor.fetchall()

print("=== Users 테이블 컬럼 정보 ===")
for col in columns:
    print(f"ID: {col[0]}, Name: {col[1]}, Type: {col[2]}, NotNull: {col[3]}, Default: {col[4]}, PK: {col[5]}")

# password_hash 컬럼이 있고 password 컬럼이 없으면 변경
column_names = [col[1] for col in columns]

if 'password_hash' in column_names and 'password' not in column_names:
    print("\n=== password_hash를 password로 변경합니다 ===")
    
    # 임시 테이블 생성
    cursor.execute('DROP TABLE IF EXISTS users_temp')
    cursor.execute('''
        CREATE TABLE users_temp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            name TEXT,
            phone TEXT,
            birth_date TEXT,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 기존 데이터 복사
    cursor.execute('''
        INSERT INTO users_temp (id, email, username, name, phone, birth_date, password, created_at)
        SELECT id, email, username, name, phone, birth_date, password_hash, created_at
        FROM users
    ''')
    
    # 기존 테이블 삭제 및 교체
    cursor.execute('DROP TABLE users')
    cursor.execute('ALTER TABLE users_temp RENAME TO users')
    
    conn.commit()
    print("✅ 변경 완료!")
    
    # 변경 후 스키마 확인
    cursor.execute("PRAGMA table_info(users)")
    columns_after = cursor.fetchall()
    print("\n=== 변경 후 Users 테이블 컬럼 ===")
    for col in columns_after:
        print(f"Name: {col[1]}, Type: {col[2]}")
elif 'password' in column_names:
    print("\n✅ password 컬럼이 이미 존재합니다.")
else:
    print("\n❌ password_hash와 password 컬럼 모두 없습니다!")

conn.close()
