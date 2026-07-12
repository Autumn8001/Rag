"""
面向 Agent / MCP Server 的工具化接口路由
提供以下接口：
- POST /api/v1/tools/search_documents     检索文档切片
- POST /api/v1/tools/get_document_detail  获取文档详情与权限校验
- POST /api/v1/tools/answer_with_citations 非流式带引用问答
- GET  /api/v1/tools/list_documents       获取租户下文档列表
- POST /api/v1/tools/evaluate_answer      大模型评估回答质量
"""

import json
import re
import logging
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_

from core.database import get_db
from core.crud import create_chat_record, get_chat_history
from core.models import User, DocumentRecord, ChatHistory
from core.auth import get_current_user
from core.rag_engine import (
    rag_engine,
    NO_MATCH_MESSAGE,
    MISSING_KNOWLEDGE_MESSAGE,
    PROMPT_BLOCK_MESSAGE,
)
from core.llm_factory import flash_llm, standard_llm, embeddings_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["RAG Tools"])


# ==========================================
# 🧱 Pydantic 请求/响应模型
# ==========================================

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索词")
    top_k: int = Field(default=5, ge=1, le=20, description="召回切片数量")


class ChunkMetadata(BaseModel):
    source: str
    rrf_score: float
    vector_rank: Optional[int] = None
    bm25_rank: Optional[int] = None
    h1: Optional[str] = ""
    h2: Optional[str] = ""
    h3: Optional[str] = ""


class ChunkResponse(BaseModel):
    chunk_id: str
    content: str
    metadata: ChunkMetadata


class SearchResponse(BaseModel):
    status: str
    query: str
    chunks: List[ChunkResponse]


class DocumentDetailRequest(BaseModel):
    doc_id: int = Field(..., description="文档在数据库中的自增 ID")


class DocumentDetailResponse(BaseModel):
    status: str
    doc_id: int
    filename: str
    file_hash: str
    created_at: str
    total_chunks: int
    has_access: bool
    tenant_id: str
    user_id: str


class Citation(BaseModel):
    content: str
    source: str
    rrf_score: float


class AnswerWithCitationsRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    session_id: Optional[str] = Field(default=None, description="会话 ID，用于加载上下文历史")


class AnswerWithCitationsResponse(BaseModel):
    status: str
    session_id: str
    answer: str
    citations: List[Citation]


class DocumentItem(BaseModel):
    doc_id: int
    filename: str
    file_hash: str
    created_at: str


class DocumentListResponse(BaseModel):
    status: str
    total: int
    documents: List[DocumentItem]


class EvaluateAnswerRequest(BaseModel):
    question: str = Field(..., min_length=1, description="原始提问")
    answer: str = Field(..., min_length=1, description="系统生成的回答")
    contexts: List[str] = Field(..., description="用于回答的参考上下文片段列表")


class EvaluateAnswerResponse(BaseModel):
    faithfulness_score: float
    answer_relevance_score: float
    is_refusal: bool
    reason: str


# ==========================================
# 🛰️ 接口路由实现
# ==========================================

