"""
update_sectors_dart.py
──────────────────────
DART API의 induty_code(한국표준산업분류)를 기반으로
instruments 테이블의 sector 컬럼을 실제 KRX 업종명으로 업데이트합니다.

실행:
    cd backend
    python update_sectors_dart.py
"""
from __future__ import annotations

import os
import time
import pandas as pd
import pymysql
import requests
from dotenv import load_dotenv

load_dotenv()

DART_KEY = os.getenv("DART_API_KEY")

# ── KSIC(한국표준산업분류) 코드 → KRX 스타일 업종명 매핑 ──────────────────────
# 긴 코드(정밀)를 먼저, 접두어 순으로 정렬해 가장 긴 매칭부터 사용
INDUTY_MAP: list[tuple[str, str]] = sorted([
    # 반도체
    ("26400", "반도체"),
    ("26110", "반도체"),  ("2611",  "반도체"),
    ("26120", "반도체"),  ("2612",  "반도체"),
    ("26112", "반도체"),
    ("264",   "반도체"),

    # 디스플레이
    ("26210", "디스플레이"), ("2621", "디스플레이"),

    # 전자부품
    ("26220", "전자부품"), ("2622", "전자부품"),
    ("26290", "전자부품"), ("2629", "전자부품"),
    ("26291", "전자부품"), ("26299", "전자부품"),
    ("26429", "전자부품"), ("26421", "전자부품"),
    ("262",  "전자부품"),
    ("261",  "전자부품"),
    ("263",  "전자부품"),  # 통신장비

    # 기계/장비 (반도체 제조장비 포함!)
    ("29271", "기계/장비"),  # 반도체 제조용 기계
    ("29229", "기계/장비"),
    ("29280", "기계/장비"),
    ("29241", "기계/장비"),
    ("29176", "기계/장비"),  # 승강기 등
    ("29172", "기계/장비"),  # 자동차용 공조 → 자동차부품으로 볼 수도 있으나 기계로
    ("29162", "기계/장비"),
    ("29119", "기계/장비"),
    ("29111", "기계/장비"),
    ("2927",  "기계/장비"),
    ("2928",  "기계/장비"),
    ("2922",  "기계/장비"),
    ("2920",  "기계/장비"),
    ("292",   "기계/장비"),
    ("291",   "기계/장비"),
    ("29",    "기계/장비"),
    ("28111", "기계/장비"),
    ("27219", "기계/장비"),
    ("27212", "기계/장비"),
    ("272",   "기계/장비"),

    # 2차전지
    ("28202", "2차전지"),
    ("28201", "2차전지"),

    # 전기/전자
    ("28302", "전기/전자"),  # 전선
    ("28121", "전기/전자"),  # 변압기/차단기
    ("281",   "전기/전자"),
    ("282",   "전기/전자"),
    ("28",    "전기/전자"),

    # 의료기기/정밀기기
    ("27299", "의료기기"), ("265", "의료기기"),
    ("2720",  "의료기기"), ("27",  "의료기기"),

    # 제약/바이오 (KSIC 21 = 의약품!)
    ("21210", "제약/바이오"), ("21290", "제약/바이오"),
    ("21120", "제약/바이오"), ("21110", "제약/바이오"),
    ("2121",  "제약/바이오"), ("2112",  "제약/바이오"), ("2111",  "제약/바이오"),
    ("212",   "제약/바이오"),
    ("211",   "제약/바이오"),  # 기초 의약물질/생물학적 의약품 (바이오!)
    ("21",    "제약/바이오"),

    # 화학
    ("20423", "화학"), ("20419", "화학"), ("20411", "화학"),
    ("20129", "화학"), ("20119", "화학"), ("20111", "화학"),
    ("2049",  "화학"), ("204",   "화학"),
    ("2041",  "화학"), ("2042",  "화학"),
    ("20494", "화학"),
    ("20",    "화학"),

    # 고무/소재
    ("22110", "소재"), ("221",  "소재"),  # 타이어/고무
    ("22",    "소재"),

    # 비금속/소재
    ("23999", "소재"), ("2312", "소재"),
    ("23",    "소재"),

    # 철강/금속 (KSIC 24 = 1차 금속)
    ("24110", "철강"), ("241",  "철강"),
    ("24213", "철강"), ("242",  "철강"),
    ("24",    "철강"),

    # 금속가공 (방산 제품 등)
    ("25200", "금속가공"),
    ("25",    "금속가공"),
    ("3111",  "금속/비철"),
    ("31113", "금속/비철"),
    ("311",   "조선"),  # 선박 → 조선

    # 자동차/부품
    ("30121", "자동차"), ("30111", "자동차"),
    ("303",   "자동차"),  # 기타 운송장비 (자동차 부품 등)
    ("301",   "자동차"),

    # 조선
    ("31113", "조선"), ("3111",  "조선"),
    ("50112", "조선/해운"),
    ("302",   "조선"),

    # 방산/항공
    ("31321", "방산/항공"),  # 항공기 엔진/부품
    ("31311", "방산/항공"),  # 항공기 제조
    ("31201", "방산/항공"),  # 철도차량
    ("303",   "방산/항공"),
    ("3131",  "방산/항공"),
    ("3132",  "방산/항공"),
    ("31",    "기계/장비"),   # 기타 운송장비 fallback

    # IT서비스/소프트웨어
    ("58221", "게임/엔터"),
    ("5822",  "게임/엔터"),
    ("5821",  "IT서비스"),
    ("58210", "IT서비스"),
    ("582",   "IT서비스"),
    ("63120", "IT서비스"),  # 포털/정보서비스
    ("631",   "IT서비스"),
    ("62021", "IT서비스"), ("62022", "IT서비스"),
    ("620",   "IT서비스"),
    ("63",    "IT서비스"),
    ("58",    "IT서비스"),

    # 미디어/엔터
    ("59201", "엔터/미디어"),
    ("59114", "엔터/미디어"),
    ("592",   "엔터/미디어"),
    ("591",   "엔터/미디어"),
    ("59",    "엔터/미디어"),
    ("602",   "미디어"),     # 방송
    ("60",    "미디어"),

    # 전문서비스
    ("72129", "전문서비스"),
    ("71310", "전문서비스"),  # 광고
    ("721",   "IT서비스"),
    ("715",   "전문서비스"),
    ("75320", "전문서비스"),  # 보안서비스
    ("75210", "소비재"),      # 여행사
    ("73",    "전문서비스"),
    ("71",    "전문서비스"),
    ("72",    "전문서비스"),
    ("75",    "전문서비스"),

    # 금융
    ("66199", "금융"),  # 핀테크
    ("66121", "금융"),  # 생명보험
    ("65122", "금융"),  # 서울보증
    ("65121", "금융"),  # 손해보험
    ("65110", "금융"),  # 생명보험
    ("65200", "금융"),  # 재보험
    ("645",   "금융"), ("644",   "금융"), ("641",   "금융"),
    ("64992", "금융"), ("649",   "금융"),
    ("661",   "금융"), ("664",   "금융"),
    ("65",    "금융"),
    ("66",    "금융"),
    ("64",    "금융"),

    # 부동산
    ("68112", "부동산"),
    ("70113", "부동산"),
    ("70",    "부동산"),
    ("68",    "부동산"),

    # 물류/운수
    ("49300", "물류"), ("493", "물류"),
    ("5299",  "물류"),
    ("50",    "물류"),
    ("49",    "물류"),
    ("51",    "항공"),

    # 건설
    ("41221", "건설"),
    ("41",    "건설"), ("42", "건설"), ("43", "건설"),

    # 에너지
    ("46713", "에너지"),  # LPG 도매
    ("19",    "에너지"),  # 석유정제

    # 유통/도소매
    ("47111", "유통"),
    ("46800", "유통"), ("467", "유통"),
    ("461",   "유통"),
    ("464",   "유통"),
    ("4632",  "식품"),  # 식음료 도매
    ("46",    "유통"),
    ("47",    "유통"),

    # 소비재/서비스
    ("91249", "소비재"),  # 카지노/오락
    ("969",   "소비재"),
    ("55",    "소비재"), ("56",  "소비재"),
    ("91",    "소비재"),

    # 식품/음료/담배
    ("12000", "식품"),   # 담배 제조
    ("108",  "식품"),
    ("12",   "식품"),
    ("10",   "식품"),
    ("11",   "음료"),

    # 의복/섬유
    ("14111", "소비재"),
    ("14",    "소비재"),
    ("13",    "소비재"),

    # 통신
    ("61220", "통신"), ("612", "통신"), ("611",  "통신"),
    ("465",   "통신"), ("61",  "통신"),

    # 유틸리티
    ("35",    "유틸리티"),
], key=lambda x: -len(x[0]))


