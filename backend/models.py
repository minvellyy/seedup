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
    investment_type = Column(String(50))  # 투자성향 (안정형, 위험중립형, 적극투자형, 공격투자형 등)
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

# ═══ 챗봇 관련 모델 ═══════════════════════════════════════════════════════════

class ChatSession(Base):
    """챗봇 대화 세션"""
    __tablename__ = 'chat_sessions'
    
    id = Column(String(255), primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    title = Column(String(255))  # 대화 제목 (첫 메시지 기반)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    user = relationship("User")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    """챗봇 대화 메시지"""
    __tablename__ = 'chat_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.id', ondelete='CASCADE'))
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    message_metadata = Column(Text)  # JSON 형태로 추가 정보 저장 (DB의 실제 컬럼명)
    created_at = Column(DateTime, server_default=func.now())
    
    session = relationship("ChatSession", back_populates="messages")

# ═══ 고객센터 문의 관련 모델 ═══════════════════════════════════════════════════

class CustomerInquiry(Base):
    """고객센터 1:1 문의"""
    __tablename__ = 'customer_inquiries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    inquiry_type = Column(String(50), nullable=False)  # 문의 유형 (서비스 이용, 포트폴리오, 계정/로그인 등)
    title = Column(String(200), nullable=False)  # 문의 제목
    content = Column(Text, nullable=False)  # 문의 내용
    status = Column(String(20), default='pending')  # 상태: pending(답변 대기), completed(답변 완료)
    answer = Column(Text)  # 관리자 답변
    answered_at = Column(DateTime)  # 답변 일시
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    user = relationship("User")
