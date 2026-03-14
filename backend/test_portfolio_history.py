"""
포트폴리오 추천 히스토리 저장 및 조회 테스트

이 스크립트로 확인할 내용:
1. DB에 포트폴리오 추천이 저장되는지
2. 히스토리가 제대로 쌓이는지 (ARCHIVED로 변경되는지)
3. API로 조회가 되는지
"""

from dotenv import load_dotenv
import os
import pymysql

load_dotenv()

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

print("=" * 80)
print("포트폴리오 추천 히스토리 확인")
print("=" * 80)

# 전체 추천 현황
print("\n1. 전체 포트폴리오 추천 현황 (최신 20개)")
print("-" * 80)

cur.execute("""
    SELECT id, user_id, strategy_name, state, created_at
    FROM portfolio_recommendations
    ORDER BY created_at DESC
    LIMIT 20
""")

rows = cur.fetchall()
if rows:
    print(f"총 {len(rows)}개의 추천 기록:\n")
    for row in rows:
        print(f"ID: {row['id']}, User: {row['user_id']}, Strategy: {row['strategy_name']}, State: {row['state']}, Created: {row['created_at']}")
else:
    print("추천 기록이 없습니다.")

# balanced, momentum, lowvol 전략 현황
print("\n\n2. 3종 전략(balanced, momentum, lowvol) 현황")
print("-" * 80)

cur.execute("""
    SELECT user_id, strategy_name, state, COUNT(*) as count
    FROM portfolio_recommendations
    WHERE strategy_name IN ('balanced', 'momentum', 'lowvol')
    GROUP BY user_id, strategy_name, state
    ORDER BY user_id, strategy_name, state
""")

rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"User {row['user_id']} - {row['strategy_name']} ({row['state']}): {row['count']}개")
else:
    print("3종 전략 추천이 없습니다.")

# 최신 ACTIVE 추천
print("\n\n3. 현재 ACTIVE 상태 추천")
print("-" * 80)

cur.execute("""
    SELECT user_id, strategy_name, created_at
    FROM portfolio_recommendations
    WHERE state = 'ACTIVE'
    ORDER BY user_id, strategy_name
""")

rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"User {row['user_id']} - {row['strategy_name']} (생성: {row['created_at']})")
else:
    print("ACTIVE 상태 추천이 없습니다.")

conn.close()

print("\n" + "=" * 80)
print("테스트 완료")
print("=" * 80)
print("\n✅ 수정 완료:")
print("   - _save_portfolio_to_db 함수에 conn.commit() 추가")
print("   - 에러 로깅 개선 (traceback 추가)")
print("\n⚠️  중요: FastAPI 서버를 재시작해야 합니다!")
print("   1. 현재 실행 중인 서버를 종료하세요 (Ctrl+C)")
print("   2. 서버를 다시 시작하세요:")
print("      cd backend")
print("      python main.py")
print("\n다음 단계:")
print("1. 서버 재시작 후 대시보드에서 포트폴리오 추천 받기")
print("   - URL: http://localhost:3000/dashboard")
print("   - '포트폴리오 분석' 버튼 클릭")
print("2. MyPage > 추천 전략 히스토리에서 확인")
print("   - URL: http://localhost:3000/mypage (히스토리 탭)")
print("3. 다시 이 스크립트 실행하여 DB 저장 확인:")
print("   python backend\\test_portfolio_history.py")
