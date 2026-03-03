from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal

def seed_survey_questions(session: Session):
    """설문 질문 시드 데이터 생성 - Raw SQL 사용"""
    # 기존 데이터 확인
    result = session.execute(text('SELECT COUNT(*) FROM survey_questions'))
    count = result.fetchone()[0]
    if count > 0:
        print(f"Survey questions already exist ({count} questions), skipping seeding")
        return
    
    questions = [
        ("INVEST_GOAL", "투자 목적은 무엇인가요?", "TEXT", None, 1),
        ("TARGET_HORIZON", "목표 시점은 언제인가요?", "TEXT", None, 2),
        ("TARGET_AMOUNT", "목표 금액은 어느 정도인가요?", "NUMBER", None, 3),
        ("CONTRIBUTION_TYPE", "선호하는 투자 방식을 선택해 주세요", "SINGLE_CHOICE", '["LUMP_SUM", "DCA"]', 4),
        ("LUMP_SUM_AMOUNT", "일시금 금액", "NUMBER", None, 5),
        ("MONTHLY_AMOUNT", "월 투자 가능 금액", "NUMBER", None, 6),
        ("MAX_HOLDINGS", "최대 몇 개의 종목을 보유하고 싶으신가요?", "NUMBER", None, 7),
        ("DIVIDEND_PREF", "배당 선호 정도는?", "SINGLE_CHOICE", '["HIGH", "MID", "LOW"]', 8),
        ("ACCOUNT_TYPE", "계좌 유형", "TEXT", None, 9)
    ]
    
    for code, question_text, answer_type, options_json, order_no in questions:
        session.execute(
            text('''
                INSERT INTO survey_questions (code, question_text, answer_type, options_json, order_no, created_at, updated_at)
                VALUES (:code, :question_text, :answer_type, :options_json, :order_no, NOW(), NOW())
            '''),
            {
                'code': code,
                'question_text': question_text,
                'answer_type': answer_type,
                'options_json': options_json,
                'order_no': order_no
            }
        )
    
    session.commit()
    print(f"Survey questions seeded successfully! Total: {len(questions)} questions")

if __name__ == "__main__":
    with SessionLocal() as session:
        seed_survey_questions(session)
        print("Survey questions seeded successfully.")