import sqlite3

conn = sqlite3.connect('seedup.db')
cursor = conn.cursor()

print("=== Users 테이블 ===")
cursor.execute('SELECT id, email, username FROM users')
users = cursor.fetchall()
for user in users:
    print(f"ID: {user[0]}, Email: {user[1]}, Username: {user[2]}")

print("\n=== Survey Answers 테이블 (최근 10개) ===")
cursor.execute('SELECT id, user_id, question_id, value_text, value_number, value_choice, created_at FROM survey_answers ORDER BY created_at DESC LIMIT 10')
answers = cursor.fetchall()
for answer in answers:
    print(f"Answer ID: {answer[0]}, User ID: {answer[1]}, Question ID: {answer[2]}, Text: {answer[3]}, Number: {answer[4]}, Choice: {answer[5]}, Created: {answer[6]}")

print("\n=== User ID별 설문 응답 집계 ===")
cursor.execute('SELECT user_id, COUNT(*) FROM survey_answers GROUP BY user_id')
stats = cursor.fetchall()
for stat in stats:
    print(f"User ID: {stat[0]}, 응답 수: {stat[1]}")

conn.close()
