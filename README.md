# 🌱 SeedUp
투자입문자를 위한 AI 기반 주식 투자 자문 서비스

## 🎯 프로젝트 개요

SeedUp은 투자 초보자들이 쉽고 안전하게 주식 투자를 시작할 수 있도록 돕는 종합 투자 플랫폼입니다.
GPT-4o-mini 기반의 투자 전문 AI 챗봇이 개인화된 맞춤형 투자 조언을 제공합니다.

## ✨ 주요 기능

### 🤖 AI 투자 챗봇
- **GPT-4o-mini** 모델 기반 투자 전문 상담
- 구조화된 마크다운 형식의 가독성 높은 응답
- 실시간 대화형 투자 조언 및 교육
- 게스트/회원 구분 서비스 (개인화 수준 차별화)

### 📊 투자 분석 서비스
- **종목 분석**: 기업 재무 분석, 기술적 분석, 투자 포인트 제공
- **포트폴리오 추천**: 개인 투자성향 기반 맞춤 포트폴리오 구성
- **투자 용어 사전**: 실무 활용 예시와 함께 제공하는 쉬운 용어 설명
- **리스크 관리**: 손절매, 분산투자 등 리스크 관리 가이드

### 👤 개인화 서비스
- **투자 성향 설문**: 9가지 질문으로 투자 성향 분석
- **사용자별 맞춤 조언**: 투자 목표, 위험 선호도, 투자 기간 고려
- **대화 이력 관리**: 로그인 사용자 대화 세션 저장 및 연속성 제공

### 🎨 사용자 경험
- **반응형 웹 디자인**: PC/모바일 최적화
- **실시간 채팅 인터페이스**: 부드러운 UX/UI
- **마크다운 렌더링**: 이모지, 불릿 포인트, 강조 표시 등 가독성 개선

## 🏗️ 기술 아키텍처

### Backend
- **FastAPI**: 고성능 비동기 웹 프레임워크
- **MySQL**: 관계형 데이터베이스 (사용자, 설문, 채팅 이력)
- **SQLAlchemy**: ORM 및 데이터베이스 모델링
- **OpenAI API**: GPT-4o-mini 모델 연동
- **Pydantic**: 데이터 검증 및 직렬화

### Frontend  
- **React 18**: 모던 프론트엔드 프레임워크
- **Vite**: 빠른 개발 빌드 도구
- **React Router**: 클라이언트 사이드 라우팅
- **Axios**: HTTP 클라이언트
- **CSS3**: 커스텀 스타일링 (반응형 디자인)

### Database Schema
- **users**: 사용자 정보 및 투자성향
- **survey_questions/answers**: 투자 성향 설문 시스템
- **chat_sessions/messages**: 챗봇 대화 이력 관리

## 🚀 빠른 시작

### 1. 환경 설정

#### 필수 요구사항
- Python 3.8+
- Node.js 16+
- MySQL 8.0+
- OpenAI API Key

#### 환경변수 설정
```bash
cd backend
cp .env.example .env
```

`.env` 파일 수정:
```bash
# OpenAI API 설정
OPENAI_API_KEY=your_openai_api_key_here

# MySQL 데이터베이스 설정  
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=seedup_db

# 챗봇 모델 설정
CHATBOT_MODEL=gpt-4o-mini
MAX_TOKENS=800
TEMPERATURE=0.3
```

### 2. 백엔드 실행

```bash
cd backend

# 가상환경 생성 및 활성화 (권장)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate     # Windows

# 의존성 설치
pip install -r requirements.txt

# 데이터베이스 테이블 생성 및 서비스 실행
python main.py
```

**서버 주소**: http://localhost:8000  
**API 문서**: http://localhost:8000/docs

### 3. 프론트엔드 실행

```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev
```

**서버 주소**: http://localhost:3000

### 4. 챗봇 테스트

```bash
cd backend
python test_chatbot.py
```

## 📚 API 엔드포인트

### 인증 & 사용자
- `GET /api/health` - 헬스 체크
- `GET /api/check_username` - 아이디 중복 확인
- `POST /api/signup` - 회원가입
- `POST /api/login` - 로그인  
- `GET /api/users/{user_id}` - 사용자 정보 조회
- `POST /api/users/{user_id}/investment-type` - 투자성향 저장

### 설문조사
- `GET /api/survey-questions` - 설문 질문 목록 조회
- `POST /api/survey` - 설문 답변 저장
- `POST /api/init-survey-questions` - 설문 질문 초기화

### 챗봇 서비스
- `POST /api/chat/send` - 일반 채팅 (JSON 응답)
- `POST /api/chat/stream` - 스트리밍 채팅 (SSE)

## 💡 주요 특징

### 🎨 구조화된 AI 응답
AI가 다음과 같은 형식으로 체계적인 답변을 제공합니다:

```markdown
## 📊 삼성전자 분석
### ✅ 투자 포인트
• 글로벌 반도체 시장 리더십
• 안정적인 배당 정책
• 강력한 브랜드 파워

### ❌ 리스크 요소  
• 반도체 시장 변동성
• 중국 시장 의존도

### ⭐ 추천도
⭐⭐⭐⭐ (4/5점)
```

### 🔐 사용자별 맞춤화
- **로그인 사용자**: 개인 투자성향과 포트폴리오 기반 맞춤 조언
- **게스트 사용자**: 일반적인 투자 교육 및 상담 서비스
- **대화 연속성**: 세션 기반 컨텍스트 유지

### ⚡ 성능 최적화
- **GPT-4o-mini**: GPT-4 수준 성능, 10배 저렴한 비용
- **응답 시간**: 평균 5-10초 이내 
- **토큰 최적화**: max_tokens=800, temperature=0.3

## 🛠️ 개발 도구

### 테스트 스크립트
- `test_chatbot.py`: 챗봇 API 전체 테스트 (사용자/게스트/세션 연속성)
- `check_db.py`: 데이터베이스 연결 및 데이터 확인
- `check_tables.py`: 테이블 구조 및 존재 여부 확인

### 디버깅 팁
```bash
# 챗봇 API 테스트
python backend/test_chatbot.py

# DB 상태 확인  
python backend/check_db.py

# 서버 로그 확인
python backend/main.py  # 콘솔에서 실시간 로그 확인
```

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## ⚠️ 주의사항

- **투자 책임**: 제공되는 모든 정보는 참고용이며, 투자 결정은 본인 책임입니다
- **API Key 관리**: OpenAI API 키를 안전하게 보관하고 노출되지 않도록 주의하세요
- **데이터베이스**: 운영 환경에서는 적절한 백업 및 보안 설정을 적용하세요

---

**🌱 SeedUp과 함께 현명한 투자 여정을 시작하세요!**
