from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import random

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

# Response Models
class StockChartData(BaseModel):
    date: str
    price: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None

class CompanyInfo(BaseModel):
    ceo: str
    founded_date: str
    industry: str
    business_area: str
    market_cap: str
    market_type: str  # KOSPI/KOSDAQ

class InvestmentFit(BaseModel):
    score: int  # 0-100
    summary: str
    details: List[str]

class ComprehensiveAnalysis(BaseModel):
    profitability: int  # 0-100
    growth: int
    stability: int
    dividend: int
    market_interest: int

class StockRecommendation(BaseModel):
    stock_code: str
    stock_name: str
    current_price: int
    price_change: int
    price_change_percent: float
    recommendation_reason: str
    chart_data: List[StockChartData]
    company_info: Optional[CompanyInfo] = None
    investment_fit: Optional[InvestmentFit] = None
    industry_analysis: Optional[List[str]] = None
    comprehensive_analysis: Optional[ComprehensiveAnalysis] = None

class PortfolioAsset(BaseModel):
    stock_name: str
    stock_code: str
    allocation_percent: float
    analysis: Optional[str] = None  # 해당 종목을 넣은 이유

class PortfolioRecommendation(BaseModel):
    portfolio_id: int
    portfolio_name: str
    assets: List[PortfolioAsset]
    recommendation_reason: str
    expected_return: float
    risk_level: str
    short_term_return: Optional[float] = None  # 단기 수익률 (3개월)
    mid_long_term_return: Optional[float] = None  # 중장기 수익률 (1년)
    risk_analysis: Optional[str] = None  # LLM 생성 리스크 분석

class RecommendationsResponse(BaseModel):
    stocks: List[StockRecommendation]
    portfolios: List[PortfolioRecommendation]

# 더미 차트 데이터 생성 함수
def generate_dummy_chart_data(base_price: int, days: int = 30) -> List[StockChartData]:
    """더미 주가 차트 데이터 생성 (캔들스틱 포함)"""
    chart_data = []
    current_price = base_price
    start_date = datetime.now() - timedelta(days=days)
    
    for i in range(days):
        date = start_date + timedelta(days=i)
        
        # 시가
        open_price = current_price
        
        # 랜덤하게 ±3% 변동
        change_percent = random.uniform(-0.03, 0.03)
        close_price = int(current_price * (1 + change_percent))
        
        # 고가/저가 계산
        high_price = int(max(open_price, close_price) * random.uniform(1.0, 1.02))
        low_price = int(min(open_price, close_price) * random.uniform(0.98, 1.0))
        
        chart_data.append(StockChartData(
            date=date.strftime("%Y-%m-%d"),
            price=float(close_price),
            open=float(open_price),
            high=float(high_price),
            low=float(low_price),
            close=float(close_price)
        ))
        
        current_price = close_price
    
    return chart_data

