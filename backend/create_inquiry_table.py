"""
고객센터 문의 테이블 생성 스크립트
"""
import sys
import traceback

try:
    from database import engine
    from models import Base, CustomerInquiry

    def create_inquiry_table():
        """customer_inquiries 테이블 생성"""
        print("Creating customer_inquiries table...")
        try:
            Base.metadata.create_all(bind=engine)
            print("✓ customer_inquiries table created successfully!")
        except Exception as e:
            print(f"✗ Error creating table: {e}")
            traceback.print_exc()

    if __name__ == "__main__":
        create_inquiry_table()
        
except Exception as e:
    print(f"✗ Import error: {e}")
    traceback.print_exc()
    sys.exit(1)
