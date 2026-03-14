"""
esg_module - ESG 분석 패키지

사용법:
    from esg_module import analyze_by_stock_code

    result = analyze_by_stock_code("005930")
    # 보고서 없는 종목 → None 반환 (언급 안 함)
    # 있는 종목 → {"risks": "...", "opportunities": "...", ...}
"""
from .analyzer import analyze_by_stock_code

__all__ = ["analyze_by_stock_code"]
