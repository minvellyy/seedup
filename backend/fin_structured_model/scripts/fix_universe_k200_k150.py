import pandas as pd
from pathlib import Path

BASE = Path("data/processed/universe.parquet")
INP = Path("data/processed/universe_k200_k150.parquet")
OUT = Path("data/processed/universe_k200_k150_fixed.parquet")

# 우선주 -> 보통주 매핑(회사 corp_code 동일 처리)
PREF_TO_COMMON = {
    "005935": "005930",  # 삼성전자우 -> 삼성전자
    "005385": "005380",  # 현대차우 -> 현대차
    "005387": "005380",  # 현대차2우B -> 현대차
    "000155": "000150",  # 두산우 -> 두산
}

# 6자리 전제 파이프라인을 위해, 문자 포함 종목코드를 보통주 6자리로 정규화
# 미래에셋증권2우B (00680K) -> 미래에셋증권(006800)
NON_6DIGIT_FIX = {
    "00680K": "006800",
}

def _zfill6(x) -> str:
    return str(x).strip().zfill(6)

def main():
    u = pd.read_parquet(INP).copy()
    b = pd.read_parquet(BASE).copy()

    # ticker 표준화(기본: 6자리 zfill)
    u["ticker"] = u["ticker"].astype(str).str.strip()
    b["ticker"] = b["ticker"].astype(str).str.strip().str.zfill(6)

    # 0) 문자 포함 티커 정정(예: 00680K)
    #    - 파이프라인 키는 6자리로 통일
    for bad_tk, good_tk in NON_6DIGIT_FIX.items():
        mask = (u["ticker"] == bad_tk)
        if mask.any():
            u.loc[mask, "ticker"] = good_tk
            # 이름은 그대로 두고 싶으면 유지 (미래에셋증권2우B 표시 유지 가능)
            # 다만 티커는 보통주로 통일됨.

    # 혹시 6자리 숫자인데 공백/이상값 있는 것들 정리
    # (이미 6자리 숫자면 그대로, 아니면 zfill이 부작용 날 수 있어 fullmatch로 제한)
    is_6digit = u["ticker"].astype(str).str.fullmatch(r"\d{6}")
    u.loc[is_6digit, "ticker"] = u.loc[is_6digit, "ticker"].astype(str).str.zfill(6)

    # 1) 우선주 corp_code 보강(보통주 corp_code로)
    #    - 우선주는 ticker는 유지(005935 등)하되 corp_code/corp_name만 보통주 기준으로 맞춤
    for pref, common in PREF_TO_COMMON.items():
        cc = b.loc[b["ticker"] == common, "corp_code"]
        cn = b.loc[b["ticker"] == common, "corp_name"]
        if len(cc) == 0:
            print(f"[WARN] common ticker not found in base: {common} for pref {pref}")
            continue

        u.loc[u["ticker"] == pref, "corp_code"] = cc.iloc[0]
        if len(cn):
            u.loc[u["ticker"] == pref, "corp_name"] = cn.iloc[0]

    # 2) 여전히 corp_code가 비어있는 경우 → base에서 ticker로 직접 재-merge하여 보강
    #    (기존 merge 과정에서 누락된 케이스까지 자동 보강)
    if "corp_code" not in u.columns:
        u["corp_code"] = pd.NA
    if "corp_name" not in u.columns:
        u["corp_name"] = pd.NA

    need = u["corp_code"].isna() | (u["corp_code"].astype(str).str.strip() == "")
    if need.any():
        tmp = u.loc[need, ["ticker"]].merge(
            b[["ticker", "corp_code", "corp_name"]],
            on="ticker",
            how="left",
        )
        u.loc[need, "corp_code"] = tmp["corp_code"].values
        u.loc[need, "corp_name"] = tmp["corp_name"].values

    # 3) 여전히 6자리 숫자가 아닌 ticker는 경고(이제는 거의 없어야 정상)
    bad = u[~u["ticker"].astype(str).str.fullmatch(r"\d{6}")].copy()
    if not bad.empty:
        print("[WARN] non-6digit tickers remain (manual check needed):")
        cols = [c for c in ["ticker", "name", "exchange", "asset_type"] if c in bad.columns]
        print(bad[cols].to_string(index=False))

    # 저장
    OUT.parent.mkdir(parents=True, exist_ok=True)
    u.to_parquet(OUT, index=False)

    miss = u[u["corp_code"].isna() | (u["corp_code"].astype(str).str.strip() == "")][["ticker"] + ([ "name"] if "name" in u.columns else [])]
    print(f"[OK] wrote: {OUT} rows={len(u)}")
    print("corp_code_missing=", float((u["corp_code"].isna() | (u["corp_code"].astype(str).str.strip() == "")).mean()))
    print("still_missing_rows=", len(miss))
    if len(miss):
        print(miss.to_string(index=False))

if __name__ == "__main__":
    main()