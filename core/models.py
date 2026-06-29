# 文件位置：core/models.py

from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, UniqueConstraint
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

    # 租户和用户标识，用于多租户权限隔离
    tenant_id = Column(String, index=True, nullable=False, server_default="default_tenant")
    user_id = Column(String, index=True, nullable=False, server_default="default_user")

    # String 是短字符串。存我们上传的文件名，比如 "入职手册.pdf"
    filename = Column(String, index=True)

    # 文件哈希，移除全局唯一约束，改为在租户级别唯一
    file_hash = Column(String, index=True)

    # DateTime 存时间。注意 default=datetime.now，这表示只要你存入数据，它会自动帮你打上时间戳！
    created_at = Column(DateTime, default=datetime.now)

    # 联合唯一约束：同一租户下文件哈希不能重复
    __table_args__ = (
        UniqueConstraint('tenant_id', 'file_hash', name='uq_tenant_file_hash'),
    )


# ==========================================
# 💬 第二张表：多轮对话记忆表（海马体）
# ==========================================
class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id = Column(Integer, primary_key=True, index=True)

    # 租户和用户标识，用于多租户权限隔离
    tenant_id = Column(String, index=True, nullable=False, server_default="default_tenant")
    user_id = Column(String, index=True, nullable=False, server_default="default_user")

    # 预留字段：现在我们是单机版，以后你要是发到 GitHub 上别人用，
    # 肯定要区分是张三问的还是李四问的，这个 session_id 就是用来区分不同用户的聊天窗口的。
    session_id = Column(String, index=True, default="default_session")

    # 为什么这里不用 String 而是用 Text？
    # 因为 String 一般有长度限制（比如 255 个字符），而 Text 可以存几万字的无限长文本！
    user_query = Column(Text)  # 用户的提问
    ai_response = Column(Text)  # AI 的长篇大论回答

    created_at = Column(DateTime, default=datetime.now)


# ==========================================
# 🔑 第三张表：API Key 与租户映射关系表
# ==========================================
class APIKeyMap(Base):
    __tablename__ = "api_key_maps"

    id = Column(Integer, primary_key=True, index=True)
    api_key = Column(String, unique=True, index=True, nullable=False)
    tenant_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


# ==========================================
# 👤 第四张表：用户注册/登录凭证与租户关系表 (统一鉴权核心)
# ==========================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)  # 登录用户名，唯一
    hashed_password = Column(String, nullable=False)                    # 强加密哈希密码
    tenant_id = Column(String, index=True, nullable=False)              # 所属隔离租户 ID
    created_at = Column(DateTime, default=datetime.now)
    is_temporary = Column(Boolean, nullable=False, default=False, server_default="false")
    expires_at = Column(DateTime, nullable=True, index=True)
    last_active_at = Column(DateTime, nullable=True)
