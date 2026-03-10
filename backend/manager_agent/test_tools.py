"""manager_agent 툴 동작 확인 스크립트 (LLM 없이 데이터 읽기만 테스트)"""
import sys, json
sys.path.insert(0, ".")

from manager_agent.tools.fin_structured_tool import _load_report
from manager_agent.tools.stock_direction_tool import _load_signal_pack
from manager_agent.tools.unstructured_tool import _load_unstructured

TICKER = "051910"

# 1) fin_structured
print("=" * 60)
print(f"[1] fin_structured_model → structured_report.json ({TICKER})")
print("=" * 60)
r = _load_report(TICKER)
if r:
    print(json.dumps(r, ensure_ascii=False, indent=2)[:1200])
else:
    print("NOT FOUND in structured_report.json")

# 2) stock_direction
print()
print("=" * 60)
print(f"[2] stock_direction_model → signal_pack_latest.csv ({TICKER})")
print("=" * 60)
df = _load_signal_pack()
if df is None:
    print("signal_pack_latest.csv 없음")
else:
    row = df[df["ticker"] == TICKER]
    cols = [c for c in ["ticker","name","date","p_up","p_adj","rank_overall","rank_in_asset","regime"] if c in df.columns]
    if not row.empty:
        print(row[cols].to_string(index=False))
    else:
        print(f"NOT FOUND. 전체 종목 수: {len(df)}")
        print("샘플:", df["ticker"].head(5).tolist())

# 3) unstructured (placeholder)
print()
print("=" * 60)
print(f"[3] unstructured_model → placeholder ({TICKER})")
print("=" * 60)
u = _load_unstructured(TICKER)
print(u if u else "PENDING (정상 — 모듈 개발 중)")
