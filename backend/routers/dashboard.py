from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
from datetime import datetime, timedelta
from pykrx import stock
import pandas as pd
import json
import os
from dotenv import load_dotenv

# OpenAI API 사용 (선택사항)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

load_dotenv()

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Response Models
class MarketWeatherResponse(BaseModel):
    weather: str
    score: int
    recommendation: str
    hint: str

class TradingTrendResponse(BaseModel):
    date: str
    market: str
    institution: float
    foreign: float
    individual: float

class MarketIndexResponse(BaseModel):
    market: str
    index: float
    change: float
    change_rate: float
    date: str

class StockRecommendationResponse(BaseModel):
    stock_code: str
    stock_name: str
    current_price: int
    recommendation_type: str
    reason: str

# 유틸리티 함수들
def get_trading_data(days_back: int = 5):
    """최근 N일간의 투자자별 매매동향 데이터 조회"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        fromdate = start_date.strftime("%Y%m%d")
        todate = end_date.strftime("%Y%m%d")
        
        # KOSPI 데이터 가져오기
        df_kospi = stock.get_market_trading_value_by_date(
            fromdate, todate, "KOSPI"
        )
        df_kospi["시장"] = "KOSPI"
        
        # KOSDAQ 데이터 가져오기
        df_kosdaq = stock.get_market_trading_value_by_date(
            fromdate, todate, "KOSDAQ"
        )
        df_kosdaq["시장"] = "KOSDAQ"
        
        # 합치기
        df_all = pd.concat([df_kospi, df_kosdaq])
        df_all = df_all.reset_index()
        
        return df_all
    except Exception as e:
        print(f"Error fetching trading data: {e}")
        return None

def calculate_market_score(institution: float, foreign: float, individual: float) -> int:
    """투자자별 매매동향을 기반으로 시장 점수 계산 (0-100)"""
    # 억원 단위로 변환
    institution_billion = institution / 100_000_000
    foreign_billion = foreign / 100_000_000
    individual_billion = individual / 100_000_000
    
    # 가중치 적용
    score = 50  # 기본 점수
    
    # 외국인 (45%)
    if foreign_billion > 1000:
        score += 22
    elif foreign_billion > 500:
        score += 15
    elif foreign_billion > 0:
        score += 8
    elif foreign_billion > -500:
        score -= 8
    elif foreign_billion > -1000:
        score -= 15
    else:
        score -= 22
    
    # 기관 (35%)
    if institution_billion > 1000:
        score += 17
    elif institution_billion > 500:
        score += 12
    elif institution_billion > 0:
        score += 6
    elif institution_billion > -500:
        score -= 6
    elif institution_billion > -1000:
        score -= 12
    else:
        score -= 17
    
    # 개인 (10% - 역방향)
    if individual_billion > 1000:
        score -= 5
    elif individual_billion > 0:
        score -= 3
    else:
        score += 3
    
    # 0-100 범위로 제한
    return max(0, min(100, score))

def get_weather_from_score(score: int) -> tuple:
    """점수를 기반으로 날씨와 추천 반환"""
    if score >= 80:
        return "맑음", "적극 매수 추천"
    elif score >= 60:
        return "구름조금", "종목 선별 매수"
    elif score >= 40:
        return "흐림", "관망 추천"
    else:
        return "비", "리스크 관리 필요"

def analyze_market_with_llm(trading_data: Dict) -> Dict:
    """LLM을 사용한 시장 분석 (OpenAI API 사용)"""
    if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
        # LLM 없이 기본 분석
        institution = trading_data["institution"]
        foreign = trading_data["foreign"]
        individual = trading_data["individual"]
        
        score = calculate_market_score(institution, foreign, individual)
        weather, recommendation = get_weather_from_score(score)
        
        # 간단한 힌트 생성
        hint = ""
        if foreign > 0 and institution > 0:
            hint = "외국인과 기관의 동반 매수세가 나타나고 있습니다."
        elif foreign > 0:
            hint = "외국인 매수세가 강합니다. 대형주를 주목하세요."
        elif institution > 0:
            hint = "기관의 매수세가 보입니다. 안정적인 장세가 예상됩니다."
        else:
            hint = "매도세가 우세합니다. 신중한 접근이 필요합니다."
        
        return {
            "weather": weather,
            "score": score,
            "recommendation": recommendation,
            "hint": hint
        }
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        system_prompt = """너는 대한민국 주식 시장 수급 분석 전문가이자 친절한 투자 가이드야.
투자자별 매매동향 데이터를 분석하여 시장 점수(0~100)와 날씨를 판단해줘.

가중치:
- 외국인: 45% (순매수가 큰 것이 좋음)
- 기관: 35% (순매수가 큰 것이 좋음)
- 개인: 10% (순매수가 큰 것은 오히려 부정적 신호)

날씨 기준:
- 맑음 (80점 이상): 외국인/기관 동반 순매수
- 구름조금 (60~79점): 외국인 또는 기관 중 하나만 매수
- 흐림 (40~59점): 외국인/기관 매도세, 개인만 매수
- 비 (40점 미만): 외국인/기관 동반 투매

초보 투자자가 이해하기 쉬운 힌트를 제공해줘."""

        user_content = f"""다음 투자자별 매매동향 데이터를 분석해줘:
시장: {trading_data['market']}
기관 순매수: {trading_data['institution']:,.0f}원
외국인 순매수: {trading_data['foreign']:,.0f}원
개인 순매수: {trading_data['individual']:,.0f}원

