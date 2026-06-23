# 文件位置：core/crud.py

from sqlalchemy.orm import Session
from core.models import DocumentRecord, ChatHistory


# ==========================================
# 📄 模块一：文档记录的搬运工
# ==========================================

def get_document_by_hash(db: Session, file_hash: str, tenant_id: str):
    """
    【查】：在存入前，先按 MD5 指纹和租户ID查一下数据库里有没有。
    这就叫“防重复过滤”，比你去 Chroma 里面查要快几万倍！
    """
    # 过滤当前租户的数据，防止跨租户查重失效
    return db.query(DocumentRecord).filter(
        DocumentRecord.file_hash == file_hash,
        DocumentRecord.tenant_id == tenant_id
    ).first()


def create_document_record(db: Session, filename: str, file_hash: str, tenant_id: str, user_id: str):
    """
    【增】：存入一条新的文档上传记录，绑定租户与用户
    """
    db_document = DocumentRecord(
        filename=filename,
        file_hash=file_hash,
        tenant_id=tenant_id,
        user_id=user_id
    )

    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    return db_document


# ==========================================
# 💬 模块二：聊天记忆（海马体）的搬运工
# ==========================================

def create_chat_record(db: Session, session_id: str, user_query: str, ai_response: str, tenant_id: str, user_id: str):
    """
    【增】：用户和 AI 聊完一句，我们就把它永远刻在硬盘上，同时关联租户与用户
    """
    db_chat = ChatHistory(
        session_id=session_id,
        user_query=user_query,
        ai_response=ai_response,
        tenant_id=tenant_id,
        user_id=user_id
    )
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return db_chat


def get_chat_history(db: Session, session_id: str, tenant_id: str, user_id: str, limit: int = 5):
    """
    【查】：获取滑动窗口记忆！且限制仅能获取当前租户及对应用户的历史记录（用户级强隔离）。
    """
    records = db.query(ChatHistory).filter(
        ChatHistory.session_id == session_id,
        ChatHistory.tenant_id == tenant_id,
        ChatHistory.user_id == user_id
    ).order_by(
        ChatHistory.created_at.desc()
    ).limit(limit).all()

    # 因为是倒序拿的（最新的在前面），我们需要把它反转一下，让最老的在前面，符合人类阅读习惯
    return records[::-1]

def delete_document_by_hash(db: Session, file_hash: str, tenant_id: str):
    """
    【删】：只删除当前租户名下的文档上传记录
    """
    record_to_delete = get_document_by_hash(db, file_hash, tenant_id)
    if record_to_delete is not None:
        db.delete(record_to_delete)
        db.commit()
        print(f"成功删除记录：{file_hash} (租户: {tenant_id})")
        return True
    print(f"没找到要删除的记录: {file_hash} (租户: {tenant_id})")
    return False