import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.models import User, WikiPage, WikiItem, DocumentRecord
from core.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wiki", tags=["Wiki"])

@router.get("/list", summary="获取当前租户的所有 Wiki 编译页面列表")
async def list_wikis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tenant_id = current_user.tenant_id
    logger.info("Listing wikis for tenant: %s", tenant_id)
    
    # 强制进行租户级别逻辑隔离，只允许查看属于当前租户的 Wiki 页面
    wikis = db.query(WikiPage).filter(WikiPage.tenant_id == tenant_id).order_by(WikiPage.created_at.desc()).all()
    
    return {
        "wikis": [
            {
                "id": wiki.id,
                "document_id": wiki.document_id,
                "title": wiki.title,
                "summary": wiki.summary,
                "created_at": wiki.created_at
            }
            for wiki in wikis
        ]
    }


@router.get("/detail", summary="根据文档ID获取单篇 Wiki 结构化详情")
async def get_wiki_page(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tenant_id = current_user.tenant_id
    logger.info("Fetching wiki detail for document ID: %s, tenant: %s", document_id, tenant_id)
    
    # 强制进行多租户鉴权，防范越权攻击 (IDOR)
    wiki_page = db.query(WikiPage).filter(
        WikiPage.document_id == document_id,
        WikiPage.tenant_id == tenant_id
    ).first()
    
    if not wiki_page:
        raise HTTPException(status_code=404, detail="该文档对应的 Wiki 页面未找到或已触发自动降级兜底。")
        
    # 获取此 Wiki 下的所有精细化词条（概念、合规条款和典型 FAQ）
    items = db.query(WikiItem).filter(WikiItem.wiki_page_id == wiki_page.id).all()
    
    concepts = []
    clauses = []
    faqs = []
    
    for item in items:
        entry = {
            "key": item.key,
            "value": item.value,
            "citation": item.citation
        }
        if item.category == "concept":
            concepts.append(entry)
        elif item.category == "clause":
            clauses.append(entry)
        elif item.category == "faq":
            faqs.append(entry)
            
    return {
        "wiki": {
            "id": wiki_page.id,
            "document_id": wiki_page.document_id,
            "title": wiki_page.title,
            "summary": wiki_page.summary,
            "markdown_content": wiki_page.markdown_content,
            "concepts": concepts,
            "clauses": clauses,
            "faqs": faqs,
            "created_at": wiki_page.created_at
        }
    }
