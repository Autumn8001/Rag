import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 引入我们刚才画好的设计图纸
from core.models import Base
from core.config import settings

# ==========================================
# 1. 确定数据库的物理存放位置 (水库)
# ==========================================
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# ==========================================
# 2. 创建数据库引擎 (超级大水泵)
# ==========================================
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
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
    print("[Database] 正在检查并初始化关系型数据库表结构...")
    Base.metadata.create_all(bind=engine)

    # 自动注入测试用的 API Key 映射数据
    db = SessionLocal()
    try:
        from core.models import APIKeyMap
        if db.query(APIKeyMap).count() == 0:
            print("[Database] 检测到 API Key 映射表为空，正在注入演示数据...")
            demo_keys = [
                APIKeyMap(api_key="key_company_a", tenant_id="tenant_company_A", user_id="user_A"),
                APIKeyMap(api_key="key_company_b", tenant_id="tenant_company_B", user_id="user_B"),
                APIKeyMap(api_key="key_default", tenant_id="default_tenant", user_id="default_user")
            ]
            db.bulk_save_objects(demo_keys)
            db.commit()
            print("[Database] 演示数据注入成功！")
    except Exception as e:
        db.rollback()
        print(f"[Database] 注入演示数据失败: {e}")
    finally:
        db.close()

    print("[Database] 关系型数据库准备就绪！")
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