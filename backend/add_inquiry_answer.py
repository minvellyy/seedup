"""
1:1 문의에 답변 추가하기
"""
from database import SessionLocal
from models import CustomerInquiry
from datetime import datetime

def add_answer_to_inquiry():
    db = SessionLocal()
    try:
        # 첫 번째 pending 상태의 문의 찾기
        inquiry = db.query(CustomerInquiry)\
            .filter(CustomerInquiry.status == 'pending')\
            .first()
        
        if not inquiry:
            print("답변 대기 중인 문의가 없습니다.")
            return
        
        # 답변 추가
        inquiry.answer = """안녕하세요, SeedUp입니다.

문의해주신 내용 확인했습니다.

현재 저희 서비스는 20세 이상 성인을 대상으로 제공되고 있습니다. 투자 활동은 법적으로 성인만 가능하며, 미성년자의 경우 부모님 명의의 계좌를 통해 간접적으로 투자 학습을 하실 수 있습니다.

다만, 저희 서비스의 투자 성향 분석 및 포트폴리오 추천 기능은 교육 목적으로도 활용하실 수 있으니, 성인이 되신 후 실제 투자를 시작하실 때 참고하시면 좋을 것 같습니다.

추가 문의사항이 있으시면 언제든지 문의해주세요.

감사합니다."""
        
        inquiry.status = 'completed'
        inquiry.answered_at = datetime.now()
        
        db.commit()
        
        print(f"✅ 문의 #{inquiry.id} '{inquiry.title}'에 답변이 추가되었습니다.")
        print(f"   문의 유형: {inquiry.inquiry_type}")
        print(f"   답변 시간: {inquiry.answered_at}")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_answer_to_inquiry()
