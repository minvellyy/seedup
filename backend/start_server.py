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
    print("=" * 80)
    print("FastAPI 서버 시작 중...")
    print("새 엔드포인트:")
    print("  - GET /api/dashboard/portfolio-history")
    print("=" * 80)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
