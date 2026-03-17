#!/usr/bin/env python3
"""
export_to_sqlite.py
--------------------
현재 MySQL(seedup_db)의 스키마 + 데이터를 SQLite3 파일로 통째로 내보냅니다.
방화벽 밖의 다른 컴퓨터에서 동일한 DB를 사용할 때 활용하세요.

사용법:
    cd backend
    python export_to_sqlite.py

출력: backend/seedup_export.db  (SQLite3 파일)
"""

import os
import re
import sqlite3
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# ── .env 로드 ─────────────────────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

MYSQL_CFG = dict(
    host     = os.getenv("DB_HOST", "localhost"),
    port     = int(os.getenv("DB_PORT", 3306)),
    user     = os.getenv("DB_USER"),
    password = os.getenv("DB_PASSWORD"),
    db       = os.getenv("DB_NAME"),
    charset  = "utf8mb4",
    cursorclass = pymysql.cursors.DictCursor,
)

SQLITE_PATH = Path(__file__).parent / "seedup_export.db"

# ── MySQL → SQLite 타입 매핑 ───────────────────────────────────────────────────
_TYPE_MAP = [
    (r"tinyint\(1\)",           "INTEGER"),   # bool
    (r"tinyint\b",              "INTEGER"),
    (r"smallint\b",             "INTEGER"),
    (r"mediumint\b",            "INTEGER"),
    (r"bigint\b",               "INTEGER"),
    (r"int\b",                  "INTEGER"),
    (r"float\b",                "REAL"),
    (r"double\b",               "REAL"),
    (r"decimal\b[^,)]*",       "REAL"),
    (r"numeric\b[^,)]*",       "REAL"),
    (r"datetime\b",             "DATETIME"),
    (r"timestamp\b",            "DATETIME"),
    (r"date\b",                 "DATE"),
    (r"time\b",                 "TIME"),
    (r"char\b",                 "TEXT"),
    (r"varchar\b[^,)]*",        "TEXT"),
    (r"tinytext\b",             "TEXT"),
    (r"mediumtext\b",           "TEXT"),
    (r"longtext\b",             "TEXT"),
    (r"text\b",                 "TEXT"),
    (r"tinyblob\b",             "BLOB"),
    (r"mediumblob\b",           "BLOB"),
    (r"longblob\b",             "BLOB"),
    (r"blob\b",                 "BLOB"),
    (r"enum\([^)]+\)",          "TEXT"),
    (r"set\([^)]+\)",           "TEXT"),
    (r"json\b",                 "TEXT"),
]

def mysql_type_to_sqlite(mysql_type: str) -> str:
    t = mysql_type.strip().lower()
    for pattern, sqlite_t in _TYPE_MAP:
        if re.search(pattern, t, re.IGNORECASE):
            return sqlite_t
    return "TEXT"


def get_create_table_info(cursor, table: str):
    """SHOW CREATE TABLE 결과에서 DDL 문자열 반환"""
    cursor.execute(f"SHOW CREATE TABLE `{table}`")
    row = cursor.fetchone()
    return row["Create Table"]


def parse_columns(create_ddl: str):
    """
    MySQL CREATE TABLE DDL을 파싱해 [(col_name, sqlite_type, constraints), ...] 반환.
    기본 컬럼 속성만 추출하며, FK 제약은 별도 처리.
    """
    lines = create_ddl.splitlines()
    columns = []
    primary_keys = []
    foreign_keys = []  # (col, ref_table, ref_col)

    for raw_line in lines[1:]:  # 첫 줄 "CREATE TABLE `name` (" 제외
        line = raw_line.strip().rstrip(",")

        # PRIMARY KEY 별도 라인
        if line.upper().startswith("PRIMARY KEY"):
            m = re.search(r"PRIMARY KEY\s*\(([^)]+)\)", line, re.IGNORECASE)
            if m:
                keys = [k.strip().strip("`") for k in m.group(1).split(",")]
                primary_keys.extend(keys)
            continue

        # KEY / INDEX 라인 무시 (UNIQUE KEY는 컬럼 UNIQUE 속성으로 대신 처리)
        if re.match(r"(UNIQUE\s+)?KEY\b|INDEX\b|CONSTRAINT\b.*UNIQUE", line, re.IGNORECASE):
            continue

        # FOREIGN KEY
        fk_m = re.match(
            r"(CONSTRAINT\s+`[^`]+`\s+)?FOREIGN KEY\s*\(`([^`]+)`\)\s*REFERENCES\s*`([^`]+)`\s*\(`([^`]+)`\)",
            line, re.IGNORECASE
        )
        if fk_m:
            foreign_keys.append((fk_m.group(2), fk_m.group(3), fk_m.group(4)))
            continue

        # 일반 컬럼: `col_name` col_type [attrs...]
        col_m = re.match(r"`([^`]+)`\s+(\S+)(.*)", line)
        if not col_m:
            continue

        col_name  = col_m.group(1)
        mysql_type_raw = col_m.group(2)
        rest      = col_m.group(3)

        sqlite_type = mysql_type_to_sqlite(mysql_type_raw)

        # NOT NULL
        not_null = "NOT NULL" if re.search(r"\bNOT NULL\b", rest, re.IGNORECASE) else ""

        # AUTO_INCREMENT → AUTOINCREMENT (PRIMARY KEY 컬럼에 붙여야 함)
        autoincrement = "AUTOINCREMENT" if re.search(r"\bAUTO_INCREMENT\b", rest, re.IGNORECASE) else ""

        # UNIQUE
        unique = "UNIQUE" if re.search(r"\bUNIQUE\b", rest, re.IGNORECASE) else ""

        # DEFAULT (SQLite에서 안전하게 처리 가능한 것만)
        default = ""
        def_m = re.search(r"DEFAULT\s+('[^']*'|\"[^\"]*\"|\S+)", rest, re.IGNORECASE)
        if def_m:
            val = def_m.group(1)
            # MySQL 함수 기본값은 SQLite에서 지원 안 함 → 제외
            if not re.match(r"(CURRENT_TIMESTAMP|NOW\(\)|CURRENT_DATE|NULL)", val, re.IGNORECASE):
                default = f"DEFAULT {val}"

        parts = [f"`{col_name}`", sqlite_type, not_null, unique, default]
        if autoincrement:
            # AUTOINCREMENT는 반드시 INTEGER PRIMARY KEY AUTOINCREMENT 형식이어야 함
            parts = [f"`{col_name}`", "INTEGER", "PRIMARY KEY", "AUTOINCREMENT"]

        constraint_str = " ".join(p for p in parts if p)
        columns.append((col_name, constraint_str, bool(autoincrement)))

    return columns, primary_keys, foreign_keys


