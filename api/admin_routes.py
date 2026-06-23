"""
管理员 API 路由

提供知识库管理相关接口：
- POST   /api/v1/upload   上传文档并入库
- DELETE /api/v1/clear    清空知识库
- GET    /api/v1/list     分页查询已入库文档列表
"""

import os
import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from markitdown import MarkItDown
from sqlalchemy.orm import Session

from core.database import get_db
from core.crud import get_document_by_hash, create_document_record
from core.models import DocumentRecord, ChatHistory, User
from core.rag_engine import ingest_knowledge, clear_all_data
from core.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"])
md_converter = MarkItDown()

@router.post("/upload", summary="Upload and index a document")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    上传文档流程：
    1. 计算文件 MD5 指纹，结合租户ID进行查重后跳过已入库文件
    2. 使用 MarkItDown 将文件转换为 Markdown 格式
    3. 调用 RAGEngine 切分入库并带上 tenant_id，更新对应租户的 BM25 检索器
    4. 在 PostgreSQL 中记录文件元数据，绑定当前租户与用户
    """
    tenant_id = current_user.tenant_id
    user_id = current_user.username
    try:
        content = await file.read()
        file_hash = hashlib.md5(content).hexdigest()

        # 查重：同租户下存在则跳过，节省 Embedding 调用成本
        existing = get_document_by_hash(db, file_hash, tenant_id)
        if existing:
            return {
                "status": "skipped",
                "message": f"File '{file.filename}' already exists in the knowledge base.",
            }

        await file.seek(0)
        
        # 物理隔离存放上传文件 (防止路径穿越并采用 UUID 重命名落盘)
        upload_dir = f"data/uploads/{tenant_id}"
        os.makedirs(upload_dir, exist_ok=True)
        
        orig_filename = Path(file.filename).name
        file_ext = Path(file.filename).suffix
        safe_physical_name = f"{uuid.uuid4().hex}{file_ext}"
        file_path = os.path.join(upload_dir, safe_physical_name).replace("\\", "/")
        
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
 
        md_result = md_converter.convert(file_path)
        md_text = md_result.text_content
 
        success = ingest_knowledge(md_text, orig_filename, tenant_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to index document.")
 
        create_document_record(
            db=db,
            filename=orig_filename,
            file_hash=file_hash,
            tenant_id=tenant_id,
            user_id=user_id
        )
        return {
            "status": "success",
            "message": f"File '{orig_filename}' has been indexed successfully.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload failed for file '%s': %s", file.filename, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear", summary="Clear the entire knowledge base")
async def clear_knowledge_base(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清空当前租户的向量库、BM25 索引，以及数据库中的文档记录和对话历史。"""
    tenant_id = current_user.tenant_id
    try:
        db.query(DocumentRecord).filter(DocumentRecord.tenant_id == tenant_id).delete()
        db.query(ChatHistory).filter(ChatHistory.tenant_id == tenant_id).delete()
        success = clear_all_data(tenant_id)
        if not success:
            raise ValueError("Vector store cleanup failed.")
        db.commit()
        return {"status": "success", "message": "Knowledge base cleared successfully."}
    except Exception as e:
        db.rollback()
        logger.error("Failed to clear knowledge base for tenant %s: %s", tenant_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", summary="List indexed documents with pagination")
async def list_knowledge_base(
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    page_size: int = Query(10, ge=1, le=100, description="Number of records per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页查询属于当前租户的文档记录。"""
    tenant_id = current_user.tenant_id
    try:
        total_items = db.query(DocumentRecord).filter(DocumentRecord.tenant_id == tenant_id).count()
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        offset = (page - 1) * page_size

        records = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.tenant_id == tenant_id)
            .order_by(DocumentRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        data = [
            {
                "id": f"DOC_{record.id}",
                "source": record.filename,
                "fingerprint": record.file_hash[:8],
                "indexed_at": record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for record in records
        ]

        return {
            "status": "success",
            "total": total_items,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": data,
        }

    except Exception as e:
        logger.error("Failed to retrieve document list for tenant %s: %s", tenant_id, e)
        raise HTTPException(status_code=500, detail=str(e))