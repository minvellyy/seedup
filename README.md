# SeedUp
투자입문자를 위한 국내 주식 투자 자문 AI Agent 서비스

## 프로젝트 구조

This project contains the following structure:

- **backend/**: Contains all backend-related code, including the main FastAPI application and database logic.
- **frontend/**: Contains the frontend code for the application.

## Notes
- The `backend/main.py` file is the entry point for the backend server.
- The `backend/requirements.txt` file contains the dependencies for the backend.
- The root-level `main.py` and `requirements.txt` files are deprecated and can be removed.

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
