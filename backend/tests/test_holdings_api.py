"""보유 주식 API 테스트"""
import requests

BASE_URL = "http://localhost:8000"

# 1. 빈 summary 조회 테스트 (user_id=11)
print("=" * 80)
print("1. GET /api/holdings/11/summary - 빈 데이터 조회")
print("-" * 80)
try:
    response = requests.get(f"{BASE_URL}/api/holdings/11/summary", timeout=5)
    print(f"Status Code: {response.status_code}")
    if response.ok:
        data = response.json()
        print(f"Response: {data}")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"❌ 요청 실패: {e}")

print("\n" + "=" * 80)
print("2. POST /api/holdings - 테스트 주식 등록 (삼성전자)")
print("-" * 80)
test_holding = {
    "user_id": 11,
    "stock_code": "005930",
    "stock_name": "삼성전자",
    "broker": "kb",
    "account_number": "123456789",
    "shares": 10,
    "purchase_price": 70000,
    "purchase_date": "2024-01-15"
}
try:
    response = requests.post(f"{BASE_URL}/api/holdings", json=test_holding, timeout=5)
    print(f"Status Code: {response.status_code}")
    if response.ok:
        data = response.json()
        print(f"등록 성공! ID: {data['id']}")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"❌ 요청 실패: {e}")

print("\n" + "=" * 80)
print("3. GET /api/holdings/11/summary - 등록 후 조회")
print("-" * 80)
try:
    response = requests.get(f"{BASE_URL}/api/holdings/11/summary", timeout=10)
    print(f"Status Code: {response.status_code}")
    if response.ok:
        data = response.json()
        print(f"총 보유 금액: {data['total_current_value']:,.0f}원")
        print(f"총 손익: {data['total_return_amount']:,.0f}원 ({data['total_return_rate']:.2f}%)")
        print(f"보유 종목 수: {len(data['holdings'])}개")
        for h in data['holdings']:
            print(f"  - {h['stock_name']} ({h['stock_code']}): {h['shares']}주")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"❌ 요청 실패: {e}")

print("\n완료!")
