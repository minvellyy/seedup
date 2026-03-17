"""Pydantic schemas for FastAPI request / response bodies (추천 API)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# 공통
# ─────────────────────────────────────────────

class UserSurveyRequest(BaseModel):
    """DB에서 설문 답변을 불러올 때 사용하는 요청 바디."""
    user_id: int = Field(..., description="DB users.id")
    koscom_score: int = Field(20, description="코스콤 투자성향 점수 (기본 20 = 안전추구형)")
    monthly_override: Optional[int] = Field(None, description="월 투자금 강제 지정(원). 없으면 DB값 사용.")
    total_assets_override: Optional[int] = Field(None, description="총 투자 가능 자산 강제 지정(원).")
    explain_detail: str = Field("detailed", description="설명 수준 'simple' | 'detailed'")
    explain_lang: str = Field("ko", description="설명 언어 'ko' | 'en'")
    explain_style: str = Field("formal", description="설명 톤 'formal' | 'friendly'")


# ─────────────────────────────────────────────
# 개별 주식 추천 응답
# ─────────────────────────────────────────────

class StockFeatures(BaseModel):
    ret_3m: Optional[float] = None
    ret_6m: Optional[float] = None
    ret_1y: Optional[float] = None
    vol_ann: Optional[float] = None
    beta: Optional[float] = None
    mdd: Optional[float] = None
    mc_p10: Optional[float] = None   # MC 1년 기대수익률 하락(10%) 시나리오 (%)
    mc_p50: Optional[float] = None   # MC 1년 기대수익률 중앙값 (%)
    mc_p90: Optional[float] = None   # MC 1년 기대수익률 상승(90%) 시나리오 (%)


class StockItem(BaseModel):
    rank: int
    ticker: str
    name: str
    market: str
    total_score: float
    reasons: List[str]
    features: StockFeatures
    explanation: Optional[str] = None   # LLM / 템플릿 설명문


class StockRecommendationResponse(BaseModel):
    user_id: int
    risk_tier: str                       # 정식 명칭 e.g. "안전추구형"
    risk_grade: str                      # 등급 번호 e.g. "4등급"
    generated_at: str
    items: List[StockItem]


# ─────────────────────────────────────────────
# 포트폴리오 추천 응답
# ─────────────────────────────────────────────

class PortfolioItem(BaseModel):
    ticker: str
    name: str
    asset_type: str                      # "STOCK" | "ETF" | "CASH"
    risk_type: str
    weight: float                        # 0~1 소수
    weight_pct: float                    # 0~100 표시용
    selection_reason: str
    explanation: Optional[str] = None   # LLM / 템플릿 설명문


class BuyPlanItem(BaseModel):
    ticker: str
    name: str
    price_krw: int
    shares: int
    allocated_budget_krw: int
    expected_return_1y_pct: float
    rationale: str


class CapCompliance(BaseModel):
    compliant: bool = True
    violations: List[str] = []
    summary: str = ""


class PerformanceMetrics(BaseModel):
    ann_return_pct: float
    ann_vol_pct: float
    mdd_pct: float
    sharpe: float
    period: str = ""
    interpretation: str = ""


class MonteCarloResult(BaseModel):
    n_simulations: int = 2000
    horizon_days: int = 252
    p10_pct: float
    p50_pct: float
    p90_pct: float
    interpretation: str = ""


class AllocationRulesSummary(BaseModel):
    grade: str
    stock_max_pct: float = 100
    single_stock_max_pct: float = 30
    etf_min_pct: float = 0
    target_weights: Dict[str, float] = {}


class UserProfileSummary(BaseModel):
    user_id: int
    risk_tier: str
    risk_grade: str
    investment_type: str = ""
    horizon_years: int = 3
    monthly_contribution_krw: int = 0
    total_assets_krw: Optional[int] = None


class PortfolioRecommendationResponse(BaseModel):
    risk_tier: str
    risk_grade: str
    generated_at: str
    user_profile: UserProfileSummary
    allocation_rules: AllocationRulesSummary
    portfolio_items: List[PortfolioItem]
    buy_plan: List[BuyPlanItem]
    investable_amount_krw: int
    total_invested_krw: int
    leftover_krw: int
    cap_compliance: CapCompliance
    performance_3y: Optional[PerformanceMetrics] = None
    monte_carlo_1y: Optional[MonteCarloResult] = None
    overall_summary: str
    portfolio_label: str = ""
