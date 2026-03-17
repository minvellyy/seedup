"""
유니버스 bucket 필드 재정립 스크립트
==============================================
분류 기준:
  CORE   - 묵직한 대형·우량주 (포트폴리오 뼈대)
           1) KOSPI 대형주 고정 리스트 (코스피 100 주요 블루칩)
           2) 위 리스트에 없는 KOSPI 종목 중 1년 연변동성 < 35%
  GROWTH - 수익 상방을 노리는 성장·테마주 (알파 추구)
           KOSDAQ 종목 전체, 고변동성 KOSPI 종목
  ETF    - ETF는 기존 ETF 값 유지

실행:
    cd backend
    python seed_universe_buckets.py
"""

from __future__ import annotations
import os
import math
from datetime import date, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import pymysql

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# KOSPI 블루칩 고정 리스트 (KOSPI 100 내 대표 대형주·금융·산업재)
# 이 리스트에 있으면 변동성과 무관하게 CORE로 분류됩니다.
# ─────────────────────────────────────────────────────────────────────────────
CORE_FIXED = {
    # ── 반도체·IT
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "066570",  # LG전자
    "009150",  # 삼성전기
    "035420",  # NAVER
    "035720",  # 카카오
    # ── 2차전지·에너지
    "373220",  # LG에너지솔루션
    "006400",  # 삼성SDI
    "051910",  # LG화학
    "096770",  # SK이노베이션
    "003670",  # 포스코퓨처엠
    # ── 바이오·헬스케어
    "207940",  # 삼성바이오로직스
    "068270",  # 셀트리온
    "128940",  # 한미약품
    # ── 자동차
    "005380",  # 현대차
    "000270",  # 기아
    "012330",  # 현대모비스
    # ── 철강·소재
    "005490",  # POSCO홀딩스

    # ── 금융
    "105560",  # KB금융
    "055550",  # 신한지주
    "086790",  # 하나금융지주
    "316140",  # 우리금융지주
    "000810",  # 삼성화재
    "005830",  # DB손해보험
    "032830",  # 삼성생명
    # ── 방산·중공업
    "012450",  # 한화에어로스페이스
    "079550",  # LIG넥스원
    "047810",  # 한국항공우주
    "329180",  # HD현대중공업
    "010120",  # LS ELECTRIC
    "267260",  # HD현대일렉트릭
    # ── 유통·소비
    "028260",  # 삼성물산
    "090430",  # 아모레퍼시픽
    "033780",  # KT&G
    "003230",  # 삼양식품
    "097950",  # CJ제일제당
    # ── 통신·인프라
    "030200",  # KT
    "017670",  # SK텔레콤
    "015760",  # 한국전력
    # ── 지주사
    "034730",  # SK
    "003550",  # LG
    "000150",  # 두산
    "402340",  # SK스퀘어
    "011170",  # 롯데케미칼
    "003490",  # 대한항공
    "005940",  # NH투자증권
    "006800",  # 미래에셋증권
}

# 변동성 임계값: 이 이하이면 KOSPI 종목도 CORE로 추가 분류
VOL_CORE_THRESHOLD = 0.35   # 연변동성 35% 이하
VOL_LOOKBACK_DAYS  = 365    # 1년 거래일 기준

# ─────────────────────────────────────────────────────────────────────────────


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


def calc_vol(prices: list[float]) -> float | None:
    """연 변동성(표준편차) 계산. prices는 시간순 종가 리스트."""
    if len(prices) < 20:
        return None
    daily_r = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
    n = len(daily_r)
    mean = sum(daily_r) / n
    var  = sum((r - mean) ** 2 for r in daily_r) / max(n - 1, 1)
    return math.sqrt(var) * math.sqrt(252)