JSON 형식으로 답변해줘:
{{
    "weather": "날씨",
    "score": 점수,
    "recommendation": "추천",
    "hint": "힌트"
}}"""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.7
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        print(f"LLM analysis error: {e}")
        # Fallback to basic analysis
        institution = trading_data["institution"]
        foreign = trading_data["foreign"]
        individual = trading_data["individual"]
        
        score = calculate_market_score(institution, foreign, individual)
        weather, recommendation = get_weather_from_score(score)
        
        return {
            "weather": weather,
            "score": score,
            "recommendation": recommendation,
            "hint": "시장 분석 중 일시적인 오류가 발생했습니다."
        }

# API 엔드포인트들
@router.get("/trading-trends", response_model=List[TradingTrendResponse])
async def get_trading_trends(days: int = 5):
    """투자자별 매매동향 데이터 조회"""
    try:
        df = get_trading_data(days)
        if df is None or df.empty:
            raise HTTPException(status_code=500, detail="Failed to fetch trading data")
        
        # 데이터 변환
        results = []
        for _, row in df.iterrows():
            results.append({
                "date": row["날짜"].strftime("%Y-%m-%d") if hasattr(row["날짜"], 'strftime') else str(row["날짜"]),
                "market": row["시장"],
                "institution": float(row["기관"]) / 100_000_000,  # 억원 단위
                "foreign": float(row["외국인"]) / 100_000_000,
                "individual": float(row["개인"]) / 100_000_000
            })
        
        return results
    except Exception as e:
        print(f"Error in get_trading_trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market-weather", response_model=MarketWeatherResponse)
async def get_market_weather(market: str = "KOSPI"):
    """시장 날씨 분석"""
    try:
        # 최근 1일 데이터 가져오기
        df = get_trading_data(days_back=1)
        if df is None or df.empty:
            raise HTTPException(status_code=500, detail="Failed to fetch market data")
        
        # 해당 시장 데이터 필터링
        market_data = df[df["시장"] == market]
        if market_data.empty:
            raise HTTPException(status_code=404, detail=f"No data for market: {market}")
        
        # 최신 데이터 가져오기
        latest = market_data.iloc[-1]
        
        trading_data = {
            "market": market,
            "institution": float(latest["기관"]),
            "foreign": float(latest["외국인"]),
            "individual": float(latest["개인"])
        }
        
        # LLM 분석 (또는 기본 분석)
        analysis = analyze_market_with_llm(trading_data)
        
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_market_weather: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market-indices", response_model=List[MarketIndexResponse])
async def get_market_indices():
    """코스피/코스닥 지수 정보"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        yesterday = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d")
        
        results = []
        
        # KOSPI
        try:
            df_kospi = stock.get_index_ohlcv(yesterday, today, "1001")  # KOSPI
            if not df_kospi.empty:
                latest = df_kospi.iloc[-1]
                prev = df_kospi.iloc[-2] if len(df_kospi) > 1 else latest
                
                change = latest["종가"] - prev["종가"]
                change_rate = (change / prev["종가"]) * 100 if prev["종가"] != 0 else 0
                
                results.append({
                    "market": "KOSPI",
                    "index": float(latest["종가"]),
                    "change": float(change),
                    "change_rate": float(change_rate),
                    "date": latest.name.strftime("%Y-%m-%d") if hasattr(latest.name, 'strftime') else str(latest.name)
                })
        except Exception as e:
            print(f"Error fetching KOSPI: {e}")
        
        # KOSDAQ
        try:
            df_kosdaq = stock.get_index_ohlcv(yesterday, today, "2001")  # KOSDAQ
            if not df_kosdaq.empty:
                latest = df_kosdaq.iloc[-1]
                prev = df_kosdaq.iloc[-2] if len(df_kosdaq) > 1 else latest
                
                change = latest["종가"] - prev["종가"]
                change_rate = (change / prev["종가"]) * 100 if prev["종가"] != 0 else 0
                
                results.append({
                    "market": "KOSDAQ",
                    "index": float(latest["종가"]),
                    "change": float(change),
                    "change_rate": float(change_rate),
                    "date": latest.name.strftime("%Y-%m-%d") if hasattr(latest.name, 'strftime') else str(latest.name)
                })
        except Exception as e:
            print(f"Error fetching KOSDAQ: {e}")
        
        if not results:
            raise HTTPException(status_code=500, detail="Failed to fetch market indices")
        
        return results
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_market_indices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stock-recommendations", response_model=List[StockRecommendationResponse])
async def get_stock_recommendations():
    """종목 추천 목록 (더미 데이터)"""
    # 실제로는 DB나 추천 알고리즘에서 가져와야 함
    return [
        {
            "stock_code": "005930",
            "stock_name": "삼성전자",
            "current_price": 75000,
            "recommendation_type": "매수",
            "reason": "반도체 업황 개선 기대"
        },
        {
            "stock_code": "000660",
            "stock_name": "SK하이닉스",
            "current_price": 145000,
            "recommendation_type": "매수",
            "reason": "HBM 수요 증가"
        },
        {
            "stock_code": "035420",
            "stock_name": "NAVER",
            "current_price": 220000,
            "recommendation_type": "보유",
            "reason": "AI 서비스 확대"
        }
    ]

@router.get("/portfolio-recommendations")
async def get_portfolio_recommendations():
    """포트폴리오 추천 목록 (더미 데이터)"""
    return {
        "portfolios": [
            {
                "name": "안정형 포트폴리오",
                "stocks": ["005930", "000660", "051910"],
                "expected_return": 8.5,
                "risk_level": "낮음"
            },
            {
                "name": "성장형 포트폴리오",
                "stocks": ["035420", "035720", "068270"],
                "expected_return": 15.2,
                "risk_level": "중간"
            }
        ]
    }
