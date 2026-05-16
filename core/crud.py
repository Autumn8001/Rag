# 文件位置：core/crud.py

from sqlalchemy.orm import Session
from core.models import DocumentRecord, ChatHistory


# ==========================================
# 📄 模块一：文档记录的搬运工
# ==========================================

def get_document_by_hash(db: Session, file_hash: str):
    """
    【查】：在存入前，先按 MD5 指纹查一下数据库里有没有。
    这就叫“防重复过滤”，比你去 Chroma 里面查要快几万倍！
    """
    # 翻译成 SQL：SELECT * FROM document_records WHERE file_hash = 'xxx' LIMIT 1;
    return db.query(DocumentRecord).filter(DocumentRecord.file_hash == file_hash).first()


def create_document_record(db: Session, filename: str, file_hash: str):
    """
    【增】：存入一条新的文档上传记录
    """
    # 1. 组装对象（就像捏一个泥人）
    db_document = DocumentRecord(filename=filename, file_hash=file_hash)

    # 2. 放到传送带上
    db.add(db_document)

    # 3. 按下确认按钮，真正写入硬盘！
    db.commit()

    # 4. 刷新一下，把数据库自动生成的 ID 和时间拿回来
    db.refresh(db_document)

    return db_document


# ==========================================
# 💬 模块二：聊天记忆（海马体）的搬运工
# ==========================================

def create_chat_record(db: Session, session_id: str, user_query: str, ai_response: str):
    """
    【增】：用户和 AI 聊完一句，我们就把它永远刻在硬盘上
    """
    db_chat = ChatHistory(
        session_id=session_id,
        user_query=user_query,
        ai_response=ai_response
    )
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return db_chat


def get_chat_history(db: Session, session_id: str, limit: int = 5):
    """
    【查】：获取滑动窗口记忆！
    当用户再次提问时，我们从硬盘里捞出最近的几轮对话喂给大模型。
    """
    # 翻译成 SQL：SELECT * FROM chat_histories WHERE session_id = 'xxx' ORDER BY created_at DESC LIMIT 5;
    # 这一句极其经典！按时间倒序排，只拿最近的 limit 条！
    records = db.query(ChatHistory).filter(ChatHistory.session_id == session_id).order_by(
        ChatHistory.created_at.desc()).limit(limit).all()

    # 因为是倒序拿的（最新的在前面），我们需要把它反转一下，让最老的在前面，符合人类阅读习惯
    return records[::-1]

def delete_document_by_hash(db: Session, file_hash: str):
    record_to_delete = get_document_by_hash(db, file_hash)
    if record_to_delete is not None:
        db.delete(record_to_delete)
        db.commit()
        print(f"成功删除记录：{file_hash}")
        return True
    print(f"没找到要删除的记录:{file_hash}")
    return False