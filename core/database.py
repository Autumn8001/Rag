import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 引入我们刚才画好的设计图纸
from core.models import Base

# ==========================================
# 1. 确定数据库的物理存放位置 (水库)
# ==========================================
# 我们把数据库文件就存在本地的 data 目录下，名字叫 rag_data.db
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DB_DIR, exist_ok=True) # 如果没这个文件夹就自动建一个

SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(DB_DIR, 'rag_data.db')}"

# ==========================================
# 2. 创建数据库引擎 (超级大水泵)
# ==========================================
# engine 负责和底层 SQLite 文件进行极其底层的二进制通信
# 注意：check_same_thread=False 是 SQLite 专属的坑！
# 因为 FastAPI 是多线程并发的，不加这个参数，并发请求时 SQLite 会直接报错崩溃。
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
# ==========================================
# 3. 创建会话工厂 (水龙头制造机)
# ==========================================
# 以后代码里想要存取数据，都要找它拿一个 Session (水龙头)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# ==========================================
# 4. 一键建表魔法 (施工队开工)
# ==========================================
def init_db():
    """
    拿着 models.py 里的 Base 设计图，去水库里把真正的表格砌出来！
    如果表格已经存在了，它会自动跳过，极其智能。
    """
    print("🧱 [Database] 正在检查并初始化 SQLite 数据库表结构...")
    Base.metadata.create_all(bind=engine)
    print("✅ [Database] 关系型数据库准备就绪！")
# ==========================================
# 5. 依赖注入函数 (给大堂经理 FastAPI 用的)
# ==========================================
def get_db():
    """
    FastAPI 专用魔法：每次有 HTTP 请求进来，就拧开一个水龙头 (Session)。
    等请求处理完了，自动关上水龙头 (db.close())。防止连接泄漏！
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()