@router.post(
    "/search_documents",
    response_model=SearchResponse,
    summary="Search relevant document chunks (Tenant Isolated)"
)
async def search_documents_endpoint(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
):
    """
    根据 query 检索多租户隔离的文档切片，支持向量 + 关键词混合检索与重排。
    此接口仅能检索当前用户所属租户的数据，防御横向越权。
    """
    tenant_id = current_user.tenant_id
    query_text = request.query.strip()
    top_k = request.top_k

    logger.info("Tool search query for tenant %s: %s (top_k=%s)", tenant_id, query_text, top_k)

    # 1. 拦截安全注入
    if rag_engine._is_prompt_injection(query_text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=PROMPT_BLOCK_MESSAGE
        )

    # 2. 获取混合检索器
    vectorstore = rag_engine._get_vectorstore()
    if not vectorstore:
        return SearchResponse(status="success", query=query_text, chunks=[])

    # 3. 构造或获取检索链
    tenant_retriever = rag_engine._get_tenant_retriever(tenant_id)
    if not tenant_retriever:
        return SearchResponse(status="success", query=query_text, chunks=[])

    # 4. 执行检索（重排并过滤前 top_k 个）
    retrieved_docs = await tenant_retriever.ainvoke(query_text)
    
    chunks_payload = []
    # 如果 vectorstore 存在，提取切片的具体 ID
    # Chroma 检索命中后的 ids 匹配比较复杂，为保证稳定，使用内容哈希作为 chunk_id
    for doc in retrieved_docs[:top_k]:
        content = doc.page_content
        source = doc.metadata.get("source", "未知来源")
        chunk_id = doc.metadata.get("id") or hashlib_id(content, source, tenant_id)
        
        meta = ChunkMetadata(
            source=source,
            rrf_score=doc.metadata.get("rrf_score", 0.0),
            vector_rank=doc.metadata.get("vector_rank"),
            bm25_rank=doc.metadata.get("bm25_rank"),
            h1=doc.metadata.get("H1", ""),
            h2=doc.metadata.get("H2", ""),
            h3=doc.metadata.get("H3", "")
        )
        chunks_payload.append(
            ChunkResponse(chunk_id=chunk_id, content=content, metadata=meta)
        )

    return SearchResponse(status="success", query=query_text, chunks=chunks_payload)


@router.post(
    "/get_document_detail",
    response_model=DocumentDetailResponse,
    summary="Get document details & Check permission"
)
async def get_document_detail_endpoint(
    request: DocumentDetailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取指定 ID 的已上传文档详情。
    严格以后端解析的 JWT tenant_id 与 DocumentRecord.tenant_id 进行比对校验，若不符则返回 403 越权。
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.username
    doc_id = request.doc_id

    # 1. 查询数据库记录
    record = db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档未找到。"
        )

    # 2. 🛡️ 横向越权强安全校验
    if record.tenant_id != tenant_id:
        logger.warning(
            "Unauthorized access attempt! User %s (tenant %s) tried to access doc %s (tenant %s)",
            user_id, tenant_id, doc_id, record.tenant_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，禁止跨租户访问他人文档。"
        )

    # 3. 统计在向量库中的分片总数
    total_chunks = 0
    vectorstore = rag_engine._get_vectorstore()
    if vectorstore:
        where_filter = {
            "$and": [
                {"tenant_id": tenant_id},
                {"source": record.filename}
            ]
        }
        db_data = vectorstore.get(where=where_filter, include=[])
        if db_data and db_data.get("ids"):
            total_chunks = len(db_data["ids"])

    return DocumentDetailResponse(
        status="success",
        doc_id=record.id,
        filename=record.filename,
        file_hash=record.file_hash,
        created_at=record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        total_chunks=total_chunks,
        has_access=True,
        tenant_id=record.tenant_id,
        user_id=record.user_id
    )


