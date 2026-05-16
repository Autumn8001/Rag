"""
LLM 工厂模块

统一管理项目中所有 LLM 实例，采用三级模型分层策略：
- flash_llm:    轻量模型，用于路由判断、问题重写、上下文评估
- standard_llm: 中端模型，用于 RAG 检索结果的最终生成
- plus_llm:     旗舰模型，用于对话质量要求较高的闲聊场景
- embeddings_model: 向量化模型，用于文本 Embedding
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from core.config import settings

# 路由/分类/裁判：高速低成本
flash_llm = ChatOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.BASE_URL,
    model="glm-4-flash",
    temperature=0,
)

# RAG 主力生成：质量与成本平衡
standard_llm = ChatOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.BASE_URL,
    model="glm-4",
    temperature=0,
)

# 闲聊/高质量对话：旗舰模型
plus_llm = ChatOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.BASE_URL,
    model="glm-4-plus",
    temperature=0,
)

# 文本向量化
embeddings_model = OpenAIEmbeddings(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.BASE_URL,
    model="embedding-3",
)