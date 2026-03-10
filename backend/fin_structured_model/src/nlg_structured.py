# src/nlg_structured.py
from __future__ import annotations
import math
from typing import Any, Dict, Optional

def _is_na(x: Any) -> bool:
    try:
        return x is None or (isinstance(x, float) and math.isnan(x))
    except Exception:
        return x is None

def _pct(x: Any, nd: int = 2) -> Optional[str]:
    if _is_na(x):
        return None
    return f"{float(x)*100:.{nd}f}%"

def _num(x: Any, nd: int = 2) -> Optional[str]:
    if _is_na(x):
        return None
    return f"{float(x):.{nd}f}"

def _bucket(val: float, cuts: list[float], labels: list[str]) -> str:
    # cuts: ascending thresholds, labels: len(cuts)+1
    for i, c in enumerate(cuts):
        if val < c:
            return labels[i]
    return labels[-1]

def make_narrative(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload: export_structured_report.py에서 만든 JSON dict (metrics/flags/summary 포함)
    returns: {"narrative": [..lines..], "highlights":[..], "warnings":[..]}
    """
    t = payload.get("ticker")
    as_of = payload.get("as_of")
    summ = payload.get("summary", {})
    metrics = payload.get("metrics", {})
    flags = payload.get("flags", {})

    grade = summ.get("overall_grade")
    score = summ.get("overall_score")

    prof = metrics.get("profitability", {})
    grow = metrics.get("growth", {})
    stab = metrics.get("stability", {})
    val = metrics.get("valuation", {})
    price = metrics.get("price", {})

    opm = prof.get("opm")
    roa = prof.get("roa")
    debt_eq = stab.get("debt_equity")
    cur_ratio = stab.get("current_ratio")
    per = val.get("per")
    pbr = val.get("pbr")

    ret_3m = price.get("ret_3m")
    dd_52w = price.get("dd_52w")
    price_source = price.get("price_source")

    sales_yoy = grow.get("sales_yoy")
    opinc_yoy = grow.get("op_income_yoy")

    highlights: list[str] = []
    warnings: list[str] = []
    lines: list[str] = []

    # 0) 헤더
    score_txt = "N/A" if _is_na(score) else f"{float(score):.2f}"
    lines.append(f"{t} | {as_of} 기준 정형 분석: {grade} (종합 {score_txt})")

    # 1) 수익성
    opm_txt = _pct(opm)
    roa_txt = _pct(roa)
    if opm_txt is None and roa_txt is None:
        lines.append("수익성: 산출 데이터가 부족해 평가를 보류합니다.")
    else:
        # 버킷
        if not _is_na(opm):
            opm_level = _bucket(float(opm), [0.03, 0.10], ["낮은 편", "보통", "우수"])
        else:
            opm_level = None
        if not _is_na(roa):
            roa_level = _bucket(float(roa), [0.02, 0.07], ["낮은 편", "보통", "우수"])
        else:
            roa_level = None

        parts = []
        if opm_txt is not None:
            parts.append(f"OPM {opm_txt}({opm_level})")
        if roa_txt is not None:
            parts.append(f"ROA {roa_txt}({roa_level})")
        lines.append("수익성: " + ", ".join(parts))

        if opm_txt is not None and float(opm) >= 0.10:
            highlights.append("영업이익률이 높은 편")
        if roa_txt is not None and float(roa) < 0.02:
            warnings.append("ROA가 낮아 자산 효율이 약한 편")

    # 2) 성장성(없으면 보류)
    if _is_na(sales_yoy) and _is_na(opinc_yoy):
        lines.append("성장성: 전년 비교(TTM YoY) 데이터가 부족해 평가를 보류합니다.")
    else:
        sy = _pct(sales_yoy)
        oy = _pct(opinc_yoy)
        parts = []
        if sy is not None:
            parts.append(f"매출 YoY {sy}")
        if oy is not None:
            parts.append(f"영업이익 YoY {oy}")
        lines.append("성장성: " + ", ".join(parts))

    # 3) 안정성
    if not _is_na(debt_eq):
        de = float(debt_eq)
        de_level = _bucket(de, [0.5, 1.5], ["매우 안정", "보통", "주의"])
        if de >= 1.5:
            warnings.append("부채/자본 비율이 높아 재무 레버리지 부담 가능")
    else:
        de_level = None

    if not _is_na(cur_ratio):
        cr = float(cur_ratio)
        cr_level = _bucket(cr, [1.0, 2.0], ["주의", "보통", "양호"])
        if cr < 1.0:
            warnings.append("유동비율이 1 미만으로 단기 유동성 리스크")
        if cr >= 2.0:
            highlights.append("유동비율이 높아 단기 유동성은 양호")
    else:
        cr_level = None

    de_txt = _num(debt_eq)
    cr_txt = _num(cur_ratio)
    if de_txt is None and cr_txt is None:
        lines.append("안정성: 산출 데이터가 부족해 평가를 보류합니다.")
    else:
        parts = []
        if de_txt is not None:
            parts.append(f"부채/자본 {de_txt}({de_level})")
        if cr_txt is not None:
            parts.append(f"유동비율 {cr_txt}({cr_level})")
        lines.append("안정성: " + ", ".join(parts))

    # 4) 밸류에이션
    if _is_na(per) and _is_na(pbr):
        lines.append("밸류에이션: PER/PBR 산출 데이터가 부족해 평가를 보류합니다.")
    else:
        per_txt = _num(per)
        pbr_txt = _num(pbr)
        parts = []
        if per_txt is not None:
            # PER 단순 버킷 (산업별 보정은 나중 단계)
            per_level = _bucket(float(per), [10, 25], ["낮은 편", "보통", "높은 편"])
            parts.append(f"PER {per_txt}({per_level})")
            if float(per) < 10:
                highlights.append("PER이 낮아 상대적 저평가 가능성(업황/이익 변동 고려)")
            if float(per) >= 25:
                warnings.append("PER이 높아 밸류 부담 가능성")
        if pbr_txt is not None:
            pbr_level = _bucket(float(pbr), [1.0, 3.0], ["낮은 편", "보통", "높은 편"])
            parts.append(f"PBR {pbr_txt}({pbr_level})")
            if float(pbr) < 1.0:
                highlights.append("PBR 1 미만(자산가치 대비 낮게 거래 가능성)")
        lines.append("밸류에이션: " + ", ".join(parts))

    # 5) 가격/리스크(모멘텀 + 낙폭)
    if _is_na(ret_3m) and _is_na(dd_52w):
        lines.append("주가 흐름: 가격 데이터가 부족해 평가를 보류합니다.")
    else:
        r3 = _pct(ret_3m)
        dd = _pct(dd_52w)
        parts = []
        if r3 is not None:
            r3_level = _bucket(float(ret_3m), [-0.10, 0.10], ["약세", "중립", "강세"])
            parts.append(f"3개월 {r3}({r3_level})")
        if dd is not None:
            # dd_52w는 음수(낙폭) 값
            ddv = float(dd_52w)
            if ddv <= -0.40:
                warnings.append("52주 낙폭이 -40% 이하로 변동성/리스크가 큰 편")
                dd_level = "경고"
            elif ddv <= -0.20:
                dd_level = "주의"
            else:
                dd_level = "양호"
            parts.append(f"52주 낙폭 {dd}({dd_level})")
        src = f" (source: {price_source})" if price_source else ""
        lines.append("주가 흐름: " + ", ".join(parts) + src)

    # 6) 데이터 품질(플래그 기반)
    dq = []
    if bool(flags.get("ttm_net_income_proxy", False)):
        dq.append("순이익 일부 구간 대체 산출")
    if not bool(flags.get("has_cashflow", True)):
        dq.append("현금흐름 지표 누락")
    if bool(flags.get("price_missing", False)):
        dq.append("가격 데이터 일부 누락")
    if dq:
        lines.append("데이터 품질: " + ", ".join(dq) + " → 해석 시 주의")
    else:
        lines.append("데이터 품질: 주요 결측/대체 이슈 없음")

    # 7) 결론(한 줄)
    if warnings:
        lines.append("체크포인트: " + "; ".join(warnings[:3]))
    elif highlights:
        lines.append("포인트: " + "; ".join(highlights[:3]))
    else:
        lines.append("포인트: 주요 지표는 중립 범위")

    return {"narrative": lines, "highlights": highlights, "warnings": warnings}