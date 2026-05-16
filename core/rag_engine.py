"""
RAG 引擎核心模块

封装完整的 RAG 检索生成流水线，包含：
- 语义路由（业务问题 vs. 日常闲聊）
- 混合检索（向量检索 + BM25 关键词检索 + Flashrank 重排）
- Critic Agent 前置评估（防止幻觉生成）
- 全链路异步化，支持高并发流式输出
"""

import os
import pickle
import hashlib
import logging
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import Chroma
from langchain_community.document_compressors import FlashrankRerank
from langchain_community.retrievers import BM25Retriever
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever

from core.llm_factory import flash_llm, standard_llm, plus_llm, embeddings_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
DB_DIR = BASE_DIR / "data" / "chroma_db"
BM25_FILE = BASE_DIR / "data" / "bm25.pkl"


class RAGEngine:
    """
    RAG 检索生成引擎（单例）

    负责管理向量数据库连接、BM25 检索器、Rerank 压缩器，
    以及完整的异步流式问答流水线。
    """

    def __init__(self):
        self.vectorstore = None
        self.bm25_retriever = None
        self.medium_retriever = None
        self.final_retriever = None
        self.compressor = None
        self._initialize_components()

    def _get_vectorstore(self):
        """获取或初始化向量数据库连接。"""
        if self.vectorstore is None:
            if os.path.exists(DB_DIR):
                self.vectorstore = Chroma(
                    persist_directory=str(DB_DIR),
                    embedding_function=embeddings_model,
                )
            else:
                logger.warning("Local Chroma database not found. Engine waiting for first document upload.")
        return self.vectorstore

    def _initialize_components(self):
        """初始化混合检索器和 Rerank 压缩器。"""
        vectorstore = self._get_vectorstore()

        # 向量检索器
        base_retriever = vectorstore.as_retriever(search_kwargs={"k": 5}) if vectorstore else None

        # BM25 关键词检索器（从磁盘持久化加载）
        try:
            if BM25_FILE.exists():
                with open(BM25_FILE, "rb") as f:
                    self.bm25_retriever = pickle.load(f)
        except Exception as e:
            logger.error("Failed to load BM25 retriever: %s", e)

        # 混合检索器（RRF 权重融合）
        if base_retriever and self.bm25_retriever:
            self.medium_retriever = EnsembleRetriever(
                retrievers=[base_retriever, self.bm25_retriever],
                weights=[0.5, 0.5],
            )
        elif base_retriever:
            self.medium_retriever = base_retriever

        # Flashrank Rerank 精排
        try:
            self.compressor = FlashrankRerank(top_n=5)
            if self.medium_retriever:
                self.final_retriever = ContextualCompressionRetriever(
                    base_compressor=self.compressor,
                    base_retriever=self.medium_retriever,
                )
        except Exception as e:
            logger.warning("Reranker initialization failed, falling back to ensemble retriever: %s", e)
            self.final_retriever = self.medium_retriever

    async def evaluate_context(self, question: str, context: str) -> bool:
        """
        Critic Agent：判断检索到的上下文是否与问题相关。

        倾向宽松判断——只要上下文与问题存在合理关联即通过，
        避免因过度严格导致正确信息被错误拒绝。
        """
        eval_prompt = ChatPromptTemplate.from_template(
            """You are a document relevance evaluator.
            Determine whether the [Reference] is relevant to the [Question] and can help answer it.

            Rules:
            1. Output YES if the reference directly contains the answer, or contains information that can reasonably lead to the answer.
            2. Output NO only when the reference is completely unrelated to the question.
            3. When uncertain, prefer YES over NO.
            4. Output only YES or NO, no other text.

            [Reference]:
            {context}

            [Question]:
            {question}
            """
        )
        chain = eval_prompt | flash_llm | StrOutputParser()
        result = await chain.ainvoke({"context": context, "question": question})
        return "YES" in result.upper()

    async def rewrite_query(self, user_question: str, history: list) -> str:
        """根据对话历史将问题改写为独立的完整问句。"""
        if not history:
            return user_question

        history_text = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in history]
        )
        rewrite_prompt = ChatPromptTemplate.from_template(
            """Rewrite the latest question as a standalone question based on the conversation history.
            Only output the rewritten question, nothing else.

            [History]:
            {history}

            [Latest Question]:
            {question}
            """
        )
        chain = rewrite_prompt | flash_llm | StrOutputParser()
        return await chain.ainvoke({"history": history_text, "question": user_question})

    async def classify_question(self, user_question: str) -> str:
        """
        语义路由：将问题分类为 A（业务检索）或 B（闲聊）。

        Returns:
            "A": 需要查询知识库的业务/专业问题
            "B": 日常闲聊、问候、与知识库无关的问题
        """
        system_prompt = (
            "You are a precise intent classifier. Output only A or B:\n"
            "A: Questions requiring knowledge base lookup (business, policy, product specifications, etc.)\n"
            "B: Casual conversation, greetings, or topics unrelated to the knowledge base"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question},
        ]
        response = await flash_llm.ainvoke(messages)
        return response.content.strip()

    def ingest_knowledge(self, md_text: str, source_filename: str) -> bool:
        """
        将 Markdown 文本切分后写入向量库，并热更新 BM25 检索器。

        Args:
            md_text: 已转换为 Markdown 格式的文档内容
            source_filename: 原始文件名，写入 metadata 用于来源溯源

        Returns:
            True 表示入库成功，False 表示发生异常
        """
        logger.info("Ingesting document: %s", source_filename)
        try:
            # 按 Markdown 标题层级切分，再按字符长度二次切分
            md_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[("#", "H1"), ("##", "H2"), ("###", "H3")]
            )
            md_chunks = md_splitter.split_text(md_text)

            text_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
            final_chunks = text_splitter.split_documents(md_chunks)

            # 基于内容生成幂等 ID，防止重复入库
            ids = []
            for chunk in final_chunks:
                chunk.metadata["source"] = source_filename
                ids.append(
                    hashlib.md5(
                        (chunk.page_content + source_filename).encode("utf-8")
                    ).hexdigest()
                )

            # 写入向量库
            vectorstore = self._get_vectorstore()
            if not vectorstore:
                self.vectorstore = Chroma(
                    persist_directory=str(DB_DIR),
                    embedding_function=embeddings_model,
                )
                vectorstore = self.vectorstore

            vectorstore.add_documents(final_chunks, ids=ids)

            # 重建 BM25 检索器并持久化
            all_db_data = vectorstore.get()
            all_docs = [
                Document(
                    page_content=all_db_data["documents"][i],
                    metadata=all_db_data["metadatas"][i],
                )
                for i in range(len(all_db_data["documents"]))
            ]
            self.bm25_retriever = BM25Retriever.from_documents(all_docs)
            with open(BM25_FILE, "wb") as f:
                pickle.dump(self.bm25_retriever, f)

            self._initialize_components()
            return True

        except Exception as e:
            logger.error("Failed to ingest document '%s': %s", source_filename, e)
            return False

    async def stream_rag_answer(self, question: str, history: list = None):
        """
        流式 RAG 问答主流程（全链路异步）。

        执行顺序：
        1. 查询重写（消除指代词）
        2. 语义路由（A/B 分流）
        3. A 路线：混合检索 -> Critic 评估 -> 流式生成 -> 来源标注
        4. B 路线：带人格的大模型直接回复
        """
        logger.info("Processing question: %s", question)
        clean_query = await self.rewrite_query(question, history) if history else question
        route = await self.classify_question(question)

        if "A" in route:
            if not self.final_retriever:
                yield "知识库尚未就绪，请先通过管理界面上传文档。"
                return

            retrieved_docs = await self.final_retriever.ainvoke(clean_query)
            context_str = "\n\n".join(doc.page_content for doc in retrieved_docs)

            # Critic Agent 前置评估
            if not await self.evaluate_context(question, context_str):
                yield "抱歉，知识库中没有与该问题相关的资料，为保证回答准确性，暂无法作答。"
                return

            answer_prompt = ChatPromptTemplate.from_template(
                """你是一个专业的企业知识库助手。请严格基于【参考资料】回答用户问题，不要添加资料中没有的内容。

                【参考资料】：
                {context}

                【用户问题】：
                {input}
                """
            )
            chain = answer_prompt | standard_llm | StrOutputParser()
            async for chunk in chain.astream({"context": context_str, "input": question}):
                yield chunk

            # 来源溯源
            if retrieved_docs:
                yield "\n\n---\n**参考来源：**\n"
                for i, source in enumerate(
                    set(d.metadata.get("source", "未知") for d in retrieved_docs), 1
                ):
                    yield f"{i}. {source}\n"

        else:
            # B 路线：带统一人格的闲聊回复
            persona_messages = [
                {
                    "role": "system",
                    "content": (
                        "你是一个企业级智能知识库助手，名字叫小智。"
                        "你的核心职责是帮用户解答知识库中的专业问题。"
                        "对于日常闲聊和问候，请用简短、友好的方式自然回应，并引导用户提出业务问题。"
                        "不要凭空捏造任何业务数据或知识库中不存在的信息。"
                    ),
                },
                {"role": "user", "content": question},
            ]
            async for chunk in plus_llm.astream(persona_messages):
                if chunk.content:
                    yield chunk.content

    def clear_all_data(self) -> bool:
        """清空向量库和 BM25 索引，并重置内存状态。"""
        vectorstore = self._get_vectorstore()
        if vectorstore:
            ids = vectorstore.get().get("ids", [])
            if ids:
                vectorstore.delete(ids=ids)

        if BM25_FILE.exists():
            os.remove(BM25_FILE)

        self.vectorstore = None
        self.bm25_retriever = None
        self._initialize_components()
        return True


# ---------------------------------------------------------------------------
# 模块级单例与兼容性导出
# ---------------------------------------------------------------------------
rag_engine = RAGEngine()


async def stream_rag_answer(question: str, history: list = None):
    async for chunk in rag_engine.stream_rag_answer(question, history):
        yield chunk


def ingest_knowledge(md_text: str, source_filename: str) -> bool:
    return rag_engine.ingest_knowledge(md_text, source_filename)


def clear_all_data() -> bool:
    return rag_engine.clear_all_data()