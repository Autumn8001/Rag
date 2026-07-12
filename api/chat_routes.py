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
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session

from core.database import engine, get_db
from core.crud import create_chat_record, get_chat_history
from core.models import ChatHistory, User
from core.rag_engine import METADATA_START_MARKER, rag_engine, stream_rag_answer
from core.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Chat"])


def strip_response_metadata(response_text: str) -> str:
    import re
    cleaned = re.sub(r"__STAGE__:[A-Z_]+\n?", "", response_text)
    if METADATA_START_MARKER not in cleaned:
        return cleaned.strip()
    return cleaned.split(METADATA_START_MARKER, 1)[0].rstrip()


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户当前问题")
    session_id: str | None = Field(default=None, description="当前会话 ID")
    history: list[dict[str, str]] | None = Field(
        default=None, description="前端可选传入的历史消息"
    )
    search_mode: str = Field(default="RAG_ONLY", description="检索模式 RAG_ONLY / WIKI_ONLY")


@router.get("/health", summary="Service health check")
async def health_check():
    components = {
        "api": {"name": "API", "status": "ok", "detail": "FastAPI ready"},
        "database": {
            "name": {
                "postgresql": "PostgreSQL",
                "sqlite": "SQLite",
            }.get(engine.dialect.name, engine.dialect.name),
            "status": "unknown",
            "detail": engine.dialect.name,
        },
        "vectorstore": {"name": "Chroma", "status": "unknown", "detail": "vector store"},
    }

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        components["database"]["status"] = "ok"
        components["database"]["detail"] = "reachable"
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        components["database"]["status"] = "error"
        components["database"]["detail"] = str(exc)

    try:
        vectorstore = rag_engine._get_vectorstore()
        if vectorstore is None:
            raise RuntimeError("vector store unavailable")
        components["vectorstore"]["status"] = "ok"
        components["vectorstore"]["detail"] = "reachable"
    except Exception as exc:
        logger.warning("Vector store health check failed: %s", exc)
        components["vectorstore"]["status"] = "error"
        components["vectorstore"]["detail"] = str(exc)

    overall_status = (
        "ok"
        if all(component["status"] == "ok" for component in components.values())
        else "degraded"
    )
    return {
        "status": overall_status,
        "message": "RAG engine health checked.",
        "components": components,
    }


@router.post("/chat", summary="Streaming RAG Q&A")
async def chat_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    接收用户问题，通过 RAG 流水线生成答案并以 SSE 流式返回。
    对话结束后将完整问答记录持久化到数据库。
    """
    user_question = request.question.strip()
    session_id = request.session_id or str(uuid.uuid4())
    tenant_id = current_user.tenant_id
    user_id = current_user.username

    # 🛡️ 安全防御：屏蔽前端传入的 history 伪造漏洞，聊天历史一律通过后端数据库加载
    records = get_chat_history(
        db, session_id=session_id, tenant_id=tenant_id, user_id=user_id, limit=5
    )
    history = []
    for record in records:
        history.append({"role": "user", "content": record.user_query})
        history.append({"role": "assistant", "content": record.ai_response})

    async def stream_generator():
        full_response = ""
        try:
            async for chunk in stream_rag_answer(user_question, history, tenant_id=tenant_id, search_mode=request.search_mode):
                full_response += chunk
                yield chunk
        except Exception as e:
            logger.exception("Chat generation failed (session=%s): %s", session_id, e)
            yield "\n[Error] Failed to generate a response. Please try again later."
            return
        try:
            persisted_response = strip_response_metadata(full_response)
            if persisted_response:
                create_chat_record(
                    db=db,
                    session_id=session_id,
                    user_query=user_question,
                    ai_response=persisted_response,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
        except Exception as e:
            logger.error("Failed to save chat record (session=%s): %s", session_id, e)

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "X-Session-Id": session_id,
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", summary="List recent chat sessions")
async def get_chat_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的历史会话列表（加入 user_id 强隔离）。"""
    tenant_id = current_user.tenant_id
    user_id = current_user.username
    try:
        latest_records = (
            db.query(
                ChatHistory.session_id,
                func.max(ChatHistory.created_at).label("latest_at"),
            )
            .filter(and_(ChatHistory.tenant_id == tenant_id, ChatHistory.user_id == user_id))
            .group_by(ChatHistory.session_id)
            .subquery()
        )

        records = (
            db.query(ChatHistory)
            .join(
                latest_records,
                and_(
                    ChatHistory.session_id == latest_records.c.session_id,
                    ChatHistory.created_at == latest_records.c.latest_at,
                ),
            )
            .filter(and_(ChatHistory.tenant_id == tenant_id, ChatHistory.user_id == user_id))
            .order_by(ChatHistory.created_at.desc())
            .limit(50)
            .all()
        )
        sessions = []
        for record in records:
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
async def get_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定会话的完整对话记录（加入 user_id 和 tenant_id 双重校验防止越权）。"""
    tenant_id = current_user.tenant_id
    user_id = current_user.username
    try:
        records = (
            db.query(ChatHistory)
            .filter(
                and_(
                    ChatHistory.session_id == session_id,
                    ChatHistory.tenant_id == tenant_id,
                    ChatHistory.user_id == user_id
                )
            )
            .order_by(ChatHistory.created_at.asc())
            .all()
        )
        history_list = []
        for record in records:
            history_list.append({"role": "user", "content": record.user_query})
            history_list.append({"role": "assistant", "content": record.ai_response})
        return {"status": "success", "session_id": session_id, "data": history_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{session_id}", summary="Delete a chat session")
async def delete_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除指定会话记录（加入 user_id 强隔离）。"""
    tenant_id = current_user.tenant_id
    user_id = current_user.username
    try:
        query = db.query(ChatHistory).filter(
            and_(
                ChatHistory.session_id == session_id,
                ChatHistory.tenant_id == tenant_id,
                ChatHistory.user_id == user_id
            )
        )
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