@router.post(
    "/answer_with_citations",
    response_model=AnswerWithCitationsResponse,
    summary="Non-streaming RAG question answering with sources"
)
async def answer_with_citations_endpoint(
    request: AnswerWithCitationsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    面向 Agent/MCP 的非流式 RAG 问答接口。
    输入问题与可选 session_id，返回带引用片段（citations）与评分的完整答案。
    自动拉取后端历史记录，确保租户间逻辑隔离与防范越权，避免大模型幻觉。
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.username
    question = request.question.strip()
    session_id = request.session_id or str(uuid.uuid4())

    logger.info("Tool chat with citations (tenant_id=%s, session=%s): %s", tenant_id, session_id, question)

    # 1. 提示词注入判定
    if rag_engine._is_prompt_injection(question):
        return AnswerWithCitationsResponse(
            status="blocked",
            session_id=session_id,
            answer=PROMPT_BLOCK_MESSAGE,
            citations=[]
        )

    # 2. 闲聊判定与快速响应
    if rag_engine._is_small_talk(question):
        history_records = get_chat_history(
            db, session_id=session_id, tenant_id=tenant_id, user_id=user_id, limit=5
        )
        history = []
        for r in history_records:
            history.append({"role": "user", "content": r.user_query})
            history.append({"role": "assistant", "content": r.ai_response})

        persona_response = ""
        async for chunk in rag_engine._stream_persona_response(question, history):
            persona_response += chunk
            
        create_chat_record(
            db=db,
            session_id=session_id,
            user_query=question,
            ai_response=persona_response,
            tenant_id=tenant_id,
            user_id=user_id
        )
        return AnswerWithCitationsResponse(
            status="success",
            session_id=session_id,
            answer=persona_response,
            citations=[]
        )

    # 3. 加载历史会话记忆
    history_records = get_chat_history(
        db, session_id=session_id, tenant_id=tenant_id, user_id=user_id, limit=5
    )
    history = []
    for r in history_records:
        history.append({"role": "user", "content": r.user_query})
        history.append({"role": "assistant", "content": r.ai_response})

    # 4. 改写意图问题 (Query Rewrite)
    clean_query = await rag_engine.rewrite_query(question, history) if history else question

    # 5. 执行检索
    tenant_retriever = rag_engine._get_tenant_retriever(tenant_id)
    if not tenant_retriever:
        return AnswerWithCitationsResponse(
            status="success",
            session_id=session_id,
            answer=MISSING_KNOWLEDGE_MESSAGE,
            citations=[]
        )

    retrieved_docs = await tenant_retriever.ainvoke(clean_query)
    if not retrieved_docs:
        return AnswerWithCitationsResponse(
            status="success",
            session_id=session_id,
            answer=NO_MATCH_MESSAGE,
            citations=[]
        )

    # 6. Critic Agent 相关性与幻觉防护评估
    context_str = "\n\n".join(doc.page_content for doc in retrieved_docs)
    is_valid_context = await rag_engine.evaluate_context(question, context_str)
    if not is_valid_context:
        return AnswerWithCitationsResponse(
            status="success",
            session_id=session_id,
            answer=NO_MATCH_MESSAGE,
            citations=[]
        )

    # 7. LLM 生成非流式完整答案
    history_text = "\n".join(f"{msg['role']}: {msg['content']}" for msg in history)
    answer_prompt = ChatPromptTemplate.from_template(
        """你是一个专业的企业知识助手。
请结合提供的对话历史与参考资料，以自然、专业、通顺的语气回答用户的问题。

【回答要求】：
0. 默认必须使用简体中文回答；除非用户明确要求使用其他语言，否则不要输出英文回答。
1. 必须且只能基于提供的参考资料进行回答。回答结构应当【先进行简明扼要的总结，然后再分点展开详细说明】。
2. 表达必须自然、通顺、专业，像资深专家一样对信息进行提炼与归纳，绝对不允许机械地直接复制或照搬参考资料原文。
3. 结构清晰，合理使用标准的 Markdown 格式（如标题、加粗重点、无序或有序列表等）以提高可读性。
4. 如果参考资料中没有相关答案，或者提供的信息不足以回答该问题，请直接明确说明“在参考资料中未找到相关信息”，绝对不要捏造或凭空想象。

对话历史：
{history}

参考资料：
{context}

用户问题：
{input}
"""
    )
    chain = answer_prompt | standard_llm | StrOutputParser()
    final_answer = await chain.ainvoke(
        {"history": history_text, "context": context_str, "input": clean_query}
    )
    final_answer = final_answer.strip()

    # 8. 过滤生成 Citations 信息返回
    citations = []
    for doc in retrieved_docs:
        citations.append(
            Citation(
                content=doc.page_content,
                source=doc.metadata.get("source", "未知来源"),
                rrf_score=doc.metadata.get("rrf_score", 0.0)
            )
        )

    # 9. 写入会话记忆库
    create_chat_record(
        db=db,
        session_id=session_id,
        user_query=question,
        ai_response=final_answer,
        tenant_id=tenant_id,
        user_id=user_id
    )

    return AnswerWithCitationsResponse(
        status="success",
        session_id=session_id,
        answer=final_answer,
        citations=citations
    )


@router.get(
    "/list_documents",
    response_model=DocumentListResponse,
    summary="List tenant accessible documents"
)
async def list_documents_endpoint(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页限制数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前租户下已入库的全部文档记录。
    提供给 MCP 客户端拉取文档列表以建立全局上下文理解。
    """
    tenant_id = current_user.tenant_id
    offset = (page - 1) * page_size

    total = db.query(DocumentRecord).filter(DocumentRecord.tenant_id == tenant_id).count()
    records = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.tenant_id == tenant_id)
        .order_by(DocumentRecord.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    documents = [
        DocumentItem(
            doc_id=r.id,
            filename=r.filename,
            file_hash=r.file_hash,
            created_at=r.created_at.strftime("%Y-%m-%d %H:%M:%S")
        )
        for r in records
    ]

    return DocumentListResponse(status="success", total=total, documents=documents)


@router.post(
    "/evaluate_answer",
    response_model=EvaluateAnswerResponse,
    summary="Evaluate RAG answer quality using LLM-as-a-judge"
)
async def evaluate_answer_endpoint(
    request: EvaluateAnswerRequest,
    current_user: User = Depends(get_current_user), # 工具鉴权，防止匿名恶意调用算力接口
):
    """
    使用大模型裁判（LLM-as-a-judge）对生成的回答质量进行自动化打分评估。
    返回 Faithfulness（防幻觉得分）、Answer Relevance（问题相关性）以及是否安全拒答（is_refusal）判断。
    """
    question = request.question.strip()
    answer = request.answer.strip()
    contexts_str = "\n\n".join(c.strip() for c in request.contexts)

    # 1. 构造评测判决 Chain
    eval_prompt = ChatPromptTemplate.from_template(
        """你是企业安全级 RAG 系统的黄金裁判。请客观、严格地对以下问题、回答和提供的参考资料进行打分。

问题: {question}
回答: {answer}
参考资料:
{contexts}

请严格按如下 JSON 结构返回打分，不要输出任何额外的废话、拼音或 Markdown 代码框：
{{
  "faithfulness_score": 0.0到1.0之间的浮点数 (回答中每一个事实断言在参考资料中是否都有依据？如果没有依据，说明是幻觉，给予低分；如完全没胡编或安全拒答了，给 1.0),
  "answer_relevance_score": 0.0到1.0之间的浮点数 (回答是否完全、正面、准确回答了问题本身？),
  "is_refusal": true/false (回答是否表达了“无法回答”、“未找到相关信息”等表示无答案的安全拒答？如果是输出 true，否则输出 false),
  "reason": "字数在80字以内，对这三项得分的具体中文说明与剖析"
}}
"""
    )
    
    chain = eval_prompt | flash_llm | StrOutputParser()
    try:
        raw_result = await chain.ainvoke(
            {"question": question, "answer": answer, "contexts": contexts_str}
        )
        
        # 2. 结构化 JSON 正则提取与防御解析
        cleaned_json = raw_result.strip()
        # 剥离可能存在的 ```json 框
        if "```" in cleaned_json:
            json_matches = re.findall(r"```json\s*([\s\S]*?)\s*```", cleaned_json)
            if json_matches:
                cleaned_json = json_matches[0].strip()
            else:
                cleaned_json = cleaned_json.replace("```", "").strip()

        data = json.loads(cleaned_json)
        
        return EvaluateAnswerResponse(
            faithfulness_score=float(data.get("faithfulness_score", 0.0)),
            answer_relevance_score=float(data.get("answer_relevance_score", 0.0)),
            is_refusal=bool(data.get("is_refusal", False)),
            reason=str(data.get("reason", "评估完毕。"))
        )
    except Exception as e:
        logger.error("LLM evaluation failed: %s. Raw output was: %s", e, raw_result if 'raw_result' in locals() else "")
        # 高可用降级返回
        is_refusal = any(kw in answer for kw in ["未找到", "没有相关", "无法回答", "安全拒答"])
        return EvaluateAnswerResponse(
            faithfulness_score=1.0 if is_refusal else 0.5,
            answer_relevance_score=0.5,
            is_refusal=is_refusal,
            reason=f"LLM 裁判执行异常，已自动切换为正则匹配降级打分。(Error: {str(e)})"
        )


# ==========================================
# 🔧 内部工具函数
# ==========================================

def hashlib_id(content: str, source: str, tenant_id: str) -> str:
    import hashlib
    return hashlib.md5((content + source + tenant_id).encode("utf-8")).hexdigest()
