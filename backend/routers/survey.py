from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import SurveyQuestion, SurveyAnswer

router = APIRouter()

class AnswerCreate(BaseModel):
    question_id: int
    value_text: str | None = None
    value_number: float | None = None
    value_choice: str | None = None

@router.get("/survey/questions")
def get_survey_questions(db: Session = Depends(get_db)):
    questions = db.query(SurveyQuestion).all()
    return questions

@router.post("/survey/answers")
def save_survey_answer(answer: AnswerCreate, user_id: int, db: Session = Depends(get_db)):
    existing_answer = db.query(SurveyAnswer).filter_by(user_id=user_id, question_id=answer.question_id).first()
    if existing_answer:
        existing_answer.value_text = answer.value_text
        existing_answer.value_number = answer.value_number
        existing_answer.value_choice = answer.value_choice
    else:
        new_answer = SurveyAnswer(
            user_id=user_id,
            question_id=answer.question_id,
            value_text=answer.value_text,
            value_number=answer.value_number,
            value_choice=answer.value_choice
        )
        db.add(new_answer)
    db.commit()
    return {"message": "Answer saved successfully"}

@router.get("/survey/answers/me")
def get_my_answers(user_id: int, db: Session = Depends(get_db)):
    answers = db.query(SurveyAnswer).filter_by(user_id=user_id).all()
    result = []
    for answer in answers:
        question = db.query(SurveyQuestion).filter_by(id=answer.question_id).first()
        if question is None:
            print(f"Warning: Question with id {answer.question_id} not found in survey_questions table.")
            continue
        result.append({
            "question": question.question_text,
            "answer": {
                "value_text": answer.value_text,
                "value_number": answer.value_number,
                "value_choice": answer.value_choice
            }
        })
    return result