def induty_to_sector(code: str | None) -> str | None:
    """induty_code → KRX 스타일 업종명. 없으면 None 반환."""
    if not code:
        return None
    c = str(code).strip()
    for prefix, sector in INDUTY_MAP:
        if c.startswith(prefix):
            return sector
    return None


def get_conn():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def fetch_induty_code(corp_code: str) -> str | None:
    """DART API에서 corp_code로 induty_code 조회."""
    try:
        r = requests.get(
            "https://opendart.fss.or.kr/api/company.json",
            params={"crtfc_key": DART_KEY, "corp_code": corp_code},
            timeout=10,
        )
        d = r.json()
        if d.get("status") == "000":
            return d.get("induty_code")
    except Exception:
        pass
    return None


def main():
    # universe parquet에서 ticker → corp_code 매핑
    from pathlib import Path
    parquet_path = Path(__file__).parent / "fin_structured_model" / "data" / "processed" / "universe_k200_k150_fixed.parquet"
    if not parquet_path.exists():
        print(f"[오류] universe parquet 없음: {parquet_path}")
        return

    univ = pd.read_parquet(parquet_path)
    univ["ticker"] = univ["ticker"].astype(str).str.zfill(6)
    univ["corp_code"] = univ["corp_code"].astype(str).str.zfill(8)
    ticker_to_corp = dict(zip(univ["ticker"], univ["corp_code"]))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT stock_code, name, sector FROM instruments WHERE asset_type='STOCK'")
    stocks = cur.fetchall()
    print(f"총 {len(stocks)}개 종목 처리 중...")

    updated = 0
    skipped_no_corp = 0
    skipped_no_induty = 0
    changes = []

    for row in stocks:
        code = str(row["stock_code"]).zfill(6)
        corp_code = ticker_to_corp.get(code)

        if not corp_code:
            skipped_no_corp += 1
            continue

        induty_code = fetch_induty_code(corp_code)
        time.sleep(0.05)

        new_sector = induty_to_sector(induty_code)

        if not new_sector:
            skipped_no_induty += 1
            old = row.get("sector") or "-"
            print(f"  [미매핑] {code} {row['name']}: induty_code={induty_code}, 기존={old}")
            continue

        old_sector = row.get("sector") or ""
        if new_sector != old_sector:
            cur.execute(
                "UPDATE instruments SET sector=%s WHERE stock_code=%s",
                (new_sector, row["stock_code"]),
            )
            changes.append((code, row["name"], old_sector, new_sector))
            updated += 1

    conn.commit()
    conn.close()

    print(f"\n✅ 완료: {updated}개 업종 변경")
    print(f"   corp_code 없음: {skipped_no_corp}개")
    print(f"   induty_code → 업종명 미매핑: {skipped_no_induty}개")

    if changes:
        print("\n[ 변경된 종목 ]")
        for code, name, old, new in changes:
            print(f"  {code} {name:<20} {old} → {new}")


if __name__ == "__main__":
    main()
