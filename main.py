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

app = FastAPI(title="SeedUp API Server")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 데이터베이스 경로
DB_PATH = 'seedup.db'

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
    # create DB file and ensure tables/columns exist
    first_init = False
    if not os.path.exists(DB_PATH):
        first_init = True

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # users 테이블 생성 (필요한 컬럼 포함)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE,
            name TEXT,
            phone TEXT,
            dob TEXT,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 설문조사 답변 테이블 생성
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS survey_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            survey_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    # Ensure any newer columns exist on older DBs
    try:
        cursor.execute("PRAGMA table_info(users)")
        cols = [r[1] for r in cursor.fetchall()]
        needed = {
            'username': "ALTER TABLE users ADD COLUMN username TEXT",
            'name': "ALTER TABLE users ADD COLUMN name TEXT",
            'phone': "ALTER TABLE users ADD COLUMN phone TEXT",
            'dob': "ALTER TABLE users ADD COLUMN dob TEXT",
            'updated_at': "ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        }
        for col, stmt in needed.items():
            if col not in cols:
                try:
                    cursor.execute(stmt)
                    conn.commit()
                except Exception:
                    pass
        # ensure unique index on username (can't add UNIQUE via ALTER COLUMN in sqlite)
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            conn.commit()
        except Exception:
            pass
    except Exception:
        pass

    conn.close()
    if first_init:
        print("Database initialized successfully")

def hash_password(password):
    """비밀번호 해싱"""
    return hashlib.sha256(password.encode()).hexdigest()

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
        email = data.email.strip()
        password = data.password
        username = data.username.strip()
        name = data.name.strip() if data.name else ""
        phone = data.phone.strip() if data.phone else ""
        dob = data.dob.strip() if data.dob else ""

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

        # 비밀번호 해싱
        hashed_password = hash_password(password)

        # 데이터베이스에 사용자 저장 (중복 체크: 이메일/username)
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 이미 존재하는 username 또는 email 확인
            cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
            existing = cursor.fetchone()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail={'success': False, 'message': '이미 사용 중인 이메일 또는 ID 입니다.'}
                )

            cursor.execute('''
                INSERT INTO users (email, username, name, phone, dob, password)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (email, username, name, phone, dob, hashed_password))

            conn.commit()
            user_id = cursor.lastrowid

            return {
                'success': True,
                'message': '회원가입이 완료되었습니다.',
                'user_id': user_id,
                'email': email,
                'username': username
            }

        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail={'success': False, 'message': '이미 가입된 이메일 또는 ID입니다.'}
            )
        finally:
            conn.close()
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in signup: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': '회원가입 중 오류가 발생했습니다.'}
        )

@app.post('/api/login')
async def login(data: LoginRequest):
    """로그인 API"""
    try:
        email = data.email.strip()
        password = data.password
        hashed_password = hash_password(password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        conn.close()
        
        if user and user['password'] == hashed_password:
            return {
                'success': True,
                'message': '로그인되었습니다.',
                'user_id': user['id'],
                'email': user['email']
            }
        else:
            raise HTTPException(
                status_code=401,
                detail={'success': False, 'message': '이메일 또는 비밀번호가 일치하지 않습니다.'}
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
async def save_survey(data: SurveyRequest):
    """설문조사 답변 저장 API"""
    try:
        user_id = data.user_id
        survey_data = json.dumps(data.survey_data)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO survey_responses (user_id, survey_data)
                VALUES (?, ?)
            ''', (user_id, survey_data))
            
            conn.commit()
            response_id = cursor.lastrowid
            
            return {
                'success': True,
                'message': '설문조사 답변이 저장되었습니다.',
                'response_id': response_id
            }
        finally:
            conn.close()
    
    except Exception as e:
        print(f"Error in save_survey: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={'success': False, 'message': '설문조사 저장 중 오류가 발생했습니다.'}
        )

@app.get('/api/health')
async def health():
    """헬스 체크 API"""
    return {
        'status': 'healthy',
        'message': 'SeedUp API Server is running'
    }

if __name__ == '__main__':
    # 데이터베이스 초기화
    init_db()
    
    # FastAPI 앱 실행
    print("Starting SeedUp API Server on http://localhost:5000")
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")
