"""
챗봇 API 라우터
- 투자 전문 챗봇 엔드포인트 제공
- 일반 채팅 및 스트리밍 채팅 지원
- 세션 관리 및 히스토리
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import json

from database import get_db
from models import User
from chatbot_service import (
    chatbot_service, 
    ChatRequest, 
    ChatResponse, 
    ChatSessionInfo
)

router = APIRouter(prefix="/api/chat", tags=["chatbot"])

# ═══ 유틸리티 함수 ═══════════════════════════════════════════════════════════

def get_current_user(user_id: int, db: Session = Depends(get_db)) -> User:
    """현재 사용자 조회 (게스트 사용자 지원)"""
    
    # 게스트 사용자 처리
    if user_id == 999999:
        # 가상의 게스트 사용자 객체 생성
        class GuestUser:
            id = 999999
            username = "게스트"
            investment_type = "보통투자형"
        return GuestUser()
    
    # 일반 사용자 조회
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return user

# ═══ 챗봇 API 엔드포인트 ═══════════════════════════════════════════════════════

@router.post("/send", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    일반 채팅 메시지 전송 (비스트리밍)
    
    - **user_id**: 사용자 ID
    - **message**: 사용자 메시지
    - **session_id**: 세션 ID (없으면 새 세션 생성)
    """
    try:
        # 사용자 검증
        current_user = get_current_user(request.user_id, db)
        
        print(f"[CHATBOT] 메시지 전송 요청: user_id={current_user.id}, message='{request.message}'")
        
        response = await chatbot_service.chat(
            user_id=current_user.id,
            message=request.message,
            session_id=request.session_id
        )
        
        print(f"[CHATBOT] 응답 성공: session_id={response.session_id}")
        return response
        
    except Exception as e:
        print(f"[CHATBOT ERROR] 상세 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        
        raise HTTPException(
            status_code=500, 
            detail=f"챗봇 오류: {str(e)}"
        )

@router.post("/stream")
async def stream_message(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    스트리밍 채팅 메시지 전송
    
    - **user_id**: 사용자 ID
    - **message**: 사용자 메시지
    - **session_id**: 세션 ID (없으면 새 세션 생성)
    
    SSE(Server-Sent Events) 형태로 응답 스트리밍
    """
    try:
        # 사용자 검증
        current_user = get_current_user(request.user_id, db)
        
        async def generate():
            async for chunk in chatbot_service.chat_stream(
                user_id=current_user.id,
                message=request.message,
                session_id=request.session_id
            ):
                # SSE 형식으로 데이터 전송
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            
            # 스트림 종료 신호
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # nginx 버퍼링 비활성화
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스트리밍 챗봇 오류: {str(e)}")

@router.get("/sessions")
async def get_chat_sessions(
    user_id: int = Query(..., description="사용자 ID"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    사용자의 채팅 세션 목록 조회
    
    - **user_id**: 사용자 ID
    - **limit**: 조회할 세션 수 (기본 20, 최대 100)
    """
    try:
        # 사용자 검증
        current_user = get_current_user(user_id, db)
        
        sessions = chatbot_service.get_user_sessions(
            user_id=current_user.id,
            limit=limit
        )
        
        # 프론트엔드가 기대하는 형식으로 응답
        return {
            "success": True,
            "sessions": [
                {
                    "id": session.session_id,
                    "title": session.title or "새로운 대화",
                    "created_at": session.created_at.isoformat() if session.created_at else None,
                    "updated_at": session.updated_at.isoformat() if session.updated_at else None
                }
                for session in sessions
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"세션 조회 오류: {str(e)}",
            "sessions": []
        }

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user_id: int = Query(..., description="사용자 ID"),
    db: Session = Depends(get_db)
):
    """
    특정 세션의 메시지 히스토리 조회
    
    - **session_id**: 세션 ID
    - **user_id**: 사용자 ID
    """
    try:
        from chatbot_service import get_conversation_history
        from models import ChatSession
        
        # 사용자 검증
        current_user = get_current_user(user_id, db)
        
        # 세션 소유권 확인
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
        
        from models import ChatMessage
        from sqlalchemy import desc
        raw = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at).limit(50).all()
        messages = [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in raw
        ]
        return {"messages": messages, "success": True}
        
    except Exception as e:
        return {"success": False, "error": str(e), "messages": []}

@router.delete("/message/{message_id}")
async def delete_chat_message(
    message_id: int,
    user_id: int = Query(..., description="사용자 ID"),
    db: Session = Depends(get_db)
):
    """개별 채팅 메시지 삭제"""
    try:
        from models import ChatMessage, ChatSession

        msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if not msg:
            raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")

        session = db.query(ChatSession).filter(
            ChatSession.id == msg.session_id,
            ChatSession.user_id == user_id
        ).first()
        if not session:
            raise HTTPException(status_code=403, detail="삭제 권한이 없습니다")

        db.delete(msg)
        db.commit()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"메시지 삭제 오류: {str(e)}")


