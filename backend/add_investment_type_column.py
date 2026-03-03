"""
투자성향(investment_type) 컬럼을 users 테이블에 추가하는 스크립트
"""
from sqlalchemy import text
from database import engine, SessionLocal

def add_investment_type_column():
    """users 테이블에 investment_type 컬럼 추가"""
    db = SessionLocal()
    try:
        # 컬럼이 이미 존재하는지 확인
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'users' 
            AND COLUMN_NAME = 'investment_type'
        """))
        count = result.fetchone()[0]
        
        if count > 0:
            print("✓ investment_type 컬럼이 이미 존재합니다.")
            return
        
        # 컬럼 추가
        print("investment_type 컬럼을 추가하는 중...")
        db.execute(text("""
            ALTER TABLE users 
            ADD COLUMN investment_type VARCHAR(50) NULL 
            COMMENT '투자성향 (안정형, 안정추구형, 위험중립형, 적극투자형, 공격투자형)'
        """))
        db.commit()
        print("✓ investment_type 컬럼이 성공적으로 추가되었습니다!")
        
    except Exception as e:
        print(f"✗ 오류 발생: {str(e)}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("="*60)
    print("Users 테이블에 investment_type 컬럼 추가")
    print("="*60)
    add_investment_type_column()
    print("="*60)
