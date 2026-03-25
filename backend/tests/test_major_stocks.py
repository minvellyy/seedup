#!/usr/bin/env python3
"""주요 종목 실시간 데이터 함수 개별 테스트"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from chatbot_service import get_major_stocks_realtime_data
    print("✅ chatbot_service 임포트 성공")
    
    print("\n🔍 주요 종목 실시간 데이터 테스트")
    print("="*50)
    
    major_data = get_major_stocks_realtime_data()
    
    print(f"📊 데이터 길이: {len(major_data)}자")
    print(f"📄 데이터 내용:\n{major_data}")
    
except Exception as e:
    print(f"❌ 오류 발생: {e}")
    import traceback
    traceback.print_exc()