def build_create_sql(table: str, create_ddl: str) -> str:
    """SQLite 용 CREATE TABLE SQL 생성"""
    columns, primary_keys, foreign_keys = parse_columns(create_ddl)

    col_defs = []
    pk_columns = set(primary_keys)
    has_autoincrement = any(ai for _, _, ai in columns)

    for col_name, constraint_str, is_auto in columns:
        # autoincrement가 없는 단일 PK는 인라인에 PRIMARY KEY 추가
        if not has_autoincrement and col_name in pk_columns and len(pk_columns) == 1:
            constraint_str += " PRIMARY KEY"
        col_defs.append(f"    {constraint_str}")

    # 복합 PK (autoincrement 없고 PK가 여러 컬럼)
    if not has_autoincrement and len(pk_columns) > 1:
        pk_str = ", ".join(f"`{k}`" for k in primary_keys)
        col_defs.append(f"    PRIMARY KEY ({pk_str})")

    # FOREIGN KEY
    for col, ref_table, ref_col in foreign_keys:
        col_defs.append(f"    FOREIGN KEY (`{col}`) REFERENCES `{ref_table}`(`{ref_col}`)")

    body = ",\n".join(col_defs)
    return f"CREATE TABLE IF NOT EXISTS `{table}` (\n{body}\n);"


def get_all_tables(cursor):
    cursor.execute("SHOW TABLES")
    rows = cursor.fetchall()
    # DictCursor 이므로 첫 번째 value
    return [list(r.values())[0] for r in rows]


def _to_sqlite_value(v):
    """SQLite3 가 지원하지 않는 Python 타입을 안전하게 변환."""
    import decimal, datetime
    if v is None:
        return None
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return sqlite3.Binary(v)
    if isinstance(v, bool):
        return int(v)
    return v


def copy_table_data(mysql_cur, sqlite_con, table: str):
    """MySQL 테이블 데이터를 SQLite에 INSERT"""
    mysql_cur.execute(f"SELECT * FROM `{table}`")
    rows = mysql_cur.fetchall()
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ", ".join("?" * len(columns))
    col_names = ", ".join(f"`{c}`" for c in columns)
    sql = f"INSERT OR IGNORE INTO `{table}` ({col_names}) VALUES ({placeholders})"

    data = [tuple(_to_sqlite_value(row[c]) for c in columns) for row in rows]
    sqlite_con.executemany(sql, data)
    return len(data)


def main():
    print(f"🔌 MySQL 접속 중: {MYSQL_CFG['host']}:{MYSQL_CFG['port']} / {MYSQL_CFG['db']}")
    mysql_con = pymysql.connect(**MYSQL_CFG)
    mysql_cur = mysql_con.cursor()

    tables = get_all_tables(mysql_cur)
    print(f"📋 발견된 테이블 ({len(tables)}개): {', '.join(tables)}\n")

    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()
        print(f"🗑  기존 파일 삭제: {SQLITE_PATH}")

    sqlite_con = sqlite3.connect(str(SQLITE_PATH))
    sqlite_con.execute("PRAGMA foreign_keys = OFF")   # 순서 무관하게 삽입
    sqlite_con.execute("PRAGMA journal_mode = WAL")

    for table in tables:
        ddl = get_create_table_info(mysql_cur, table)
        try:
            create_sql = build_create_sql(table, ddl)
            sqlite_con.execute(create_sql)
        except Exception as e:
            print(f"  ⚠️  {table}: 테이블 생성 실패 → {e}")
            print(f"     (원본 DDL 일부: {ddl[:200]}...)")
            continue

        try:
            count = copy_table_data(mysql_cur, sqlite_con, table)
            print(f"  ✅ {table:40s}  {count:>6,}건 복사")
        except Exception as e:
            print(f"  ⚠️  {table}: 데이터 복사 실패 → {e}")

    sqlite_con.execute("PRAGMA foreign_keys = ON")
    sqlite_con.commit()
    sqlite_con.close()
    mysql_cur.close()
    mysql_con.close()

    size_mb = SQLITE_PATH.stat().st_size / 1024 / 1024
    print(f"\n✨ 완료! SQLite 파일: {SQLITE_PATH}  ({size_mb:.2f} MB)")
    print("\n★ 다른 컴퓨터에서 사용하는 방법:")
    print("  1. seedup_export.db 파일을 복사")
    print("  2. backend/.env 에 아래 줄 추가 (또는 database.py 참고)")
    print("     USE_SQLITE=true")
    print("     SQLITE_PATH=./seedup_export.db")
    print("  3. database_sqlite.py 를 database.py 대신 임포트하여 사용")


if __name__ == "__main__":
    main()
