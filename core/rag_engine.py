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
try:
    import flashrank
    import langchain_community.document_compressors.flashrank as lc_flashrank
    setattr(lc_flashrank, 'Ranker', flashrank.Ranker)
    FlashrankRerank.model_rebuild()
except Exception:
    pass
from langchain_community.retrievers import BM25Retriever
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever

from core.llm_factory import flash_llm, standard_llm, plus_llm, embeddings_model
from langsmith import traceable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
DB_DIR = BASE_DIR / "data" / "chroma_db"
BM25_FILE = BASE_DIR / "data" / "bm25.pkl"


class RAGEngine:
    """
    RAG 检索生成引擎（单例，支持多租户隔离）

    负责管理向量数据库连接、多租户 BM25 检索器缓存、Rerank 压缩器，
    以及完整的异步流式问答流水线。
    """

    def __init__(self):
        self.vectorstore = None
        self.bm25_retrievers = {}  # 缓存不同租户的 BM25 检索器：tenant_id -> BM25Retriever
        self.compressor = None
        self._initialize_reranker()

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

    def _initialize_reranker(self):
        """初始化 Flashrank Rerank 压缩器。"""
        try:
            self.compressor = FlashrankRerank(top_n=8)
        except Exception as e:
            logger.warning("Reranker initialization failed: %s", e)

    def _get_bm25_retriever_for_tenant(self, tenant_id: str):
        """为指定租户获取或加载其专属的 BM25 检索器"""
        if tenant_id not in self.bm25_retrievers:
            bm25_file = BASE_DIR / "data" / f"bm25_{tenant_id}.pkl"
            try:
                if bm25_file.exists():
                    with open(bm25_file, "rb") as f:
                        self.bm25_retrievers[tenant_id] = pickle.load(f)
                else:
                    self.bm25_retrievers[tenant_id] = None
            except Exception as e:
                logger.error("Failed to load BM25 retriever for tenant %s: %s", tenant_id, e)
                self.bm25_retrievers[tenant_id] = None
        return self.bm25_retrievers[tenant_id]

    def _get_tenant_retriever(self, tenant_id: str):
        """为指定租户动态构建混合检索与精排管道"""
        vectorstore = self._get_vectorstore()
        if not vectorstore:
            return None

        # 1. 向量库检索器（加入 tenant_id filter 限制）
        base_retriever = vectorstore.as_retriever(
            search_kwargs={"filter": {"tenant_id": tenant_id}, "k": 8}
        )

        # 2. 当前租户专用的 BM25 检索器
        bm25_retriever = self._get_bm25_retriever_for_tenant(tenant_id)

        # 3. 混合检索（Ensemble 融合）
        if base_retriever and bm25_retriever:
            medium_retriever = EnsembleRetriever(
                retrievers=[base_retriever, bm25_retriever],
                weights=[0.5, 0.5],
            )
        else:
            medium_retriever = base_retriever

        # 4. Flashrank Rerank 精排过滤
        if not medium_retriever:
            return None

        if self.compressor:
            try:
                return ContextualCompressionRetriever(
                    base_compressor=self.compressor,
                    base_retriever=medium_retriever,
                )
            except Exception as e:
                logger.warning("Tenant reranker creation failed: %s", e)
        return medium_retriever

    @traceable(run_type="chain", name="Critic相关性评估裁判")
    async def evaluate_context(self, question: str, context: str) -> bool:
        """
        Critic Agent：判断检索到的上下文是否与问题相关。
        """
        eval_prompt = ChatPromptTemplate.from_template(
            """你是一个企业知识库 RAG 系统的证据评估裁判。
            你的任务不是判断参考资料是否已经组织成完整答案，而是判断资料中是否存在回答问题所需的事实依据。

            评判规则：
            1. 如果参考资料直接包含答案，或包含可以通过计算、比较、条件判断得出答案的关键事实，输出 YES。
            2. 对价格、折扣、保修、城市级别、补贴、报销、退货等问题，只要资料包含相关规则或数值依据，输出 YES。
            3. 对“文档是否提及某信息”的问题，只要参考资料属于同一产品、政策或主题，即使资料未提及该字段，也输出 YES，让回答模型基于资料说明“未提及”。
            4. 仅当参考资料与问题主题完全无关，无法提供任何事实依据时，输出 NO。
            5. 当不确定时，倾向于输出 YES 而不是 NO。
            6. 必须仅输出 YES 或 NO，不要包含任何其他说明文字。

            【参考资料】：
            {context}

            【用户问题】：
            {question}
            """
        )
        chain = eval_prompt | flash_llm | StrOutputParser()
        result = await chain.ainvoke({"context": context, "question": question})
        return "YES" in result.upper()

    @traceable(run_type="chain", name="多轮对话Query改写")
    async def rewrite_query(self, user_question: str, history: list) -> str:
        """根据对话历史将问题改写为独立的完整问句。"""
        if not history:
            return user_question

        history_text = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in history]
        )
        rewrite_prompt = ChatPromptTemplate.from_template(
            """请根据对话历史，将最新的用户问题改写为一个独立的、意思完整的问句。
            必须仅输出改写后的问句，不要包含任何其他文字。

            【对话历史】：
            {history}

            【最新问题】：
            {question}
            """
        )
        chain = rewrite_prompt | flash_llm | StrOutputParser()
        return await chain.ainvoke({"history": history_text, "question": user_question})

    @traceable(run_type="chain", name="日常与业务意图路由器")
    async def classify_question(self, user_question: str) -> str:
        """
        语义路由：将问题分类为 A（业务检索）或 B（闲聊）。
        """
        system_prompt = (
            "你是一个精准的意图分类器。请严格仅输出 A 或 B，不要包含任何其他字符：\n"
            "A: 需要检索知识库的问题（如业务规则、产品规格、公司政策、出差报销等专业知识性问题）\n"
            "B: 日常闲聊、打招呼、问候，或与知识库完全无关的随意对话"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question},
        ]
        response = await flash_llm.ainvoke(messages)
        return response.content.strip()

    @traceable(run_type="chain", name="多租户知识分片入库")
    def ingest_knowledge(self, md_text: str, source_filename: str, tenant_id: str = "default_tenant") -> bool:
        """
        将 Markdown 文本切分后写入向量库（注入租户ID），并重新生成该租户专属的 BM25 检索器。
        """
        logger.info("Ingesting document for tenant '%s': %s", tenant_id, source_filename)
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
                chunk.metadata["tenant_id"] = tenant_id
                # ID 计算也加入 tenant_id 防止多租户间哈希冲突
                ids.append(
                    hashlib.md5(
                        (chunk.page_content + source_filename + tenant_id).encode("utf-8")
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

            # 只提取当前租户的文档数据，以重建该租户专用的 BM25 检索器
            all_db_data = vectorstore.get(where={"tenant_id": tenant_id})
            if all_db_data and all_db_data.get("documents"):
                all_docs = [
                    Document(
                        page_content=all_db_data["documents"][i],
                        metadata=all_db_data["metadatas"][i],
                    )
                    for i in range(len(all_db_data["documents"]))
                ]
                bm25_retriever = BM25Retriever.from_documents(all_docs)
                self.bm25_retrievers[tenant_id] = bm25_retriever

                # 持久化为租户专属的 pkl
                bm25_file = BASE_DIR / "data" / f"bm25_{tenant_id}.pkl"
                with open(bm25_file, "wb") as f:
                    pickle.dump(bm25_retriever, f)

            return True

        except Exception as e:
            logger.error("Failed to ingest document '%s' for tenant %s: %s", source_filename, tenant_id, e)
            return False

    @traceable(run_type="chain", name="RAG流式问答流水线")
    async def stream_rag_answer(self, question: str, history: list = None, tenant_id: str = "default_tenant"):
        """
        流式 RAG 问答主流程（支持多租户）。
        """
        logger.info("Processing question for tenant %s: %s", tenant_id, question)
        clean_query = await self.rewrite_query(question, history) if history else question
        history_text = ""
        if history:
            history_text = "\n".join(
                [f"{msg['role']}: {msg['content']}" for msg in history]
            )
        route = await self.classify_question(question)

        if "A" in route:
            tenant_retriever = self._get_tenant_retriever(tenant_id)
            if not tenant_retriever:
                yield "知识库尚未就绪，请先通过管理界面上传文档。"
                return

            retrieved_docs = await tenant_retriever.ainvoke(clean_query)
            if not retrieved_docs:
                yield "抱歉，知识库中没有与该问题相关的资料，为保证回答准确性，暂无法作答。"
                return

            context_str = "\n\n".join(doc.page_content for doc in retrieved_docs)

            # Critic Agent 前置评估
            if not await self.evaluate_context(question, context_str):
                yield "抱歉，知识库中没有与该问题相关的资料，为保证回答准确性，暂无法作答。"
                return

            answer_prompt = ChatPromptTemplate.from_template(
                """你是一个专业的企业知识库助手。请严格基于【参考资料】回答用户问题，不要添加资料中没有的内容。
                如果存在【对话历史】，请结合历史理解用户当前问题中的指代词和省略信息，但最终回答仍必须以参考资料为依据。

                【对话历史】：
                {history}

                【参考资料】：
                {context}

                【用户问题】：
                {input}
                """
            )
            chain = answer_prompt | standard_llm | StrOutputParser()
            async for chunk in chain.astream(
                {"history": history_text, "context": context_str, "input": clean_query}
            ):
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
                        "你是一个智能知识库助手，名字叫小智。"
                        "你的核心职责是帮用户解答知识库中的专业问题。"
                        "对于日常闲聊和问候，请用简短、友好的方式自然回应，并引导用户提出业务问题。"
                        "不要凭空捏造任何业务数据或知识库中不存在的信息。"
                    ),
                },
            ]
            if history:
                persona_messages.extend(history[-6:])
            persona_messages.append({"role": "user", "content": question})
            async for chunk in flash_llm.astream(persona_messages):
                if chunk.content:
                    yield chunk.content

    def clear_all_data(self, tenant_id: str) -> bool:
        """仅清空指定租户的向量库和 BM25 索引，并重置其内存状态。"""
        vectorstore = self._get_vectorstore()
        if vectorstore:
            # 只获取该租户的数据以进行删除
            all_db_data = vectorstore.get(where={"tenant_id": tenant_id})
            ids = all_db_data.get("ids", [])
            if ids:
                vectorstore.delete(ids=ids)

        bm25_file = BASE_DIR / "data" / f"bm25_{tenant_id}.pkl"
        if bm25_file.exists():
            os.remove(bm25_file)

        if tenant_id in self.bm25_retrievers:
            del self.bm25_retrievers[tenant_id]

        return True


# ---------------------------------------------------------------------------
# 模块级单例与兼容性导出
# ---------------------------------------------------------------------------
rag_engine = RAGEngine()


async def stream_rag_answer(question: str, history: list = None, tenant_id: str = "default_tenant"):
    async for chunk in rag_engine.stream_rag_answer(question, history, tenant_id):
        yield chunk


def ingest_knowledge(md_text: str, source_filename: str, tenant_id: str = "default_tenant") -> bool:
    return rag_engine.ingest_knowledge(md_text, source_filename, tenant_id)


def clear_all_data(tenant_id: str) -> bool:
    return rag_engine.clear_all_data(tenant_id)
