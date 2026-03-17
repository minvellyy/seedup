"""FastAPI 라우터 — 보유 주식 관리 엔드포인트.

main.py에서 include_router() 로 등록:
    from routers.holdings import router as holdings_router
    app.include_router(holdings_router, prefix="/api")
"""
from __future__ import annotations

import sys
import os
from datetime import datetime
from typing import List, Optional

# ── backend/ 디렉터리를 sys.path에 추가 ──────────────────────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pymysql
import logging as _logging
import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel

from pathlib import Path as _Path
load_dotenv(dotenv_path=_Path(__file__).parent.parent / '.env')

from kis_client import get_current_price

# OpenAI 클라이언트
try:
    from openai import OpenAI
    _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    OPENAI_AVAILABLE = True
except (ImportError, Exception) as e:
    OPENAI_AVAILABLE = False
    _logger.warning(f"OpenAI 사용 불가: {e}")

router = APIRouter(prefix="/holdings", tags=["holdings"])
_logger = _logging.getLogger(__name__)


# ── Pydantic 모델 ──────────────────────────────────────────────────────────
class HoldingCreate(BaseModel):
    user_id: int
    stock_code: str
    stock_name: str
    broker: Optional[str] = None
    account_number: Optional[str] = None
    shares: int
    purchase_price: float
    purchase_date: Optional[str] = None  # YYYY-MM-DD


class HoldingUpdate(BaseModel):
    broker: Optional[str] = None
    account_number: Optional[str] = None
    shares: Optional[int] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[str] = None


class HoldingResponse(BaseModel):
    id: int
    user_id: int
    stock_code: str
    stock_name: str
    broker: Optional[str]
    account_number: Optional[str]
    shares: int
    purchase_price: float
    purchase_date: Optional[str]
    created_at: str
    updated_at: str
    # 추가 계산 필드
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    return_amount: Optional[float] = None
    return_rate: Optional[float] = None


class HoldingsSummary(BaseModel):
    total_purchase_value: float
    total_current_value: float
    total_return_amount: float
    total_return_rate: float
    holdings: List[HoldingResponse]


class ParsedHolding(BaseModel):
    stock_name: str
    stock_code: Optional[str] = None
    shares: Optional[int] = None
    purchase_price: Optional[float] = None
    current_price: Optional[float] = None


class MTSParseResponse(BaseModel):
    success: bool
    holdings: List[ParsedHolding]
    raw_text: Optional[str] = None
    error: Optional[str] = None


# ── DB 연결 헬퍼 ───────────────────────────────────────────────────────────
def _get_db_connection():
    """DB 커넥션 생성"""
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        db=os.getenv("DB_NAME"),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


