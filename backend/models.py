from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float, DateTime, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False)
    username = Column(String, nullable=False)
    name = Column(String)
    phone = Column(String)
    birth_date = Column(String)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.datetime('now'), nullable=False)
    updated_at = Column(DateTime, server_default=func.datetime('now'), onupdate=func.datetime('now'), nullable=False)

    answers = relationship("SurveyAnswer", back_populates="user")

class SurveyQuestion(Base):
    __tablename__ = 'survey_questions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False)
    text = Column(Text, nullable=False)
    answer_type = Column(String, nullable=False)
    options_json = Column(Text)
    order_no = Column(Integer, nullable=False)
    parent_question_id = Column(Integer, ForeignKey('survey_questions.id', ondelete='CASCADE'))
    show_if_question_id = Column(Integer, ForeignKey('survey_questions.id', ondelete='CASCADE'))
    show_if_value = Column(String)
    created_at = Column(DateTime, server_default=func.datetime('now'), nullable=False)
    updated_at = Column(DateTime, server_default=func.datetime('now'), onupdate=func.datetime('now'), nullable=False)

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
    value_choice = Column(String)
    created_at = Column(DateTime, server_default=func.datetime('now'), nullable=False)
    updated_at = Column(DateTime, server_default=func.datetime('now'), onupdate=func.datetime('now'), nullable=False)

    user = relationship("User", back_populates="answers")
    question = relationship("SurveyQuestion", back_populates="answers")
