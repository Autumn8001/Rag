from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
class Settings(BaseSettings):
    OPENAI_API_KEY: str
    BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8"
    )

settings = Settings()