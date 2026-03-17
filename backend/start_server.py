"""
FastAPI 서버 시작 스크립트

새로 추가한 엔드포인트를 반영하려면 서버를 재시작해야 합니다.
"""

import sys
import os

# backend 디렉토리를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import uvicorn
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    print("=" * 80)
    print("FastAPI 서버 시작 중...")
    print("주의: reload=False (KIS WS ALREADY IN USE 방지)")
    print("코드 수정 후에는 서버를 수동으로 재시작하세요.")
    print("=" * 80)
    # reload=True 제거: 파일 감시로 인한 워커 재시작 시 KIS appkey 세션이
    # 서버에 60~90초 잔존하여 ALREADY IN USE 오류가 반복 발생함
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
