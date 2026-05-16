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

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from markitdown import MarkItDown
from sqlalchemy.orm import Session

from core.database import get_db
from core.crud import get_document_by_hash, create_document_record
from core.models import DocumentRecord, ChatHistory
from core.rag_engine import ingest_knowledge, clear_all_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"])
md_converter = MarkItDown()

os.makedirs("data/uploads", exist_ok=True)


@router.post("/upload", summary="Upload and index a document")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    上传文档流程：
    1. 计算文件 MD5 指纹，查重后跳过已入库文件
    2. 使用 MarkItDown 将文件转换为 Markdown 格式
    3. 调用 RAGEngine 切分入库，更新 BM25 检索器
    4. 在 SQLite 中记录文件元数据
    """
    try:
        content = await file.read()
        file_hash = hashlib.md5(content).hexdigest()

        # 查重：已存在则跳过，节省 Embedding 调用成本
        existing = get_document_by_hash(db, file_hash)
        if existing:
            return {
                "status": "skipped",
                "message": f"File '{file.filename}' already exists in the knowledge base.",
            }

        await file.seek(0)
        file_path = f"data/uploads/{file.filename}"
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        md_result = md_converter.convert(file_path)
        md_text = md_result.text_content

        success = ingest_knowledge(md_text, file.filename)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to index document.")

        create_document_record(db=db, filename=file.filename, file_hash=file_hash)
        return {
            "status": "success",
            "message": f"File '{file.filename}' has been indexed successfully.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload failed for file '%s': %s", file.filename, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear", summary="Clear the entire knowledge base")
async def clear_knowledge_base(db: Session = Depends(get_db)):
    """清空向量库、BM25 索引，以及数据库中的文档记录和对话历史。"""
    try:
        db.query(DocumentRecord).delete()
        db.query(ChatHistory).delete()
        success = clear_all_data()
        if not success:
            raise ValueError("Vector store cleanup failed.")
        db.commit()
        return {"status": "success", "message": "Knowledge base cleared successfully."}
    except Exception as e:
        db.rollback()
        logger.error("Failed to clear knowledge base: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", summary="List indexed documents with pagination")
async def list_knowledge_base(
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    page_size: int = Query(10, ge=1, le=100, description="Number of records per page"),
    db: Session = Depends(get_db),
):
    try:
        total_items = db.query(DocumentRecord).count()
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        offset = (page - 1) * page_size

        records = (
            db.query(DocumentRecord)
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
        logger.error("Failed to retrieve document list: %s", e)
        raise HTTPException(status_code=500, detail=str(e))