def main():
    conn = get_conn()
    cur  = conn.cursor()

    # 1. 활성 STOCK universe 전체 조회
    cur.execute("""
        SELECT u.id, u.instrument_id, u.market, u.asset_type,
               i.stock_code, i.name
        FROM universe_items u
        JOIN instruments i ON u.instrument_id = i.instrument_id
        WHERE u.active = 1 AND u.asset_type = 'STOCK'
    """)
    rows = cur.fetchall()
    print(f"활성 STOCK 종목 수: {len(rows)}")

    if not rows:
        print("종목 없음. 종료.")
        return

    iids = [r["instrument_id"] for r in rows]
    placeholders = ",".join(["%s"] * len(iids))

    # 2. 최근 1년 가격 데이터 일괄 조회
    cutoff = (date.today() - timedelta(days=VOL_LOOKBACK_DAYS + 30)).isoformat()
    cur.execute(
        f"""
        SELECT instrument_id, close
        FROM market_prices
        WHERE instrument_id IN ({placeholders})
          AND price_date >= %s
          AND close > 0
        ORDER BY instrument_id, price_date
        """,
        iids + [cutoff],
    )
    price_hist: dict = defaultdict(list)
    for r in cur.fetchall():
        price_hist[r["instrument_id"]].append(float(r["close"]))

    # 3. 각 종목 bucket 결정
    updates: dict[int, str] = {}   # universe_items.id → bucket
    stats = {"CORE": 0, "GROWTH": 0, "unknown": 0}

    for row in rows:
        uid        = row["id"]
        iid        = row["instrument_id"]
        stock_code = row["stock_code"]
        market     = row["market"]  # KOSPI / KOSDAQ

        # ETF는 건드리지 않음
        if row["asset_type"] == "ETF":
            continue

        # ── 분류 로직 ──────────────────────────────────────────────────
        if stock_code in CORE_FIXED:
            bucket = "CORE"
        elif market == "KOSPI":
            # KOSPI인데 리스트에 없으면 변동성으로 판단
            vol = calc_vol(price_hist.get(iid, []))
            if vol is None or vol <= VOL_CORE_THRESHOLD:
                bucket = "CORE"    # 변동성 낮거나 데이터 부족 → 안정적 KOSPI → CORE
            else:
                bucket = "GROWTH"
        else:
            # KOSDAQ 기본 GROWTH
            vol = calc_vol(price_hist.get(iid, []))
            # 예외: 코스닥이어도 매우 안정적이면(거의 없음) CORE
            if vol is not None and vol < 0.25:
                bucket = "CORE"
            else:
                bucket = "GROWTH"

        updates[uid] = bucket
        stats[bucket] = stats.get(bucket, 0) + 1

    # 4. DB 일괄 업데이트
    print(f"\n분류 결과: CORE={stats['CORE']}, GROWTH={stats['GROWTH']}")
    confirm = input("DB에 반영하시겠습니까? (y/N): ").strip().lower()
    if confirm != "y":
        print("취소됨.")
        return

    update_count = 0
    for uid, bucket in updates.items():
        cur.execute(
            "UPDATE universe_items SET bucket = %s WHERE id = %s",
            (bucket, uid),
        )
        update_count += 1

    conn.commit()
    conn.close()
    print(f"\n✅ 완료: {update_count}개 종목 bucket 업데이트 완료.")

    # 5. 검증 출력
    conn2 = get_conn()
    cur2  = conn2.cursor()
    cur2.execute("""
        SELECT u.bucket, u.market, COUNT(*) as cnt
        FROM universe_items u
        WHERE u.active = 1 AND u.asset_type = 'STOCK'
        GROUP BY u.bucket, u.market
        ORDER BY u.bucket, u.market
    """)
    print("\n[ 최종 bucket 분포 ]")
    print(f"{'bucket':<10} {'market':<10} {'count':>6}")
    print("-" * 28)
    for r in cur2.fetchall():
        print(f"{r['bucket']:<10} {r['market']:<10} {r['cnt']:>6}")

    cur2.execute("""
        SELECT i.stock_code, i.name, u.market, u.bucket
        FROM universe_items u
        JOIN instruments i ON u.instrument_id = i.instrument_id
        WHERE u.active = 1 AND u.asset_type = 'STOCK' AND u.bucket = 'CORE'
        ORDER BY u.market, i.name
        LIMIT 30
    """)
    print("\n[ CORE 종목 샘플 (상위 30개) ]")
    for r in cur2.fetchall():
        print(f"  {r['stock_code']}  {r['name']:<20}  {r['market']}")
    conn2.close()


if __name__ == "__main__":
    main()
