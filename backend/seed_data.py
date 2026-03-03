from sqlalchemy.orm import Session
from models import SurveyQuestion
from database import SessionLocal

def seed_survey_questions(session: Session):
    questions = [
        SurveyQuestion(
            code="INVEST_GOAL",
            text="투자 목적은 무엇인가요?",
            answer_type="TEXT",
            order_no=1
        ),
        SurveyQuestion(
            code="TARGET_HORIZON",
            text="목표 시점은 언제인가요?",
            answer_type="TEXT",
            order_no=2
        ),
        SurveyQuestion(
            code="TARGET_AMOUNT",
            text="목표 금액은 어느 정도인가요?",
            answer_type="NUMBER",
            order_no=3
        ),
        SurveyQuestion(
            code="CONTRIBUTION_TYPE",
            text="선호하는 투자 방식을 선택해 주세요",
            answer_type="SINGLE_CHOICE",
            options_json='["LUMP_SUM", "DCA"]',
            order_no=4
        ),
        SurveyQuestion(
            code="LUMP_SUM_AMOUNT",
            text="일시금 금액",
            answer_type="NUMBER",
            order_no=5,
            parent_question_id=4,
            show_if_question_id=4,
            show_if_value="LUMP_SUM"
        ),
        SurveyQuestion(
            code="MONTHLY_AMOUNT",
            text="월 투자 가능 금액",
            answer_type="NUMBER",
            order_no=6,
            parent_question_id=4,
            show_if_question_id=4,
            show_if_value="DCA"
        ),
        SurveyQuestion(
            code="MAX_HOLDINGS",
            text="최대 몇 개의 종목을 보유하고 싶으신가요?",
            answer_type="NUMBER",
            order_no=7
        ),
        SurveyQuestion(
            code="DIVIDEND_PREF",
            text="배당 선호 정도는?",
            answer_type="SINGLE_CHOICE",
            options_json='["HIGH", "MID", "LOW"]',
            order_no=8
        ),
        SurveyQuestion(
            code="ACCOUNT_TYPE",
            text="계좌 유형",
            answer_type="TEXT",
            order_no=9
        )
    ]

    session.bulk_save_objects(questions)
    session.commit()

if __name__ == "__main__":
    with SessionLocal() as session:
        seed_survey_questions(session)
        print("Survey questions seeded successfully.")