@router.delete("/session/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    채팅 세션 삭제
    
    - **session_id**: 삭제할 세션 ID
    """
    try:
        from models import ChatSession
        
        # 세션 소유권 확인 후 삭제
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
        
        db.delete(session)
        db.commit()
        
        return {"message": "세션이 삭제되었습니다"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"세션 삭제 오류: {str(e)}")

@router.get("/debug/{user_id}")
async def debug_chatbot(user_id: int, db: Session = Depends(get_db)):
    """챗봇 디버그 - 단계별 확인"""
    debug_info = {}
    
    try:
        # 1단계: 사용자 확인
        debug_info["step1_user"] = "시작"
        current_user = get_current_user(user_id, db)
        debug_info["step1_user"] = f"성공 - {getattr(current_user, 'username', 'guest')}"
        
        # 2단계: chatbot_service import 확인
        debug_info["step2_service"] = "시작"
        from chatbot_service import chatbot_service
        debug_info["step2_service"] = "성공"
        
        # 3단계: 간단한 컨텍스트 생성 확인
        debug_info["step3_context"] = "시작"
        from chatbot_service import build_user_context
        user_context = build_user_context(user_id, db)
        debug_info["step3_context"] = f"성공 - {len(user_context)}자"
        
        # 4단계: OpenAI 클라이언트 확인
        debug_info["step4_openai"] = "시작"
        import openai
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        client = openai.OpenAI(api_key=api_key)
        debug_info["step4_openai"] = "성공"
        
        return {"status": "success", "debug_info": debug_info}
        
    except Exception as e:
        debug_info["error"] = str(e)
        debug_info["error_type"] = type(e).__name__
        
        import traceback
        debug_info["traceback"] = traceback.format_exc()
        
        return {"status": "error", "debug_info": debug_info}

# ═══ 헬스체크 ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def chatbot_health():
    """챗봇 서비스 상태 확인"""
    try:
        print("[CHATBOT HEALTH] 상태 확인 시작")
        
        # 1. 환경변수 확인
        import os
        openai_key = os.getenv("OPENAI_API_KEY")
        has_openai_key = bool(openai_key and openai_key != "pp_env")
        print(f"[CHATBOT HEALTH] OpenAI 키: {'OK' if has_openai_key else 'FAIL'}")
        
        # 2. 데이터베이스 연결 확인
        from database import SessionLocal
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        print("[CHATBOT HEALTH] DB 연결: OK")
        
        # 3. OpenAI 클라이언트 확인
        if has_openai_key:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            print("[CHATBOT HEALTH] OpenAI 클라이언트: OK")
        
        return {
            "status": "healthy",
            "service": "investment_chatbot",
            "openai_configured": has_openai_key,
            "database_connected": True,
            "timestamp": str(datetime.utcnow())
        }
    except Exception as e:
        print(f"[CHATBOT HEALTH ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            "status": "error",
            "service": "investment_chatbot", 
            "error": str(e),
            "timestamp": str(datetime.utcnow())
        }