# 더미 데이터
def get_dummy_stock_recommendations() -> List[StockRecommendation]:
    """종목 Top3 더미 데이터"""
    
    stocks = [
        {
            "stock_code": "005930",
            "stock_name": "삼성전자",
            "base_price": 70000,
            "current_price": 71500,
            "price_change": 1500,
            "price_change_percent": 2.14,
            "recommendation_reason": "반도체 업황 회복과 AI 수요 증가로 실적 개선이 예상됩니다. 메모리 반도체 가격 상승과 함께 파운드리 사업 확대가 기대되며, 안정적인 배당 정책으로 장기 투자에 적합합니다.",
            "company_info": {
                "ceo": "한종희",
                "founded_date": "1969-01-13",
                "industry": "전기전자",
                "business_area": "반도체, 디스플레이, 모바일, 가전",
                "market_cap": "약 426조원",
                "market_type": "KOSPI"
            },
            "investment_fit": {
                "score": 85,
                "summary": "귀하의 안정 중시 투자 성향에 적합한 종목입니다.",
                "details": [
                    "✓ 대형 우량주로 변동성이 낮아 안정적인 투자 가능",
                    "✓ 꾸준한 배당 지급으로 배당 수익 기대 가능",
                    "✓ 글로벌 시장 지배력으로 장기 성장 가능성 높음",
                    "△ 단기적 급등보다는 중장기 관점 투자 권장"
                ]
            },
            "industry_analysis": [
                "반도체 산업은 AI, 데이터센터, 자율주행 등의 성장으로 중장기 수요 전망이 밝습니다.",
                "메모리 반도체 가격이 상승 국면에 진입하며 실적 개선이 예상됩니다.",
                "파운드리 사업 확대로 사업 포트폴리오가 다각화되고 있습니다.",
                "글로벌 공급망 재편 과정에서 한국 반도체 산업의 중요성이 증대되고 있습니다."
            ],
            "comprehensive_analysis": {
                "profitability": 80,
                "growth": 75,
                "stability": 90,
                "dividend": 70,
                "market_interest": 85
            }
        },
        {
            "stock_code": "373220",
            "stock_name": "LG에너지솔루션",
            "base_price": 380000,
            "current_price": 395000,
            "price_change": 15000,
            "price_change_percent": 3.95,
            "recommendation_reason": "전기차 시장 성장과 함께 2차 전지 수요가 지속적으로 증가하고 있습니다. 북미 시장 점유율 확대와 신규 공장 가동으로 중장기 성장성이 높으며, ESG 투자 트렌드에도 부합합니다.",
            "company_info": {
                "ceo": "권영수",
                "founded_date": "2020-12-01",
                "industry": "전기전자",
                "business_area": "2차 전지(배터리), ESS",
                "market_cap": "약 92조원",
                "market_type": "KOSPI"
            },
            "investment_fit": {
                "score": 88,
                "summary": "귀하의 성장 지향 투자 성향에 매우 적합한 종목입니다.",
                "details": [
                    "✓ 전기차 시장 급성장으로 높은 성장 가능성",
                    "✓ 글로벌 배터리 시장에서 상위 3위 점유율",
                    "✓ ESG 투자 트렌드에 부합하는 친환경 사업",
                    "△ 초기 성장 단계로 단기 변동성 존재"
                ]
            },
            "industry_analysis": [
                "전기차 시장은 연평균 20% 이상 성장하며 2차 전지 수요를 견인하고 있습니다.",
                "글로벌 탄소중립 정책으로 ESS(에너지저장장치) 수요도 급증하고 있습니다.",
                "북미 IRA(인플레이션 감축법) 수혜로 미국 시장 점유율 확대가 기대됩니다.",
                "배터리 기술 혁신으로 에너지 밀도 향상 및 원가 절감이 진행 중입니다."
            ],
            "comprehensive_analysis": {
                "profitability": 70,
                "growth": 95,
                "stability": 65,
                "dividend": 40,
                "market_interest": 90
            }
        },
        {
            "stock_code": "035720",
            "stock_name": "카카오",
            "base_price": 45000,
            "current_price": 47200,
            "price_change": 2200,
            "price_change_percent": 4.89,
            "recommendation_reason": "플랫폼 사업 다각화와 AI 기술 접목으로 새로운 성장 동력을 확보했습니다. 카카오톡 기반의 안정적인 수익 구조와 함께 금융, 모빌리티, 커머스 등 다양한 분야에서 시너지 효과가 기대됩니다.",
            "company_info": {
                "ceo": "정신아",
                "founded_date": "1995-02-16",
                "industry": "IT서비스",
                "business_area": "메신저, 콘텐츠, 광고, 핀테크, 모빌리티",
                "market_cap": "약 20조원",
                "market_type": "KOSPI"
            },
            "investment_fit": {
                "score": 78,
                "summary": "균형잡힌 투자 포트폴리오에 적합한 IT 플랫폼 종목입니다.",
                "details": [
                    "✓ 카카오톡 기반 안정적인 수익 구조 확보",
                    "✓ 다양한 사업 영역으로 성장 동력 다각화",
                    "✓ AI 기술 활용으로 미래 경쟁력 강화",
                    "△ 규제 리스크와 경쟁 심화 주시 필요"
                ]
            },
            "industry_analysis": [
                "국내 메신저 시장 독보적 1위로 5천만 이상의 월간 활성 사용자 보유",
                "AI 챗봇, 이미지 생성 등 생성형 AI 서비스를 빠르게 도입하고 있습니다.",
                "카카오페이, 카카오뱅크 등 금융 부문이 새로운 수익원으로 성장 중입니다.",
                "카카오모빌리티, 카카오엔터 등 자회사들의 성장으로 시너지 효과 증대"
            ],
            "comprehensive_analysis": {
                "profitability": 75,
                "growth": 80,
                "stability": 70,
                "dividend": 50,
                "market_interest": 82
            }
        }
    ]
    
    return [
        StockRecommendation(
            stock_code=stock["stock_code"],
            stock_name=stock["stock_name"],
            current_price=stock["current_price"],
            price_change=stock["price_change"],
            price_change_percent=stock["price_change_percent"],
            recommendation_reason=stock["recommendation_reason"],
            chart_data=generate_dummy_chart_data(stock["base_price"], days=30),
            company_info=CompanyInfo(**stock["company_info"]) if "company_info" in stock else None,
            investment_fit=InvestmentFit(**stock["investment_fit"]) if "investment_fit" in stock else None,
            industry_analysis=stock.get("industry_analysis"),
            comprehensive_analysis=ComprehensiveAnalysis(**stock["comprehensive_analysis"]) if "comprehensive_analysis" in stock else None
        )
        for stock in stocks
    ]

