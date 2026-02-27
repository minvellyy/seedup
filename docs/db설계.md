# SeedUp DB & 설문 구조 리팩토링 요청서

# SeedUp DB & 설문 구조 리팩토링 요청서 (SQLite 버전)

너는 시니어 백엔드 개발자야. 우리 프로젝트(SeedUp)는 
FastAPI + SQLite + SQLAlchemy ORM을 사용한다.

현재 ERD는 users / survey_questions / survey_answers 3개 테이블이 있고
기존 구조는 실무 확장에 적합하지 않다.

기존 테이블 설계는 모두 버리고,
아래의 새 스키마로 SQLite 기준 마이그레이션 SQL + SQLAlchemy 모델 + CRUD 코드를 작성해줘.

------------------------------------------------------------
[중요: SQLite 사용 기준]
------------------------------------------------------------
- DB는 SQLite 사용 (PostgreSQL 아님)
- timestamptz 사용 금지 → DATETIME 또는 TIMESTAMP 사용
- now() 대신 CURRENT_TIMESTAMP 사용
- JSON 타입 없음 → options_json은 TEXT 컬럼에 JSON 문자열로 저장
- Boolean 타입은 INTEGER (0/1)로 처리
- SQLite는 ALTER 제약이 약하므로 DROP TABLE 후 CREATE 방식 허용

------------------------------------------------------------
[요구 사항]
------------------------------------------------------------

1) 답변 저장은 반드시 세로형(행 단위) 구조로 저장한다.
2) 질문 원문(question text)은 survey_questions.text 컬럼에 저장한다.
3) 문항 타입:
   - Q1, Q2, Q7 = TEXT
   - Q3, Q4-1, Q4-2, Q5 = NUMBER
   - Q4, Q6 = SINGLE_CHOICE
4) 조건부 문항:
   - Q4(CONTRIBUTION_TYPE) == "LUMP_SUM" → Q4-1 저장
   - Q4(CONTRIBUTION_TYPE) == "DCA" → Q4-2 저장
5) 모든 문항은 NULL 가능 → 미응답 시 survey_answers에 행 생성하지 않아도 됨
6) UNIQUE(user_id, question_id) 제약 설정
7) users 테이블:
   - password → password_hash 로 변경
   - email UNIQUE
   - dob 제거, birth_date만 유지
   - created_at, updated_at 유지 (DEFAULT CURRENT_TIMESTAMP)
8) survey_questions 테이블:
   - code (UNIQUE)
   - text (원문)
   - answer_type ("TEXT","NUMBER","SINGLE_CHOICE")
   - options_json (TEXT)
   - order_no (INTEGER)
   - parent_question_id (INTEGER FK)
   - show_if_question_id (INTEGER FK)
   - show_if_value (TEXT)
   - created_at, updated_at
9) survey_answers 테이블:
   - user_id (FK)
   - question_id (FK)
   - value_text TEXT NULL
   - value_number REAL NULL
   - value_choice TEXT NULL
   - created_at, updated_at
   - UNIQUE(user_id, question_id)

------------------------------------------------------------
[해야 할 작업]
------------------------------------------------------------

A. SQLite 마이그레이션 SQL 작성
   - DROP TABLE IF EXISTS 사용
   - FOREIGN KEY 활성화 (PRAGMA foreign_keys = ON;)
   - CURRENT_TIMESTAMP 사용
   - 인덱스 생성 포함

B. SQLAlchemy 모델 작성 (SQLite 기준)
   - DateTime(timezone=False)
   - default=datetime.utcnow
   - relationship 설정 포함

C. Seed 데이터 작성
   - codes:
     INVEST_GOAL
     TARGET_HORIZON
     TARGET_AMOUNT
     CONTRIBUTION_TYPE
     LUMP_SUM_AMOUNT
     MONTHLY_AMOUNT
     MAX_HOLDINGS
     DIVIDEND_PREF
     ACCOUNT_TYPE

   - CONTRIBUTION_TYPE options_json:
     ["LUMP_SUM","DCA"]

   - DIVIDEND_PREF options_json:
     ["HIGH","MID","LOW"]

   - LUMP_SUM_AMOUNT show_if:
     show_if_question_id = CONTRIBUTION_TYPE
     show_if_value = "LUMP_SUM"

   - MONTHLY_AMOUNT show_if:
     show_if_question_id = CONTRIBUTION_TYPE
     show_if_value = "DCA"

D. FastAPI CRUD 스켈레톤 작성
   - GET /survey/questions
   - POST /survey/answers (upsert 로직 포함)
   - GET /survey/answers/me
   - Pydantic Schema 포함

------------------------------------------------------------
[출력 형식]
------------------------------------------------------------
1) SQLite migration SQL 파일 내용
2) SQLAlchemy models.py
3) seed_data.py
4) survey_router.py

주의:
- snake_case 컬럼
- PascalCase 모델
- SQLite 문법 기준으로 작성
- JSON은 TEXT로 저장

## survey_questions
1. 투자 목적은 무엇인가요?
2. 목표 시점은 언제인가요?
3. 목표 금액은 어느 정도인가요?
4. 선호하는 투자 방식을 선택해 주세요,
    4-1. 일시금 금액
    4-2. 월 투자 가능 금액
5. 최대 몇 개의 종목을 보유하고 싶으신가요?
6. 배당 선호 정도는?
7. 계좌 유형