# ── API 엔드포인트 ─────────────────────────────────────────────────────────
@router.post("", response_model=HoldingResponse)
def create_holding(holding: HoldingCreate):
    """보유 주식 추가"""
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            sql = """
            INSERT INTO user_holdings 
            (user_id, stock_code, stock_name, broker, account_number, shares, purchase_price, purchase_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(sql, (
                holding.user_id,
                holding.stock_code,
                holding.stock_name,
                holding.broker,
                holding.account_number,
                holding.shares,
                holding.purchase_price,
                holding.purchase_date
            ))
            conn.commit()
            holding_id = cur.lastrowid
            
            # 생성된 데이터 조회
            cur.execute("SELECT * FROM user_holdings WHERE id = %s", (holding_id,))
            result = cur.fetchone()
            
        conn.close()
        
        return {
            **result,
            "purchase_date": result["purchase_date"].strftime("%Y-%m-%d") if result["purchase_date"] else None,
            "created_at": result["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": result["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
        }
        
    except Exception as e:
        _logger.error(f"보유 주식 추가 실패: {e}")
        raise HTTPException(status_code=500, detail=f"보유 주식 추가 실패: {str(e)}")


@router.get("/{user_id}", response_model=List[HoldingResponse])
def get_holdings(user_id: int, include_prices: bool = True):
    """사용자의 모든 보유 주식 조회"""
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM user_holdings WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
            results = cur.fetchall()
        conn.close()
        
        # 기본 holding_data 목록 먼저 구성
        holdings_data = []
        for row in results:
            holdings_data.append({
                **row,
                "purchase_date": row["purchase_date"].strftime("%Y-%m-%d") if row["purchase_date"] else None,
                "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
            })

        # 현재가 병렬 조회 (N+1 → 1 round)
        if include_prices and holdings_data:
            codes = [row["stock_code"] for row in results]
            price_map: dict = {}
            max_workers = min(10, len(codes))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                future_to_code = {pool.submit(get_current_price, code): code for code in codes}
                for fut in as_completed(future_to_code):
                    code = future_to_code[fut]
                    try:
                        price_map[code] = fut.result()
                    except Exception as e:
                        _logger.warning(f"종목 {code} 현재가 조회 실패: {e}")

            for i, row in enumerate(results):
                price_info = price_map.get(row["stock_code"])
                if price_info:
                    current_price = price_info["current_price"]
                    current_value = current_price * row["shares"]
                    purchase_value = float(row["purchase_price"]) * row["shares"]
                    return_amount = current_value - purchase_value
                    return_rate = (return_amount / purchase_value * 100) if purchase_value > 0 else 0
                    holdings_data[i].update({
                        "current_price": current_price,
                        "current_value": current_value,
                        "return_amount": return_amount,
                        "return_rate": return_rate
                    })

        return holdings_data
        
    except Exception as e:
        _logger.error(f"보유 주식 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"보유 주식 조회 실패: {str(e)}")


@router.get("/{user_id}/summary", response_model=HoldingsSummary)
def get_holdings_summary(user_id: int):
    """사용자의 보유 주식 요약 정보 (총 보유 금액, 전일 대비, 개별 종목 현재가)"""
    try:
        holdings = get_holdings(user_id, include_prices=True)
        
        total_purchase_value = 0
        total_current_value = 0
        
        for holding in holdings:
            purchase_value = float(holding["purchase_price"]) * holding["shares"]
            total_purchase_value += purchase_value
            
            if holding.get("current_value"):
                total_current_value += holding["current_value"]
            else:
                # 현재가 조회 실패한 경우 매입가로 계산
                total_current_value += purchase_value
        
        total_return_amount = total_current_value - total_purchase_value
        total_return_rate = (total_return_amount / total_purchase_value * 100) if total_purchase_value > 0 else 0
        
        return {
            "total_purchase_value": total_purchase_value,
            "total_current_value": total_current_value,
            "total_return_amount": total_return_amount,
            "total_return_rate": total_return_rate,
            "holdings": holdings
        }
        
    except Exception as e:
        _logger.error(f"보유 주식 요약 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"보유 주식 요약 조회 실패: {str(e)}")


@router.put("/{holding_id}", response_model=HoldingResponse)
def update_holding(holding_id: int, holding: HoldingUpdate):
    """보유 주식 정보 수정"""
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            # 기존 데이터 확인
            cur.execute("SELECT * FROM user_holdings WHERE id = %s", (holding_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="보유 주식을 찾을 수 없습니다")
            
            # 업데이트할 필드만 수정
            update_fields = []
            update_values = []
            
            if holding.broker is not None:
                update_fields.append("broker = %s")
                update_values.append(holding.broker)
            if holding.account_number is not None:
                update_fields.append("account_number = %s")
                update_values.append(holding.account_number)
            if holding.shares is not None:
                update_fields.append("shares = %s")
                update_values.append(holding.shares)
            if holding.purchase_price is not None:
                update_fields.append("purchase_price = %s")
                update_values.append(holding.purchase_price)
            if holding.purchase_date is not None:
                update_fields.append("purchase_date = %s")
                update_values.append(holding.purchase_date)
            
            if not update_fields:
                raise HTTPException(status_code=400, detail="수정할 필드가 없습니다")
            
            update_values.append(holding_id)
            sql = f"UPDATE user_holdings SET {', '.join(update_fields)} WHERE id = %s"
            cur.execute(sql, tuple(update_values))
            conn.commit()
            
            # 수정된 데이터 조회
            cur.execute("SELECT * FROM user_holdings WHERE id = %s", (holding_id,))
            result = cur.fetchone()
            
        conn.close()
        
        return {
            **result,
            "purchase_date": result["purchase_date"].strftime("%Y-%m-%d") if result["purchase_date"] else None,
            "created_at": result["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": result["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"보유 주식 수정 실패: {e}")
        raise HTTPException(status_code=500, detail=f"보유 주식 수정 실패: {str(e)}")


@router.delete("/{holding_id}")
def delete_holding(holding_id: int):
    """보유 주식 삭제"""
    try:
        conn = _get_db_connection()
        with conn.cursor() as cur:
            # 기존 데이터 확인
            cur.execute("SELECT * FROM user_holdings WHERE id = %s", (holding_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="보유 주식을 찾을 수 없습니다")
            
            cur.execute("DELETE FROM user_holdings WHERE id = %s", (holding_id,))
            conn.commit()
            
        conn.close()
        
        return {"message": "보유 주식이 삭제되었습니다"}
        
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"보유 주식 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail=f"보유 주식 삭제 실패: {str(e)}")


@router.post("/parse-mts-image", response_model=MTSParseResponse)
async def parse_mts_image(file: UploadFile = File(...)):
    """MTS 캡처 이미지에서 보유 주식 정보 추출"""
    if not OPENAI_AVAILABLE:
        raise HTTPException(status_code=500, detail="OpenAI API를 사용할 수 없습니다")
    
    try:
        # 이미지 읽기
        image_data = await file.read()
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # OpenAI Vision API 호출
        response = _openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 MTS(모바일 트레이딩 시스템) 화면 캡처 이미지를 분석하는 전문가입니다.
이미지에서 보유 주식 정보를 추출하여 JSON 형식으로 반환하세요.

추출할 정보:
- stock_name: 종목명 (예: 삼성전자, SK하이닉스)
- stock_code: 종목코드 6자리 (예: 005930, 000660)
- shares: 보유 수량 (숫자만)
- purchase_price: 매입 평균가 또는 매수가 (원 단위, 쉼표 제거)
- current_price: 현재가 (원 단위, 쉼표 제거)

여러 종목이 있을 경우 모두 추출하세요.

응답 형식:
{
  "holdings": [
    {
      "stock_name": "삼성전자",
      "stock_code": "005930",
      "shares": 10,
      "purchase_price": 70000,
      "current_price": 72000
    }
  ]
}

정보를 찾을 수 없는 필드는 null로 설정하세요."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "이 MTS 화면에서 보유 주식 정보를 추출해주세요."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,
            temperature=0.1
        )
        
        # 응답 파싱
        result_text = response.choices[0].message.content
        _logger.info(f"OpenAI 응답: {result_text}")
        
        # JSON 추출 (마크다운 코드 블록 제거)
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        parsed_data = json.loads(result_text)
        holdings = parsed_data.get("holdings", [])
        
        return MTSParseResponse(
            success=True,
            holdings=[ParsedHolding(**h) for h in holdings],
            raw_text=result_text
        )
        
    except json.JSONDecodeError as e:
        _logger.error(f"JSON 파싱 실패: {e}, 응답: {result_text}")
        return MTSParseResponse(
            success=False,
            holdings=[],
            error=f"응답 파싱 실패: {str(e)}",
            raw_text=result_text
        )
    except Exception as e:
        _logger.error(f"이미지 분석 실패: {e}")
        return MTSParseResponse(
            success=False,
            holdings=[],
            error=str(e)
        )
