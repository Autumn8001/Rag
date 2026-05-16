"""
对话与历史记录 API 路由

提供以下接口：
- GET  /api/v1/health             服务健康检查
- POST /api/v1/chat               流式 RAG 问答
- GET  /api/v1/sessions           获取历史会话列表
- GET  /api/v1/history/{id}       获取指定会话的完整对话记录
- DELETE /api/v1/history/{id}     删除指定会话记录
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.database import get_db
from core.crud import create_chat_record
from core.models import ChatHistory
from core.rag_engine import stream_rag_answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Chat"])


@router.get("/health", summary="Service health check")
async def health_check():
    return {"status": "ok", "message": "RAG engine is running."}


@router.post("/chat", summary="Streaming RAG Q&A")
async def chat_endpoint(
    request: dict,
    db: Session = Depends(get_db),
):
    """
    接收用户问题，通过 RAG 流水线生成答案并以 SSE 流式返回。
    对话结束后将完整问答记录持久化到数据库。
    """
    user_question = request.get("question")
    history = request.get("history")
    session_id = request.get("session_id", str(uuid.uuid4()))

    async def stream_generator():
        full_response = ""
        async for chunk in stream_rag_answer(user_question, history):
            full_response += chunk
            yield chunk

        try:
            create_chat_record(
                db=db,
                session_id=session_id,
                user_query=user_question,
                ai_response=full_response,
            )
        except Exception as e:
            logger.error("Failed to save chat record (session=%s): %s", session_id, e)

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.get("/sessions", summary="List recent chat sessions")
async def get_chat_sessions(db: Session = Depends(get_db)):
    try:
        all_records = (
            db.query(ChatHistory)
            .order_by(ChatHistory.created_at.desc())
            .limit(50)
        )
        sessions = []
        seen_ids = set()
        for record in all_records:
            if record.session_id not in seen_ids:
                seen_ids.add(record.session_id)
                title = (
                    record.user_query[:20] + "..."
                    if len(record.user_query) > 20
                    else record.user_query
                )
                sessions.append(
                    {
                        "session_id": record.session_id,
                        "title": title,
                        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
        return {"status": "success", "data": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{session_id}", summary="Get full conversation history")
async def get_session_history(session_id: str, db: Session = Depends(get_db)):
    try:
        records = (
            db.query(ChatHistory)
            .filter(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.asc())
            .all()
        )
        history_list = []
        for record in records:
            history_list.append({"role": "user", "content": record.user_query})
            history_list.append({"role": "assistant", "content": record.ai_response})
        return {"status": "success", "data": history_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{session_id}", summary="Delete a chat session")
async def delete_session_history(session_id: str, db: Session = Depends(get_db)):
    try:
        query = db.query(ChatHistory).filter(ChatHistory.session_id == session_id)
        if query.count() == 0:
            raise HTTPException(status_code=404, detail="Session not found.")
        query.delete(synchronize_session=False)
        db.commit()
        return {"status": "success", "message": f"Session {session_id} deleted."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
