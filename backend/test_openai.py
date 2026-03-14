"""
OpenAI API 연결 테스트
.env에 설정된 API 키로 간단한 요청을 보내서 연결 상태를 확인합니다.
"""
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def test_openai_api():
    """OpenAI API 연결 테스트"""
    
    # API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    print(f"API 키: {api_key[:8] if api_key else 'None'}...")
    
    if not api_key or api_key == "pp_env":
        print("❌ OpenAI API 키가 올바르게 설정되지 않았습니다.")
        print("backend/.env 파일을 확인해주세요.")
        return False
    
    try:
        import openai
        
        # OpenAI 클라이언트 생성
        client = openai.OpenAI(api_key=api_key)
        print("✅ OpenAI 클라이언트 생성 성공")
        
        # 간단한 요청 테스트
        print("🔄 API 호출 테스트 중...")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "안녕하세요! 간단히 인사만 해주세요."}
            ],
            max_tokens=50,
            temperature=0.5
        )
        
        message = response.choices[0].message.content
        print(f"✅ API 호출 성공!")
        print(f"응답: {message}")
        return True
        
    except openai.AuthenticationError as e:
        print(f"❌ 인증 오류: {str(e)}")
        print("API 키가 잘못되었거나 유효하지 않습니다.")
        return False
        
    except openai.RateLimitError as e:
        print(f"❌ 요청 한도 초과: {str(e)}")
        print("API 사용량 한도에 도달했습니다.")
        return False
        
    except openai.APIConnectionError as e:
        print(f"❌ 연결 오류: {str(e)}")
        print("인터넷 연결을 확인해주세요.")
        return False
        
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {str(e)}")
        return False

if __name__ == "__main__":
    print("OpenAI API 연결 테스트 시작!")
    print("=" * 50)
    
    success = test_openai_api()
    
    print("=" * 50)
    if success:
        print("🎉 OpenAI API 연결이 정상적으로 작동합니다!")
    else:
        print("💡 문제 해결 방법:")
        print("1. .env 파일에 올바른 API 키가 설정되었는지 확인")
        print("2. API 키가 sk-로 시작하는지 확인")
        print("3. OpenAI 계정에 충분한 크레딧이 있는지 확인")