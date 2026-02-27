from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import sqlite3
import json
import hashlib
import os
from datetime import datetime
from typing import Optional, Dict, Any
import uvicorn
from routers import survey

app = FastAPI(title="SeedUp API Server")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 데이터베이스 경로를 절대 경로로 설정
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'seedup.db'))

# Pydantic 모델 정의
class SignupRequest(BaseModel):
    email: str
    password: str
    username: str
    name: Optional[str] = ""
    phone: Optional[str] = ""
    dob: Optional[str] = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class SurveyRequest(BaseModel):
    user_id: int
    survey_data: Dict[str, Any]


def init_db():
    """데이터베이스 초기화"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # users 테이블이 존재하는지 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    users_exists = cursor.fetchone() is not None

    if users_exists:
        # 기존 users 테이블의 컬럼 확인
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # dob 컬럼이 있는지 확인
        if 'dob' in columns or 'birth_date' not in columns:
            print("Migrating users table to remove 'dob' column...")
            
            # 임시 테이블 삭제 (이전 실행에서 남아있을 수 있음)
            cursor.execute("DROP TABLE IF EXISTS users_new")
            
            # 새로운 스키마로 임시 테이블 생성
            cursor.execute('''
                CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    name TEXT,
                    phone TEXT,
                    birth_date TEXT,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 기존 데이터 복사 (birth_date가 있으면 그대로, dob가 있으면 변환)
            if 'birth_date' in columns:
                cursor.execute('''
                    INSERT INTO users_new (id, email, username, name, phone, birth_date, password, created_at)
                    SELECT id, email, username, name, phone, birth_date, password, created_at FROM users
                ''')
            elif 'dob' in columns:
                cursor.execute('''
                    INSERT INTO users_new (id, email, username, name, phone, birth_date, password, created_at)
                    SELECT id, email, username, name, phone, dob, password, created_at FROM users
                ''')
            else:
                cursor.execute('''
                    INSERT INTO users_new (id, email, username, name, phone, password, created_at)
                    SELECT id, email, username, name, phone, password, created_at FROM users
                ''')

            # 기존 테이블 삭제 및 새 테이블 이름 변경
            cursor.execute('DROP TABLE users')
            cursor.execute('ALTER TABLE users_new RENAME TO users')
            print("users table migration completed!")
    else:
        # users 테이블이 없으면 새로 생성
        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                name TEXT,
                phone TEXT,
                birth_date TEXT,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("users table created!")

    # survey_questions 테이블이 존재하는지 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='survey_questions'")
    sq_exists = cursor.fetchone() is not None

    if not sq_exists:
        # survey_questions 테이블 생성
        cursor.execute('''
            CREATE TABLE survey_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                question_text TEXT NOT NULL,
                answer_type TEXT NOT NULL,
                options_json TEXT,
                order_no INTEGER,
                parent_question_id INTEGER,
                show_if_question_id INTEGER,
                show_if_value TEXT,
                is_required INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_question_id) REFERENCES survey_questions(id),
                FOREIGN KEY (show_if_question_id) REFERENCES survey_questions(id)
            )
        ''')
        print("survey_questions table created!")

    # survey_answers 테이블 재생성 (UNIQUE 제약 완전 제거를 위해 무조건 DROP)
    print("Recreating survey_answers table without UNIQUE constraint...")
    cursor.execute('DROP TABLE IF EXISTS survey_answers')
    cursor.execute('''
        CREATE TABLE survey_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            value_text TEXT,
            value_number REAL,
            value_choice TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (question_id) REFERENCES survey_questions(id)
        )
    ''')
    print("survey_answers table recreated successfully!")

    conn.commit()
    conn.close()
    print("Database initialized successfully")

def hash_password(password):
    """비밀번호 해싱 - SHA256 사용"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_db_connection():
    """데이터베이스 연결"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get('/api/check_username')
async def check_username(username: str = Query(..., description="Username to check")):
    """username(ID) 중복체크"""
    username = username.strip()
    if not username:
        raise HTTPException(status_code=400, detail={'success': False, 'message': 'username is required'})

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        return {'success': True, 'exists': bool(user)}
    except Exception as e:
        print(f"Error in check_username: {str(e)}")
        raise HTTPException(status_code=500, detail={'success': False, 'message': 'error checking username'})

@app.post('/api/signup')
async def signup(data: SignupRequest):
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

        # 데이터베이스에 사용자 저장
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 이미 존재하는 username 또는 email 확인
            cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
            existing = cursor.fetchone()
            if existing:
                print(f"[SIGNUP] 중복 사용자 발견 - username: {username}, email: {email}")
                raise HTTPException(
                    status_code=409,
                    detail={'success': False, 'message': '이미 사용 중인 이메일 또는 ID 입니다.'}
                )

            print(f"[SIGNUP] DB에 사용자 삽입 시도")
            cursor.execute('''
                INSERT INTO users (email, username, name, phone, birth_date, password)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (email, username, name, phone, dob, hashed_password))

            conn.commit()
            user_id = cursor.lastrowid
            
            print(f"[SIGNUP] 회원가입 성공 - user_id: {user_id}")

            return {
                'success': True,
                'message': '회원가입이 완료되었습니다.',
                'user_id': user_id,
                'email': email,
                'username': username
            }

        except sqlite3.IntegrityError as e:
            print(f"[SIGNUP] DB IntegrityError: {str(e)}")
            raise HTTPException(
                status_code=409,
                detail={'success': False, 'message': '이미 가입된 이메일 또는 ID입니다.'}
            )
        finally:
            conn.close()
    
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
async def login(data: LoginRequest):
    """로그인 API"""
    try:
        email = data.email.strip()
        password = data.password

        conn = get_db_connection()
        cursor = conn.cursor()

        # email로 사용자 검색
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()

        conn.close()

        if user:
            # 비밀번호 검증 - SHA256 해시 비교
            password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            if password_hash == user['password']:
                print(f"로그인 성공 - user_id: {user['id']}, email: {user['email']}")
                return {
                    'success': True,
                    'message': '로그인되었습니다.',
                    'user_id': user['id'],
                    'email': user['email'],
                    'username': user['username']
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
async def get_user(user_id: int):
    """사용자 정보 조회 API"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, email, created_at FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        conn.close()
        
        if user:
            return {
                'success': True,
                'user': {
                    'id': user['id'],
                    'email': user['email'],
                    'created_at': user['created_at']
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
async def save_survey(data: dict):
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

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # user_id 검증: users 테이블에 존재하는지 확인
        cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
        user_exists = cursor.fetchone()
        
        if not user_exists:
            conn.close()
            print(f"[ERROR] User validation failed - user_id {user_id} does not exist")
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": f"유효하지 않은 사용자 ID입니다: {user_id}"}
            )
        
        print(f"[DEBUG] User validation passed - user_id {user_id} exists")

        try:
            for answer in answers:
                question_id = answer.get("question_id")
                value_text = answer.get("value_text")
                value_number = answer.get("value_number")
                value_choice = answer.get("value_choice")

                # question_id 검증
                cursor.execute('SELECT id, answer_type, options_json FROM survey_questions WHERE id = ?', (question_id,))
                question_row = cursor.fetchone()

                if not question_row:
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "message": f"Invalid question_id: {question_id}"}
                    )

                question_id, answer_type, options_json = question_row

                # 타입 검증 및 값 매핑
                if answer_type == "TEXT":
                    if value_text is None:
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"TEXT 타입의 질문에 value_text가 필요합니다. (question_id: {question_id})"}
                        )
                elif answer_type == "NUMBER":
                    if value_number is None:
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"NUMBER 타입의 질문에 value_number가 필요합니다. (question_id: {question_id})"}
                        )
                elif answer_type == "SINGLE_CHOICE":
                    if value_choice is None:
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"SINGLE_CHOICE 타입의 질문에 value_choice가 필요합니다. (question_id: {question_id})"}
                        )
                    # options_json 파싱
                    try:
                        valid_options = json.loads(options_json) if options_json else []
                    except json.JSONDecodeError:
                        valid_options = []
                    
                    if value_choice not in valid_options:
                        raise HTTPException(
                            status_code=400,
                            detail={"success": False, "message": f"SINGLE_CHOICE 타입의 질문에 유효하지 않은 값입니다. (question_id: {question_id}, value: {value_choice}, valid_options: {valid_options})"}
                        )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail={"success": False, "message": f"알 수 없는 answer_type: {answer_type}"}
                    )

                # Insert new row for each answer
                print(f"[DEBUG] Inserting answer - user_id: {user_id}, question_id: {question_id}, value_text: {value_text}, value_number: {value_number}, value_choice: {value_choice}")
                cursor.execute('''
                    INSERT INTO survey_answers (user_id, question_id, value_text, value_number, value_choice, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''', (user_id, question_id, value_text, value_number, value_choice))

            conn.commit()
            print(f"Survey answers saved for user_id: {user_id}")

            return {
                "success": True,
                "message": "설문조사 답변이 저장되었습니다."
            }

        finally:
            conn.close()

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error in save_survey: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "message": "설문조사 저장 중 오류가 발생했습니다."}
        )

@app.get('/api/health')
async def health():
    """헬스 체크 API"""
    return {
        'status': 'healthy',
        'message': 'SeedUp API Server is running'
    }

# Include survey router
app.include_router(survey.router, prefix="/survey", tags=["Survey"])

if __name__ == '__main__':
    # 데이터베이스 초기화
    init_db()
    
    # FastAPI 앱 실행
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
