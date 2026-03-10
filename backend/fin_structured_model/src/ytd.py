import pandas as pd

# 누적(YTD) 컬럼들: 매출/이익 같은 flow 항목만 변환
FLOW_COLS = ["revenue", "op_income", "net_income"]

def ytd_to_quarter(df: pd.DataFrame) -> pd.DataFrame:
    """
    입력 df: 정규화된 분기/반기/3분기/FY 데이터 (ticker, as_of, reprt_code 포함)
    가정: Q1/H1/Q3/FY가 같은 연도에 존재(누적값)
    출력: flow 항목이 분기 단독값으로 변환된 df
    """
    out = df.copy()
    out = out.sort_values(["ticker", "as_of"]).reset_index(drop=True)

    # reprt_code: Q1=11013, H1=11012, Q3=11014, FY=11011
    # 같은 연도 내에서: Q1, H1, Q3, FY 순으로 정렬된 상태라고 가정(우리는 as_of로 정렬됨)
    # 변환 규칙(연도별):
    # Q1 = Q1
    # Q2 = H1 - Q1
    # Q3 = Q3 - H1
    # Q4 = FY - Q3
    out["_year"] = out["as_of"].dt.year

    # year별로 처리
    res = []
    for (tic, y), g in out.groupby(["ticker", "_year"], sort=False):
        g = g.sort_values("as_of").copy()

        # reprt_code별 행을 찾기
        q1 = g[g["reprt_code"] == "11013"]
        h1 = g[g["reprt_code"] == "11012"]
        q3 = g[g["reprt_code"] == "11014"]
        fy = g[g["reprt_code"] == "11011"]

        # 그대로 res에 넣되, 있는 것만 변환
        # Q2는 H1행에 저장(단독값으로)
        if not h1.empty and not q1.empty:
            for c in FLOW_COLS:
                if c in g.columns:
                    g.loc[h1.index, c] = g.loc[h1.index, c].values - g.loc[q1.index, c].values

        # Q3 단독 = Q3 - H1
        if not q3.empty and not h1.empty:
            for c in FLOW_COLS:
                if c in g.columns:
                    g.loc[q3.index, c] = g.loc[q3.index, c].values - g.loc[h1.index, c].values

        # Q4 단독 = FY - Q3
        if not fy.empty and not q3.empty:
            for c in FLOW_COLS:
                if c in g.columns:
                    g.loc[fy.index, c] = g.loc[fy.index, c].values - g.loc[q3.index, c].values

        res.append(g)

    out2 = pd.concat(res, ignore_index=True).drop(columns=["_year"])
    return out2