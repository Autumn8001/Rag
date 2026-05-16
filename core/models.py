# 文件位置：core/models.py

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

# ==========================================
# 🧱 准备地基
# ==========================================
# 这是一切表格的老祖宗。等下我们定义的所有类，都必须继承这个 Base。
# 以后 SQLAlchemy 就是通过这个 Base，去自动帮我们生成真实数据库表结构的。
Base = declarative_base()


# ==========================================
# 📄 第一张表：文档上传记录表
# ==========================================
class DocumentRecord(Base):
    # __tablename__ 是告诉 SQLAlchemy，真正在 SQLite 数据库里的那张表叫什么名字
    __tablename__ = "document_records"

    # Column 就是告诉数据库：给我建一列！
    # Integer(整数), primary_key=True(主键，绝不重复), index=True(建索引，查询快)
    id = Column(Integer, primary_key=True, index=True)

    # String 是短字符串。存我们上传的文件名，比如 "入职手册.pdf"
    filename = Column(String, index=True)

    # 这里极其关键！这是我们上周做的 MD5 指纹防重复。unique=True 保证绝不重复！
    file_hash = Column(String, unique=True, index=True)

    # DateTime 存时间。注意 default=datetime.now，这表示只要你存入数据，它会自动帮你打上时间戳！
    created_at = Column(DateTime, default=datetime.now)


# ==========================================
# 💬 第二张表：多轮对话记忆表（海马体）
# ==========================================
class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id = Column(Integer, primary_key=True, index=True)

    # 预留字段：现在我们是单机版，以后你要是发到 GitHub 上别人用，
    # 肯定要区分是张三问的还是李四问的，这个 session_id 就是用来区分不同用户的聊天窗口的。
    session_id = Column(String, index=True, default="default_session")

    # 为什么这里不用 String 而是用 Text？
    # 因为 String 一般有长度限制（比如 255 个字符），而 Text 可以存几万字的无限长文本！
    user_query = Column(Text)  # 用户的提问
    ai_response = Column(Text)  # AI 的长篇大论回答

    created_at = Column(DateTime, default=datetime.now)