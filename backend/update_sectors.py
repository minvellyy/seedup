"""
WICS(WISEindex) 업종 분류를 이용해 instruments 테이블의 sector 컬럼을 업데이트합니다.

실행:
    cd backend
    python update_sectors.py
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pymysql
import requests

load_dotenv()

# WICS 섹터 코드 → 한글 업종명
WICS_SECTORS = ["G10", "G15", "G20", "G25", "G30", "G35", "G40", "G45", "G50", "G55"]

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _last_weekday(dt: datetime) -> str:
    """주말이면 직전 금요일로 조정, 'YYYYMMDD' 반환."""
    while dt.weekday() >= 5:  # 5=토, 6=일
        dt -= timedelta(days=1)
    return dt.strftime("%Y%m%d")


def fetch_wics_sector_map(date_str: str) -> dict[str, str]:
    """WISEindex API로 WICS 업종분류 {종목코드: 업종명} 딕셔너리를 반환합니다."""
    sector_map: dict[str, str] = {}
    for sec_cd in WICS_SECTORS:
        url = (
            f"https://www.wiseindex.com/Index/GetIndexComponets"
            f"?ceil_yn=0&dt={date_str}&sec_cd={sec_cd}"
        )
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            for item in data.get("list", []):
                code = str(item.get("CMP_CD", "")).strip().zfill(6)
                sector_nm = str(item.get("SEC_NM_KOR", "")).strip()
                if code and sector_nm:
                    sector_map[code] = sector_nm
        except Exception as e:
            print(f"  [경고] 섹터 {sec_cd} 조회 실패: {e}")
        time.sleep(0.2)  # rate limit 방지

    return sector_map


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


def main():
    date_str = _last_weekday(datetime.today())
    print(f"WICS 업종 데이터 수집 중... (기준일: {date_str})")

    sector_map = fetch_wics_sector_map(date_str)
    print(f"  → {len(sector_map)}개 종목 업종 수집 완료")

    if not sector_map:
        print("업종 데이터를 가져오지 못했습니다. 종료.")
        return

    # 업종 분포 출력
    from collections import Counter
    sector_counts = Counter(sector_map.values())
    print("\n[ WICS 업종 분포 ]")
    for s, c in sorted(sector_counts.items(), key=lambda x: -x[1]):
        print(f"  {s:<20} {c:>4}개")

    conn = get_conn()
    cur = conn.cursor()

    # instruments 테이블의 전체 종목 조회
    cur.execute(
        "SELECT stock_code, name, sector FROM instruments WHERE asset_type = 'STOCK'"
    )
    rows = cur.fetchall()
    print(f"\ninstruments STOCK 종목 수: {len(rows)}")

    updated = 0
    not_found = []
    for row in rows:
        code = str(row["stock_code"]).zfill(6)
        new_sector = sector_map.get(code)
        if new_sector and new_sector != row.get("sector"):
            cur.execute(
                "UPDATE instruments SET sector = %s WHERE stock_code = %s",
                (new_sector, row["stock_code"]),
            )
            updated += 1
        elif not new_sector:
            not_found.append((row["stock_code"], row["name"]))

    conn.commit()
    conn.close()

    print(f"\n✅ 업데이트 완료: {updated}개 종목 업종 반영")
    print(f"   WICS 미매칭 종목: {len(not_found)}개 (소형주·우선주 등)")
    if not_found[:10]:
        print("   미매칭 예시:", [(c, n) for c, n in not_found[:10]])

    # 검증: 디어유(376300) 확인
    conn2 = get_conn()
    cur2 = conn2.cursor()
    cur2.execute("SELECT stock_code, name, sector FROM instruments WHERE stock_code = '376300'")
    r = cur2.fetchone()
    if r:
        print(f"\n[검증] 376300 디어유 → sector: {r['sector']}")
    conn2.close()


if __name__ == "__main__":
    main()
