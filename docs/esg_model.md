# esg_module

ESG 보고서 기반 리스크/기대요인 자연어 분석 모듈.
RAG(검색 증강 생성) 방식으로 보고서 원문에서 근거 있는 내용만 추출합니다.

---

## 구조

```
esg_module/
├── __init__.py       # 공개 API: analyze_by_stock_code, esg_bp
├── analyzer.py       # 핵심 로직 (RAG + GPT-4o-mini)
├── blueprint.py      # Flask Blueprint (REST API)
└── requirements.txt  # 의존성
```

---

## 사전 준비

### 1. 패키지 설치
```bash
pip install -r esg_module/requirements.txt
```

### 2. 환경변수 (.env)
```env
OPENAI_API_KEY=sk-...
DB_HOST=192.168.101.70
DB_PORT=3306
DB_USER=developer_team
DB_PASSWORD=0327
DB_NAME=seedup_db
```

### 3. DB 테이블
`seedup_db.esg_reports` 테이블이 있어야 합니다.
(esg_analyzer.py + export_to_mysql.py 실행으로 생성)

---

## 사용법

### A. Python 직접 호출
```python
from esg_module import analyze_by_stock_code

result = analyze_by_stock_code("005930")  # 삼성전자

if result is None:
    # ESG 보고서 없음 → UI에서 아예 표시 안 함
    pass
else:
    print(result["risks"])         # "탄소배출권 비용 증가, 수자원 리스크..."
    print(result["opportunities"]) # "Net Zero 2050 이행, 고효율 설비 교체..."
    print(result["company_name"])  # "삼성전자"
    print(result["published_at"])  # "2025-06-27"
    print(result["cached"])        # True (캐시) / False (신규 분석)
```

### B. Flask Blueprint 등록 (REST API)
```python
from flask import Flask
from esg_module import esg_bp

app = Flask(__name__)
app.register_blueprint(esg_bp, url_prefix="/api")
```

#### 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/api/esg/<stock_code>` | 분석 결과 반환 |
| GET | `/api/esg/<stock_code>?force=1` | 캐시 무시하고 재분석 |

#### 응답 형식
```json
// 보고서 있음 → 200
{
  "stock_code": "005930",
  "company_name": "삼성전자",
  "published_at": "2025-06-27",
  "risks": "탄소배출권 구매 비용 증가, 에너지 가격 변동, 수자원 리스크",
  "opportunities": "Net Zero 2050 탄소중립 이행, 고효율 설비 교체, 재생에너지 확보",
  "analyzed_at": "2026-03-12T10:00:00",
  "cached": true
}

// 보고서 없음 → 204 빈 응답
{}
```

---

## 동작 방식

1. `stock_code`로 `esg_reports` 테이블에서 최신 보고서 조회
2. 캐시(`risks`, `opportunities` 컬럼) 있으면 즉시 반환 (GPT 호출 없음)
3. 캐시 없으면:
   - 보고서 원문을 800자 단위 청크로 분할
   - SBERT(`snunlp/KR-SBERT-V40K-klueNLI-augSTS`)로 관련 청크 8개 추출 (RAG)
   - GPT-4o-mini에 컨텍스트 전달 → 리스크/기대요인 한 문장씩 추출
   - 결과를 DB에 저장 (이후 캐시 히트)
4. 보고서 자체에 근거 없는 내용은 생략 (None 반환)
