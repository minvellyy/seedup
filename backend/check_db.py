import sqlite3

conn = sqlite3.connect('seedup.db')
cursor = conn.cursor()

# survey_answers 테이블 스키마 확인
cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="survey_answers"')
result = cursor.fetchone()
if result:
    print("Current survey_answers table schema:")
    print(result[0])
else:
    print("survey_answers table does not exist")

print("\n" + "="*50 + "\n")

# 테이블 삭제 및 재생성
print("Dropping and recreating survey_answers table...")
cursor.execute('DROP TABLE IF EXISTS survey_answers')
cursor.execute('''
    CREATE TABLE survey_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        value_text TEXT,
        value_number REAL,
        value_choice TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (question_id) REFERENCES survey_questions(id)
    )
''')
conn.commit()

# 새 스키마 확인
cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="survey_answers"')
result = cursor.fetchone()
print("\nNew survey_answers table schema:")
print(result[0])

conn.close()
print("\nDone!")
