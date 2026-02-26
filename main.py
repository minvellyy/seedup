from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import hashlib
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 데이터베이스 경로
DB_PATH = 'seedup.db'

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


@app.route('/api/check_username', methods=['GET'])
def check_username():
    """username(ID) 중복체크"""
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({'success': False, 'message': 'username is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        return jsonify({'success': True, 'exists': bool(user)}), 200
    except Exception as e:
        print(f"Error in check_username: {str(e)}")
        return jsonify({'success': False, 'message': 'error checking username'}), 500

@app.route('/api/signup', methods=['POST'])
def signup():
    """회원가입 API"""
    try:
        data = request.get_json()
        
        if not data or not data.get('email') or not data.get('password') or not data.get('username'):
            return jsonify({
                'success': False,
                'message': '이메일, 비밀번호, ID는 필수입니다.'
            }), 400

        email = data.get('email').strip()
        password = data.get('password')
        username = data.get('username').strip()
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        dob = data.get('dob', '').strip()

        # 이메일 검증
        if '@' not in email:
            return jsonify({
                'success': False,
                'message': '유효한 이메일을 입력해주세요.'
            }), 400

        # 비밀번호 길이 검증
        if len(password) < 6:
            return jsonify({
                'success': False,
                'message': '비밀번호는 6자 이상이어야 합니다.'
            }), 400

        # username 검증
        if not username:
            return jsonify({
                'success': False,
                'message': 'ID를 입력해주세요.'
            }), 400

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
                return jsonify({
                    'success': False,
                    'message': '이미 사용 중인 이메일 또는 ID 입니다.'
                }), 409

            cursor.execute('''
                INSERT INTO users (email, username, name, phone, dob, password)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (email, username, name, phone, dob, hashed_password))

            conn.commit()
            user_id = cursor.lastrowid

            return jsonify({
                'success': True,
                'message': '회원가입이 완료되었습니다.',
                'user_id': user_id,
                'email': email,
                'username': username
            }), 201

        except sqlite3.IntegrityError:
            return jsonify({
                'success': False,
                'message': '이미 가입된 이메일 또는 ID입니다.'
            }), 409
        finally:
            conn.close()
    
    except Exception as e:
        print(f"Error in signup: {str(e)}")
        return jsonify({
            'success': False,
            'message': '회원가입 중 오류가 발생했습니다.'
        }), 500

@app.route('/api/login', methods=['POST'])
def login():
    """로그인 API"""
    try:
        data = request.get_json()
        
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({
                'success': False,
                'message': '이메일과 비밀번호는 필수입니다.'
            }), 400
        
        email = data.get('email').strip()
        password = data.get('password')
        hashed_password = hash_password(password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        conn.close()
        
        if user and user['password'] == hashed_password:
            return jsonify({
                'success': True,
                'message': '로그인되었습니다.',
                'user_id': user['id'],
                'email': user['email']
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': '이메일 또는 비밀번호가 일치하지 않습니다.'
            }), 401
    
    except Exception as e:
        print(f"Error in login: {str(e)}")
        return jsonify({
            'success': False,
            'message': '로그인 중 오류가 발생했습니다.'
        }), 500

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """사용자 정보 조회 API"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, email, created_at FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        conn.close()
        
        if user:
            return jsonify({
                'success': True,
                'user': {
                    'id': user['id'],
                    'email': user['email'],
                    'created_at': user['created_at']
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': '사용자를 찾을 수 없습니다.'
            }), 404
    
    except Exception as e:
        print(f"Error in get_user: {str(e)}")
        return jsonify({
            'success': False,
            'message': '사용자 조회 중 오류가 발생했습니다.'
        }), 500

@app.route('/api/survey', methods=['POST'])
def save_survey():
    """설문조사 답변 저장 API"""
    try:
        data = request.get_json()
        
        if not data or not data.get('user_id') or not data.get('survey_data'):
            return jsonify({
                'success': False,
                'message': '사용자 ID와 설문 데이터는 필수입니다.'
            }), 400
        
        user_id = data.get('user_id')
        survey_data = json.dumps(data.get('survey_data'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO survey_responses (user_id, survey_data)
                VALUES (?, ?)
            ''', (user_id, survey_data))
            
            conn.commit()
            response_id = cursor.lastrowid
            
            return jsonify({
                'success': True,
                'message': '설문조사 답변이 저장되었습니다.',
                'response_id': response_id
            }), 201
        finally:
            conn.close()
    
    except Exception as e:
        print(f"Error in save_survey: {str(e)}")
        return jsonify({
            'success': False,
            'message': '설문조사 저장 중 오류가 발생했습니다.'
        }), 500

@app.route('/api/health', methods=['GET'])
def health():
    """헬스 체크 API"""
    return jsonify({
        'status': 'healthy',
        'message': 'SeedUp API Server is running'
    }), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': '요청한 리소스를 찾을 수 없습니다.'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': '서버 내부 오류가 발생했습니다.'
    }), 500

if __name__ == '__main__':
    # 데이터베이스 초기화
    init_db()
    
    # Flask 앱 실행
    print("Starting SeedUp API Server on http://localhost:5000")
    app.run(debug=True, port=5000)
