"""주식 등록 테스트 - 매입일 없이"""
import requests
import json

BASE_URL = "http://localhost:8000"

# 매입일 없이 등록 테스트
test_holding = {
    "user_id": 11,
    "stock_code": "005930",
    "stock_name": "삼성전자",
    "broker": "kb",
    "account_number": "123456789",
    "shares": 10,
    "purchase_price": 70000,
    # purchase_date 없음
}

print("=" * 80)
print("매입일 없이 주식 등록 테스트")
print("-" * 80)
print(f"요청 데이터: {json.dumps(test_holding, ensure_ascii=False, indent=2)}")
print()

try:
    response = requests.post(
        f"{BASE_URL}/api/holdings",
        json=test_holding,
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.ok:
        print("\n✅ 등록 성공!")
    else:
        print("\n❌ 등록 실패!")
        
except Exception as e:
    print(f"\n❌ 요청 실패: {e}")
