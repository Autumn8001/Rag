from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    FLASH_MODEL: str = "glm-4-flash"
    STANDARD_MODEL: str = "glm-4"
    PLUS_MODEL: str = "glm-4-plus"
    EMBEDDING_MODEL: str = "embedding-3"
    DATABASE_URL: str = "sqlite:///./data/enterprise_rag.db"
    LANGCHAIN_TRACING_V2: str = "false"
    LANGSMITH_TRACING: str | None = None
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_ENDPOINT: str | None = None
    LANGCHAIN_API_KEY: str | None = None
    LANGSMITH_API_KEY: str | None = None
    LANGCHAIN_PROJECT: str = "enterprise-rag"
    LANGSMITH_PROJECT: str | None = None

    # JWT 统一认证配置
    JWT_SECRET_KEY: str = "enterprise-rag-super-secret-key-change-it-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    VISITOR_SESSION_TTL_MINUTES: int = 120
    TEMP_VISITOR_CLEANUP_INTERVAL_SECONDS: int = 300
    ENABLE_TEMP_VISITOR_CLEANUP: bool = True
    SEED_STATIC_VISITOR_DEMO: bool = False

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()


def _sync_langsmith_env() -> None:
    """将 pydantic 读取到的 .env 配置同步给 LangChain/LangSmith SDK。"""
    tracing_enabled = settings.LANGCHAIN_TRACING_V2.lower() == "true"
    langsmith_tracing = settings.LANGSMITH_TRACING

    os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGCHAIN_TRACING_V2
    if langsmith_tracing:
        os.environ["LANGSMITH_TRACING"] = langsmith_tracing
    elif tracing_enabled:
        os.environ.setdefault("LANGSMITH_TRACING", "true")

    endpoint = settings.LANGSMITH_ENDPOINT or settings.LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    os.environ.setdefault("LANGSMITH_ENDPOINT", endpoint)

    api_key = settings.LANGSMITH_API_KEY or settings.LANGCHAIN_API_KEY
    if api_key:
        os.environ["LANGCHAIN_API_KEY"] = api_key
        os.environ.setdefault("LANGSMITH_API_KEY", api_key)

    project = settings.LANGSMITH_PROJECT or settings.LANGCHAIN_PROJECT
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ.setdefault("LANGSMITH_PROJECT", project)


_sync_langsmith_env()

# 控制台链路追踪友情提示
langsmith_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
langsmith_enabled = (
    os.getenv("LANGSMITH_TRACING") == "true"
    or os.getenv("LANGCHAIN_TRACING_V2") == "true"
)
if langsmith_enabled and langsmith_key and langsmith_key != "your_langsmith_api_key_here":
    print("\n[LangSmith] 检测到链路追踪环境变量已配置，系统正在将 RAG 全链路监控上传至 LangSmith 平台。")
else:
    print("\n[LangSmith] 提示：如需开启 RAG 可观测性链路追踪，请在 .env 中配置 LANGCHAIN_API_KEY。")
