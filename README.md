# SeedUp
투자입문자를 위한 국내 주식 투자 자문 AI Agent 서비스

## 프로젝트 구조
```
seedup/
├── backend/              # FastAPI 백엔드
│   ├── main.py          # API 서버
│   ├── requirements.txt # Python 패키지
│   └── seedup.db        # SQLite 데이터베이스
├── frontend/            # React 프론트엔드
│   ├── src/
│   ├── package.json
│   └── vite.config.js
└── docs/                # 문서
```

## 기술 스택

### Backend
- FastAPI
- SQLite
- Pydantic

### Frontend
- React
- Vite
- React Router

## 실행 방법

### 백엔드 실행
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```
서버: http://localhost:5000  
API 문서: http://localhost:5000/docs

> **참고:** `python main.py`로도 실행 가능하지만, `uvicorn` 명령어 사용을 권장합니다.

### 프론트엔드 실행
```bash
cd frontend
npm install
npm run dev
```
서버: http://localhost:3001

## API 엔드포인트
- `GET /api/health` - 헬스 체크
- `GET /api/check_username` - 아이디 중복 확인
- `POST /api/signup` - 회원가입
- `POST /api/login` - 로그인
- `GET /api/users/{user_id}` - 사용자 정보 조회
- `POST /api/survey` - 설문조사 저장
