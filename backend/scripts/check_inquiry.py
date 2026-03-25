"""
문의 데이터 확인
"""
from database import SessionLocal
from models import CustomerInquiry

def check_inquiry():
    db = SessionLocal()
    try:
        inquiry = db.query(CustomerInquiry).filter(CustomerInquiry.id == 1).first()
        
        if not inquiry:
            print("❌ 문의를 찾을 수 없습니다.")
            return
        
        print(f"📋 문의 ID: {inquiry.id}")
        print(f"📝 제목: {inquiry.title}")
        print(f"📊 상태: {inquiry.status}")
        print(f"👤 사용자 ID: {inquiry.user_id}")
        print(f"📅 작성일: {inquiry.created_at}")
        print(f"\n💬 문의 내용:\n{inquiry.content}")
        print(f"\n✅ 답변:\n{inquiry.answer if inquiry.answer else '(답변 없음)'}")
        print(f"\n⏰ 답변 시간: {inquiry.answered_at if inquiry.answered_at else '(답변 없음)'}")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_inquiry()
