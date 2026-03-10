# fin_structured_model (정형 기업분석 에이전트)

DART 재무(정형) + yfinance 시가총액/가격을 결합해
분기(as_of) 기준 기업 스코어/지표를 만들고, JSON 리포트를 출력한다.

## 1) 산출물
- `data/processed/fin_scores_v2_smoke_2024_CONSOL_with_mc.parquet`
  - 재무 TTM 지표 + 스코어 + market cap + PER/PBR + 가격 피처
- `data/processed/price_features_asof.parquet`
  - 분기(as_of) 기준 가격 피처(ret/vol/dd)
- `data/processed/structured_report.json`
  - 종목 1개(as_of) 정형 리포트(JSON) + 규칙기반 NLG 문장

## 2) 파이프라인 개요
1) 유니버스 생성
2) DART core 재무 수집(Q1/H1/Q3/FY)
3) normalize(계정명 매핑 + 숫자화 + proxy 처리)
4) YTD → 분기 단독값 변환(Flow 항목)
5) TTM 생성 + 지표 계산
6) 점수화(백분위) + pillar/overall score
7) yfinance로 market_cap 연결 → PER/PBR 계산
8) yfinance로 일별 가격 수집 → as_of 가격 피처 생성
9) (7)(8) merge → 최종 스코어 parquet 생성
10) exporter로 JSON 리포트 생성(+규칙기반 NLG)

## 3) 실행 순서(스모크 5종목 기준)
### (1) DART core 재무 수집
```bash
python -m scripts.update_universe
python -m scripts.fetch_dart_core --year 2023 --reprt_key Q1 --smoke
python -m scripts.fetch_dart_core --year 2023 --reprt_key H1 --smoke
python -m scripts.fetch_dart_core --year 2023 --reprt_key Q3 --smoke
python -m scripts.fetch_dart_core --year 2023 --reprt_key FY --smoke

python -m scripts.fetch_dart_core --year 2024 --reprt_key Q1 --smoke
python -m scripts.fetch_dart_core --year 2024 --reprt_key H1 --smoke
python -m scripts.fetch_dart_core --year 2024 --reprt_key Q3 --smoke
python -m scripts.fetch_dart_core --year 2024 --reprt_key FY --smoke


“Windows CMD/PowerShell에서는 \ 줄바꿈을 쓰지 말고 한 줄로 실행하거나 PowerShell 백틱(`)을 사용”