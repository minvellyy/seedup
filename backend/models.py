from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float, DateTime, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), nullable=False)
    name = Column(String(100))
    phone = Column(String(20))
    birth_date = Column(String(20))
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)

    answers = relationship("SurveyAnswer", back_populates="user")

class SurveyQuestion(Base):
    __tablename__ = 'survey_questions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=True)
    question_text = Column(Text, nullable=False)
    answer_type = Column(String(50), nullable=False)
    options_json = Column(Text)
    order_no = Column(Integer, nullable=True)
    parent_question_id = Column(Integer, ForeignKey('survey_questions.id', ondelete='CASCADE'))
    show_if_question_id = Column(Integer, ForeignKey('survey_questions.id', ondelete='CASCADE'))
    show_if_value = Column(String(255))
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)

    parent_question = relationship(
        "SurveyQuestion",
        remote_side=[id],
        foreign_keys=[parent_question_id],
        back_populates="child_questions"
    )
    child_questions = relationship(
        "SurveyQuestion",
        foreign_keys=[parent_question_id],
        back_populates="parent_question"
    )
    answers = relationship("SurveyAnswer", back_populates="question")

class SurveyAnswer(Base):
    __tablename__ = 'survey_answers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    question_id = Column(Integer, ForeignKey('survey_questions.id', ondelete='CASCADE'))
    value_text = Column(Text)
    value_number = Column(Float)
    value_choice = Column(String(255))
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)

    user = relationship("User", back_populates="answers")
    question = relationship("SurveyQuestion", back_populates="answers")