def get_dummy_portfolio_recommendations() -> List[PortfolioRecommendation]:
    """포트폴리오 Top3 더미 데이터"""
    
    portfolios = [
        {
            "portfolio_id": 1,
            "portfolio_name": "안정 성장형 포트폴리오",
            "assets": [
                {
                    "stock_name": "삼성전자",
                    "stock_code": "005930",
                    "allocation_percent": 30.0,
                    "analysis": "반도체 산업의 리더로서 안정적인 실적과 배당을 제공합니다. 포트폴리오의 핵심 자산으로 전체 안정성을 높입니다."
                },
                {
                    "stock_name": "NAVER",
                    "stock_code": "035420",
                    "allocation_percent": 20.0,
                    "analysis": "국내 IT 플랫폼 1위 기업으로 안정적인 광고 수익과 함께 AI, 클라우드 등 신성장 동력을 보유하고 있습니다."
                },
                {
                    "stock_name": "SK하이닉스",
                    "stock_code": "000660",
                    "allocation_percent": 20.0,
                    "analysis": "메모리 반도체 업황 회복으로 실적 개선이 예상되며, AI 반도체 수요 증가로 중장기 성장이 기대됩니다."
                },
                {
                    "stock_name": "현대차",
                    "stock_code": "005380",
                    "allocation_percent": 15.0,
                    "analysis": "전기차 전환과 함께 미래 모빌리티 사업 확장으로 성장성을 확보하면서도 안정적인 현금흐름을 제공합니다."
                },
                {
                    "stock_name": "KB금융",
                    "stock_code": "105560",
                    "allocation_percent": 15.0,
                    "analysis": "금융주로서 안정적인 배당 수익과 함께 경기 회복 시 수익성 개선이 기대되는 방어주입니다."
                }
            ],
            "recommendation_reason": "안정적인 대형주 중심으로 구성하여 변동성을 최소화하면서도 꾸준한 수익을 추구합니다. 업종을 분산하여 리스크를 관리하며, 배당 수익도 기대할 수 있는 포트폴리오입니다.",
            "expected_return": 8.5,
            "risk_level": "중",
            "short_term_return": 5.2,
            "mid_long_term_return": 12.3,
            "risk_analysis": "대형 우량주 중심으로 구성되어 시장 변동성 대비 안정적인 수익률을 보일 것으로 예상됩니다. 다만 반도체 경기 사이클에 따른 단기 변동성이 존재하며, 금리 인상 국면에서는 금융주의 실적 개선 효과가 제한적일 수 있습니다. 업종 분산을 통해 특정 산업 리스크를 최소화했으며, 중장기 관점에서 꾸준한 상승을 기대할 수 있습니다."
        },
        {
            "portfolio_id": 2,
            "portfolio_name": "테크 성장형 포트폴리오",
            "assets": [
                {
                    "stock_name": "LG에너지솔루션",
                    "stock_code": "373220",
                    "allocation_percent": 25.0,
                    "analysis": "전기차 시장 급성장으로 2차 전지 수요가 폭발적으로 증가하고 있으며, 글로벌 시장 점유율 확대가 지속될 전망입니다."
                },
                {
                    "stock_name": "카카오",
                    "stock_code": "035720",
                    "allocation_percent": 25.0,
                    "analysis": "플랫폼 기반의 다각화된 사업 구조와 AI 기술 접목으로 새로운 성장 동력을 확보했습니다."
                },
                {
                    "stock_name": "삼성SDI",
                    "stock_code": "006400",
                    "allocation_percent": 20.0,
                    "analysis": "2차 전지와 전자재료 부문에서 강점을 보유하고 있으며, 전기차 배터리 시장에서 높은 성장이 기대됩니다."
                },
                {
                    "stock_name": "NAVER",
                    "stock_code": "035420",
                    "allocation_percent": 20.0,
                    "analysis": "검색/커머스의 안정적인 수익 기반 위에 AI, 클라우드 등 신사업 확장으로 미래 성장성이 높습니다."
                },
                {
                    "stock_name": "크래프톤",
                    "stock_code": "259960",
                    "allocation_percent": 10.0,
                    "analysis": "글로벌 게임 IP를 보유한 성장형 게임사로, 신작 출시와 해외 시장 확대로 높은 성장이 예상됩니다."
                }
            ],
            "recommendation_reason": "IT와 2차 전지 등 고성장 산업에 집중 투자하여 높은 수익률을 목표로 합니다. 미래 성장성이 높은 기업들로 구성되어 있으며, 중장기적인 관점에서 큰 수익을 기대할 수 있습니다.",
            "expected_return": 15.2,
            "risk_level": "높음",
            "short_term_return": 8.7,
            "mid_long_term_return": 22.5,
            "risk_analysis": "고성장 테크 섹터에 집중 투자한 공격적인 포트폴리오로, 높은 수익 잠재력과 함께 상당한 변동성이 예상됩니다. 전기차 시장 성장 둔화나 글로벌 경기 침체 시 주가 조정 가능성이 있으며, 규제 리스크(플랫폼 규제, 게임 규제 등)에 노출되어 있습니다. 다만 2차 전지, AI, 플랫폼 등 미래 핵심 산업에 집중 투자하여 장기적으로 높은 성장이 기대됩니다."
        },
        {
            "portfolio_id": 3,
            "portfolio_name": "배당 중심 포트폴리오",
            "assets": [
                {
                    "stock_name": "삼성전자",
                    "stock_code": "005930",
                    "allocation_percent": 25.0,
                    "analysis": "안정적이고 지속적인 배당 정책을 유지하는 대표적인 배당주로, 시가배당률과 배당 성장성이 우수합니다."
                },
                {
                    "stock_name": "SK텔레콤",
                    "stock_code": "017670",
                    "allocation_percent": 20.0,
                    "analysis": "통신 사업의 안정적인 현금흐름을 기반으로 높은 배당을 지급하며, 방어적 성격의 종목입니다."
                },
                {
                    "stock_name": "KB금융",
                    "stock_code": "105560",
                    "allocation_percent": 20.0,
                    "analysis": "금융지주 중 배당 성향이 높고, 꾸준한 배당 증가 정책을 통해 장기 투자자에게 매력적입니다."
                },
                {
                    "stock_name": "신한지주",
                    "stock_code": "055550",
                    "allocation_percent": 20.0,
                    "analysis": "탄탄한 재무구조를 바탕으로 안정적인 배당을 제공하며, 금융 부문 대표 배당주입니다."
                },
                {
                    "stock_name": "LG화학",
                    "stock_code": "051910",
                    "allocation_percent": 15.0,
                    "analysis": "화학 및 배터리 사업의 실적 개선으로 배당 여력이 확대되고 있으며, 성장성과 배당을 동시에 추구할 수 있습니다."
                }
            ],
            "recommendation_reason": "안정적인 배당 수익을 추구하는 투자자에게 적합한 포트폴리오입니다. 배당 성향이 높고 재무구조가 탄탄한 기업들로 구성되어 있어, 정기적인 현금 수익과 함께 안정적인 자산 운용이 가능합니다.",
            "expected_return": 6.8,
            "risk_level": "낮음",
            "short_term_return": 4.1,
            "mid_long_term_return": 9.5,
            "risk_analysis": "배당 수익 중심의 방어적 포트폴리오로 시장 변동성에 강한 특성을 가지고 있습니다. 금융주와 통신주의 비중이 높아 금리 변동에 민감할 수 있으나, 전체적으로 낮은 변동성과 안정적인 현금흐름이 예상됩니다. 경기 침체기에도 배당 수익으로 손실을 완화할 수 있어 보수적인 투자자에게 적합하며, 시장 급등 시 수익률은 제한적일 수 있습니다."
        }
    ]
    
    return [
        PortfolioRecommendation(
            portfolio_id=p["portfolio_id"],
            portfolio_name=p["portfolio_name"],
            assets=[PortfolioAsset(**asset) for asset in p["assets"]],
            recommendation_reason=p["recommendation_reason"],
            expected_return=p["expected_return"],
            risk_level=p["risk_level"],
            short_term_return=p.get("short_term_return"),
            mid_long_term_return=p.get("mid_long_term_return"),
            risk_analysis=p.get("risk_analysis")
        )
        for p in portfolios
    ]

@router.get("/", response_model=RecommendationsResponse)
async def get_recommendations(user_id: int = None):
    """
    종목 및 포트폴리오 추천 데이터 조회
    - user_id: 사용자 ID (옵션, 향후 개인화된 추천을 위해 사용)
    """
    try:
        stocks = get_dummy_stock_recommendations()
        portfolios = get_dummy_portfolio_recommendations()
        
        return RecommendationsResponse(
            stocks=stocks,
            portfolios=portfolios
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch recommendations: {str(e)}")

@router.get("/stocks/{stock_code}")
async def get_stock_detail(stock_code: str):
    """
    개별 종목 상세 정보 조회
    """
    stocks = get_dummy_stock_recommendations()
    stock = next((s for s in stocks if s.stock_code == stock_code), None)
    
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    return stock

@router.get("/portfolios/{portfolio_id}")
async def get_portfolio_detail(portfolio_id: int):
    """
    개별 포트폴리오 상세 정보 조회
    """
    portfolios = get_dummy_portfolio_recommendations()
    portfolio = next((p for p in portfolios if p.portfolio_id == portfolio_id), None)
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    return portfolio
