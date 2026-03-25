# 환경변수 확인 스크립트
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# OpenAI API 키 확인
openai_key = os.getenv("OPENAI_API_KEY")
if openai_key:
    print(f"✅ OpenAI API 키가 설정되어 있습니다: {openai_key[:8]}...")
else:
    print("❌ OpenAI API 키가 설정되지 않았습니다.")
    print("backend/.env 파일에 OPENAI_API_KEY=your_api_key 를 추가해주세요.")

# 기타 중요 환경변수 확인
other_vars = ["KIS_APPKEY", "KIS_APPSECRET", "DATABASE_URL"]
for var in other_vars:
    value = os.getenv(var)
    if value:
        print(f"✅ {var}: 설정됨")
    else:
        print(f"ℹ️ {var}: 설정되지 않음")