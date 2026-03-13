"""
고객센터 문의 관련 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from database import get_db
from models import CustomerInquiry, User

router = APIRouter(prefix="/api/inquiries", tags=["inquiry"])


# ═══ Pydantic 모델 ═══
class InquiryCreate(BaseModel):
    """문의 생성 요청"""
    user_id: int
    inquiry_type: str
    title: str
    content: str


class InquiryResponse(BaseModel):
    """문의 응답"""
    id: int
    user_id: int
    inquiry_type: str
    title: str
    content: str
    status: str
    answer: Optional[str] = None
    answered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InquiryListItem(BaseModel):
    """문의 목록 아이템"""
    id: int
    inquiry_type: str
    title: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ═══ API 엔드포인트 ═══

@router.post("", response_model=InquiryResponse)
def create_inquiry(
    inquiry_data: InquiryCreate,
    db: Session = Depends(get_db)
):
    """
    새로운 문의 생성
    """
    # 사용자 확인
    user = db.query(User).filter(User.id == inquiry_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    # 문의 생성
    new_inquiry = CustomerInquiry(
        user_id=inquiry_data.user_id,
        inquiry_type=inquiry_data.inquiry_type,
        title=inquiry_data.title,
        content=inquiry_data.content,
        status='pending'
    )
    
    db.add(new_inquiry)
    db.commit()
    db.refresh(new_inquiry)
    
    return new_inquiry


@router.get("", response_model=List[InquiryListItem])
def get_inquiries(
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    사용자의 문의 목록 조회
    """
    inquiries = db.query(CustomerInquiry)\
        .filter(CustomerInquiry.user_id == user_id)\
        .order_by(desc(CustomerInquiry.created_at))\
        .offset(skip)\
        .limit(limit)\
        .all()
    
    return inquiries


@router.get("/{inquiry_id}", response_model=InquiryResponse)
def get_inquiry(
    inquiry_id: int,
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    특정 문의 상세 조회
    """
    inquiry = db.query(CustomerInquiry)\
        .filter(
            CustomerInquiry.id == inquiry_id,
            CustomerInquiry.user_id == user_id
        )\
        .first()
    
    if not inquiry:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다")
    
    return inquiry


@router.delete("/{inquiry_id}")
def delete_inquiry(
    inquiry_id: int,
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    문의 삭제
    """
    inquiry = db.query(CustomerInquiry)\
        .filter(
            CustomerInquiry.id == inquiry_id,
            CustomerInquiry.user_id == user_id
        )\
        .first()
    
    if not inquiry:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다")
    
    db.delete(inquiry)
    db.commit()
    
    return {"message": "문의가 삭제되었습니다"}
