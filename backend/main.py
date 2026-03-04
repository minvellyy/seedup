from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import engine, get_db, SessionLocal
from typing import Optional, Dict, Any
import hashlib
import json
import uvicorn
from datetime import datetime
from routers import survey, dashboard, recommendations
from models import Base, SurveyQuestion

# Pydantic 모델 정의
class SignupRequest(BaseModel):
    email: str
    password: str
    username: str
    name: Optional[str] = ""
    phone: Optional[str] = ""
    dob: Optional[str] = ""

class LoginRequest(BaseModel):
    username: str
    password: str

class SurveyRequest(BaseModel):
    user_id: int
    survey_data: Dict[str, Any]

# 유틸리티 함수
def hash_password(password):
    """비밀번호 해싱 - SHA256 사용"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_survey_questions():
    """설문 질문 초기화 - Raw SQL 사용"""
    db = SessionLocal()
    try:
        # 이미 데이터가 있는지 확인
        result = db.execute(text('SELECT COUNT(*) FROM survey_questions'))
        count = result.fetchone()[0]
        if count > 0:
            print(f"Survey questions already exist ({count} questions), skipping initialization")
            return
        
        print("Initializing survey questions with Raw SQL...")
        
        # Raw SQL로 직접 삽입
        questions_sql = [
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
        
        for code, question_text, answer_type, options_json, order_no in questions_sql:
            db.execute(
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
        
        db.commit()
        print(f"Survey questions initialized successfully! Total: {len(questions_sql)} questions")
    except Exception as e:
        print(f"Error initializing survey questions: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

app = FastAPI(title="SeedUp API Server")

# 앱 시작 시 설문 질문 초기화
@app.on_event("startup")
async def startup_event():
    print("="*60)
    print("Starting up application...")
    print("="*60)
    try:
        # 테이블 생성
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully!")
        
        # 설문 질문 초기화
        print("Initializing survey questions...")
        init_survey_questions()
        print("Application startup complete!")
    except Exception as e:
        print(f"Error during startup: {str(e)}")
        import traceback
        traceback.print_exc()
    print("="*60)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get('/api/check_username')
async def check_username(username: str = Query(..., description="Username to check"), db: Session = Depends(get_db)):
    """username(ID) 중복체크"""
    username = username.strip()
    if not username:
        raise HTTPException(status_code=400, detail={'success': False, 'message': 'username is required'})

    try:
        result = db.execute(text('SELECT id FROM users WHERE username = :username'), {'username': username})
        user = result.fetchone()
        return {'success': True, 'exists': bool(user)}
    except Exception as e:
        print(f"Error in check_username: {str(e)}")
        raise HTTPException(status_code=500, detail={'success': False, 'message': 'error checking username'})

@app.post('/api/signup')
async def signup(data: SignupRequest, db: Session = Depends(get_db)):
    """회원가입 API"""
    try:
        print(f"[SIGNUP] 회원가입 요청 받음: {data.email}, {data.username}")
        
        email = data.email.strip()
        password = data.password
        username = data.username.strip()
        name = data.name.strip() if data.name else ""
        phone = data.phone.strip() if data.phone else ""
        dob = data.dob.strip() if data.dob else ""

        print(f"[SIGNUP] 데이터 정리 완료 - email: {email}, username: {username}")

        # 이메일 검증
        if '@' not in email:
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'message': '유효한 이메일을 입력해주세요.'}
            )

        # 비밀번호 길이 검증
        if len(password) < 6:
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'message': '비밀번호는 6자 이상이어야 합니다.'}
            )

        # username 검증
        if not username:
            raise HTTPException(
                status_code=400,
                detail={'success': False, 'message': 'ID를 입력해주세요.'}
            )

        print(f"[SIGNUP] 유효성 검증 통과")

        # 비밀번호 해싱
        hashed_password = hash_password(password)
        print(f"[SIGNUP] 비밀번호 해싱 완료")

        try:
            # 이미 존재하는 username 또는 email 확인
            result = db.execute(
                text('SELECT id FROM users WHERE username = :username OR email = :email'),
                {'username': username, 'email': email}
            )
            existing = result.fetchone()
            if existing:
                print(f"[SIGNUP] 중복 사용자 발견 - username: {username}, email: {email}")
                raise HTTPException(
                    status_code=409,
                    detail={'success': False, 'message': '이미 사용 중인 이메일 또는 ID 입니다.'}
                )

            print(f"[SIGNUP] DB에 사용자 삽입 시도")
            db.execute(
                text('''
                    INSERT INTO users (email, username, name, phone, birth_date, password)
                    VALUES (:email, :username, :name, :phone, :dob, :password)
                '''),
                {'email': email, 'username': username, 'name': name, 'phone': phone, 'dob': dob, 'password': hashed_password}
            )
            db.commit()

            # MySQL에서 마지막 삽입된 ID 가져오기
            result = db.execute(text('SELECT LAST_INSERT_ID()'))
            user_id = result.fetchone()[0]
            
            print(f"[SIGNUP] 회원가입 성공 - user_id: {user_id}")

            return {
                'success': True,
                'message': '회원가입이 완료되었습니다.',
                'user_id': user_id,
                'email': email,
                'username': username
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            print(f"[SIGNUP] DB Error: {str(e)}")
            raise HTTPException(
                status_code=409,
                detail={'success': False, 'message': '이미 가입된 이메일 또는 ID입니다.'}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SIGNUP ERROR] {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': f'회원가입 중 오류가 발생했습니다: {str(e)}'}
        )

@app.post('/api/login')
async def login(data: LoginRequest, db: Session = Depends(get_db)):
    """로그인 API"""
    try:
        username = data.username.strip()
        password = data.password

        # username으로 사용자 검색
        result = db.execute(
            text('SELECT id, email, username, password, investment_type FROM users WHERE username = :username'),
            {'username': username}
        )
        user = result.fetchone()

        if user:
            # 비밀번호 검증 - SHA256 해시 비교
            password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            if password_hash == user[3]:  # user[3]은 password 컬럼
                print(f"로그인 성공 - user_id: {user[0]}, username: {user[2]}")
                return {
                    'success': True,
                    'message': '로그인되었습니다.',
                    'user_id': user[0],
                    'email': user[1],
                    'username': user[2],
                    'investment_type': user[4]  # 투자성향 추가
                }
        
        # 사용자가 없거나 비밀번호가 일치하지 않는 경우
        raise HTTPException(
            status_code=401,
            detail={'success': False, 'message': 'ID 또는 비밀번호가 일치하지 않습니다.'}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in login: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': '로그인 중 오류가 발생했습니다.'}
        )

@app.get('/api/users/{user_id}')
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """사용자 정보 조회 API"""
    try:
        result = db.execute(
            text('SELECT id, email, created_at FROM users WHERE id = :user_id'),
            {'user_id': user_id}
        )
        user = result.fetchone()
        
        if user:
            return {
                'success': True,
                'user': {
                    'id': user[0],
                    'email': user[1],
                    'created_at': str(user[2])
                }
            }
        else:
            raise HTTPException(
                status_code=404,
                detail={'success': False, 'message': '사용자를 찾을 수 없습니다.'}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_user: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': '사용자 조회 중 오류가 발생했습니다.'}
        )

@app.post('/api/survey')
async def save_survey(data: dict, db: Session = Depends(get_db)):
    """설문조사 답변 저장 API"""
    try:
        print("="*50)
        print(f"[DEBUG] Received raw payload: {data}")
        print(f"[DEBUG] Payload type: {type(data)}")
        user_id = data.get("user_id")
        answers = data.get("answers", [])
        
        print(f"[DEBUG] Extracted user_id: {user_id} (type: {type(user_id)})")
        print(f"[DEBUG] Extracted answers: {answers}")
        print("="*50)

        if not user_id or not answers:
            print(f"[ERROR] Validation failed - user_id: {user_id}, answers length: {len(answers)}")
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "user_id와 answers는 필수입니다."}
            )

        # user_id 검증: users 테이블에 존재하는지 확인
        result = db.execute(text('SELECT id FROM users WHERE id = :user_id'), {'user_id': user_id})
        user_exists = result.fetchone()
        
        if not user_exists:
            print(f"[ERROR] User validation failed - user_id {user_id} does not exist")
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": f"유효하지 않은 사용자 ID입니다: {user_id}"}
            )
        
        print(f"[DEBUG] User validation passed - user_id {user_id} exists")

        try:
            for idx, answer in enumerate(answers):
                print(f"\n[DEBUG] Processing answer {idx + 1}/{len(answers)}: {answer}")
                question_id = answer.get("question_id")
                question_code = answer.get("question_code")
                value_text = answer.get("value_text")
                value_number = answer.get("value_number")
                value_choice = answer.get("value_choice")
                
                print(f"[DEBUG] question_code: {question_code}, question_id: {question_id}")
                print(f"[DEBUG] value_text: {value_text}, value_number: {value_number}, value_choice: {value_choice}")

                # question_id 또는 question_code로 질문 찾기
                if question_code:
                    print(f"[DEBUG] Searching by question_code: {question_code}")
                    result = db.execute(
                        text('SELECT id, answer_type, options_json FROM survey_questions WHERE code = :code'),
                        {'code': question_code}
                    )
                elif question_id:
                    print(f"[DEBUG] Searching by question_id: {question_id}")
                    result = db.execute(
                        text('SELECT id, answer_type, options_json FROM survey_questions WHERE id = :question_id'),
                        {'question_id': question_id}
                    )
                else:
                    print(f"[ERROR] No question_id or question_code provided")
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "message": "question_id 또는 question_code가 필요합니다."}
                    )
                
                question_row = result.fetchone()
                print(f"[DEBUG] Question found: {question_row}")

                if not question_row:
                    print(f"[ERROR] Question not found for code/id: {question_code or question_id}")
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "message": f"Invalid question_id/code: {question_id or question_code}"}
                    )

                q_id, answer_type, options_json = question_row
                print(f"[DEBUG] Question details - id: {q_id}, type: {answer_type}, options: {options_json}")

                q_id, answer_type, options_json = question_row
                print(f"[DEBUG] Question details - id: {q_id}, type: {answer_type}, options: {options_json}")

                # 타입 검증 및 값 매핑
                print(f"[DEBUG] Validating answer type: {answer_type}")
                if answer_type == "TEXT":
                    if value_text is None or value_text == "":
                        print(f"[ERROR] TEXT type question missing value_text")
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"TEXT 타입의 질문에 value_text가 필요합니다. (question_id: {q_id})"}
                        )
                    print(f"[DEBUG] TEXT validation passed")
                elif answer_type == "NUMBER":
                    if value_number is None:
                        print(f"[ERROR] NUMBER type question missing value_number")
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"NUMBER 타입의 질문에 value_number가 필요합니다. (question_id: {q_id})"}
                        )
                    print(f"[DEBUG] NUMBER validation passed, value: {value_number}")
                elif answer_type == "SINGLE_CHOICE":
                    if value_choice is None or value_choice == "":
                        print(f"[ERROR] SINGLE_CHOICE type question missing value_choice")
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"SINGLE_CHOICE 타입의 질문에 value_choice가 필요합니다. (question_id: {q_id})"}
                        )
                    # options_json 파싱
                    try:
                        valid_options = json.loads(options_json) if options_json else []
                    except json.JSONDecodeError:
                        valid_options = []
                    
                    print(f"[DEBUG] Checking if '{value_choice}' in {valid_options}")
                    if value_choice not in valid_options:
                        print(f"[ERROR] Invalid choice value")
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"SINGLE_CHOICE 타입의 질문에 유효하지 않은 값입니다. (question_id: {q_id}, value: {value_choice}, valid_options: {valid_options})"}
                        )
                    print(f"[DEBUG] SINGLE_CHOICE validation passed")
                else:
                    print(f"[ERROR] Unknown answer type: {answer_type}")
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "message": f"알 수 없는 answer_type: {answer_type}"}
                    )

                # Insert new row for each answer
                print(f"[DEBUG] Inserting answer - user_id: {user_id}, question_id: {q_id}, value_text: {value_text}, value_number: {value_number}, value_choice: {value_choice}")
                db.execute(
                    text('''
                        INSERT INTO survey_answers (user_id, question_id, value_text, value_number, value_choice, created_at, updated_at)
                        VALUES (:user_id, :question_id, :value_text, :value_number, :value_choice, NOW(), NOW())
                    '''),
                    {
                        'user_id': user_id,
                        'question_id': q_id,
                        'value_text': value_text,
                        'value_number': value_number,
                        'value_choice': value_choice
                    }
                )

            db.commit()
            print(f"Survey answers saved for user_id: {user_id}")

            return {
                "success": True,
                "message": "설문조사 답변이 저장되었습니다."
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            print(f"Error saving survey answers: {str(e)}")
            raise

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error in save_survey: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "설문조사 저장 중 오류가 발생했습니다."}
        )

@app.post('/api/logout')
async def logout():
    """로그아웃 API"""
    # 클라이언트 측에서 localStorage를 클리어하므로 서버에서는 로그만 남김
    print(f"[LOGOUT] 로그아웃 요청")
    return {
        'success': True,
        'message': '로그아웃되었습니다.'
    }

@app.post('/api/init-survey-questions')
async def manual_init_survey_questions(db: Session = Depends(get_db)):
    """설문 질문 수동 초기화 API - Raw SQL 사용"""
    try:
        # 기존 데이터 확인
        result = db.execute(text('SELECT COUNT(*) FROM survey_questions'))
        count = result.fetchone()[0]
        if count > 0:
            return {
                'success': True,
                'message': '설문 질문이 이미 존재합니다.',
                'count': count
            }
        
        # Raw SQL로 설문 질문 생성
        questions_sql = [
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
        
        for code, question_text, answer_type, options_json, order_no in questions_sql:
            db.execute(
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
        
        db.commit()
        
        return {
            'success': True,
            'message': '설문 질문이 성공적으로 생성되었습니다.',
            'count': len(questions_sql)
        }
    except Exception as e:
        db.rollback()
        print(f"Error initializing survey questions: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': f'설문 질문 초기화 중 오류가 발생했습니다: {str(e)}'}
        )

@app.get('/api/survey-questions')
async def get_survey_questions(db: Session = Depends(get_db)):
    """설문 질문 목록 조회 API - Raw SQL 사용"""
    try:
        result = db.execute(text('SELECT id, code, question_text, answer_type, options_json, order_no FROM survey_questions ORDER BY order_no'))
        questions = result.fetchall()
        
        return {
            'success': True,
            'count': len(questions),
            'questions': [
                {
                    'id': q[0],
                    'code': q[1],
                    'question_text': q[2],
                    'answer_type': q[3],
                    'options_json': q[4],
                    'order_no': q[5]
                }
                for q in questions
            ]
        }
    except Exception as e:
        print(f"Error getting survey questions: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': f'설문 질문 조회 중 오류가 발생했습니다: {str(e)}'}
        )

class InvestmentTypeRequest(BaseModel):
    user_id: int
    investment_type: str

@app.post('/api/users/{user_id}/investment-type')
async def update_investment_type(user_id: int, data: InvestmentTypeRequest, db: Session = Depends(get_db)):
    """사용자 투자성향 저장 API"""
    try:
        # user_id 검증
        result = db.execute(
            text('SELECT id FROM users WHERE id = :user_id'),
            {'user_id': user_id}
        )
        user = result.fetchone()
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail={'success': False, 'message': '사용자를 찾을 수 없습니다.'}
            )
        
        # 투자성향 업데이트
        db.execute(
            text('UPDATE users SET investment_type = :investment_type WHERE id = :user_id'),
            {'investment_type': data.investment_type, 'user_id': user_id}
        )
        db.commit()
        
        print(f"투자성향 저장 성공 - user_id: {user_id}, investment_type: {data.investment_type}")
        return {
            'success': True,
            'message': '투자성향이 저장되었습니다.',
            'investment_type': data.investment_type
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating investment type: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': '투자성향 저장 중 오류가 발생했습니다.'}
        )

@app.get('/api/health')
async def health():
    """헬스 체크 API"""
    return {
        'status': 'healthy',
        'message': 'SeedUp API Server is running'
    }

# Include routers
app.include_router(survey.router, prefix="/survey", tags=["Survey"])
app.include_router(dashboard.router)
app.include_router(recommendations.router)

if __name__ == '__main__':
    # FastAPI 앱 실행
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
