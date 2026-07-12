"""Core RAG engine for retrieval, reranking, and streaming answers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
from pathlib import Path
from typing import List

from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_community.document_compressors import FlashrankRerank
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import Chroma
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langsmith import traceable
from pydantic import ConfigDict

from core.llm_factory import embeddings_model, flash_llm, standard_llm

logger = logging.getLogger(__name__)

try:
    import flashrank
    import langchain_community.document_compressors.flashrank as lc_flashrank

    setattr(lc_flashrank, "Ranker", flashrank.Ranker)
    FlashrankRerank.model_rebuild()
except Exception:
    flashrank = None

BASE_DIR = Path(__file__).parent.parent
DB_DIR = BASE_DIR / "data" / "chroma_db"

PROMPT_INJECTION_KEYWORDS = [
    "system prompt",
    "system message",
    "ignore the instruction",
    "ignore previous",
    "translate the above",
    "spell check the above",
    "you are now a",
    "忘掉",
    "忽略之前的",
    "打印系统提示",
    "输出你的设定",
    "扮演",
    "你现在是",
    "绕过设定",
]

MISSING_KNOWLEDGE_MESSAGE = "知识库为空，请先上传文档。"
NO_MATCH_MESSAGE = "在知识库中未找到与此问题相关的参考资料。"
PROMPT_BLOCK_MESSAGE = (
    "[安全提示] 检测到潜在的提示词注入或越权尝试。该请求已被安全拦截。"
)
METADATA_START_MARKER = "__METADATA_START__"
METADATA_END_MARKER = "__METADATA_END__"
SMALL_TALK_EXACT_MATCHES = {
    "hi",
    "hello",
    "hey",
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "在吗",
    "谢谢",
    "thanks",
    "thankyou",
    "thankyou!",
}
SMALL_TALK_CONTAINS_MATCHES = [
    "你是谁",
    "介绍一下你自己",
    "介绍你自己",
    "你能做什么",
    "你会什么",
    "你可以做什么",
    "你是做什么的",
]


class MultiTenantRRFRetriever(BaseRetriever):
    vector_retriever: BaseRetriever
    bm25_retriever: BaseRetriever | None = None
    k: int = 60
    vector_weight: float = 0.5
    bm25_weight: float = 0.5
    top_n: int = 8
    doc_type: str = "document"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> List[Document]:
        import asyncio

        return asyncio.run(self._aget_relevant_documents(query, run_manager=run_manager))

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> List[Document]:
        import asyncio

        tasks = [self.vector_retriever.ainvoke(query)]
        if self.bm25_retriever:
            tasks.append(self.bm25_retriever.ainvoke(query))

        results = await asyncio.gather(*tasks)
        vector_docs = results[0]
        bm25_docs = results[1] if len(results) > 1 else []

        # 过滤只保留符合当前检索 doc_type 类型的文档，避免 BM25 检索发生越界召回
        bm25_docs = [
            doc for doc in bm25_docs
            if doc.metadata.get("doc_type", "document") == self.doc_type
        ]

        vector_weight = self.vector_weight
        bm25_weight = self.bm25_weight
        if len(query) < 5 or any(char.isdigit() for char in query):
            vector_weight = 0.3
            bm25_weight = 0.7

        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        def get_doc_key(doc: Document) -> str:
            content_hash = hashlib.md5(doc.page_content.encode("utf-8")).hexdigest()
            source = doc.metadata.get("source", "unknown")
            return f"{source}_{content_hash}"

        for rank, doc in enumerate(vector_docs, start=1):
            key = get_doc_key(doc)
            doc_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + vector_weight * (1.0 / (self.k + rank))
            doc.metadata["vector_rank"] = rank

        for rank, doc in enumerate(bm25_docs, start=1):
            key = get_doc_key(doc)
            if key not in doc_map:
                doc_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + bm25_weight * (1.0 / (self.k + rank))
            doc_map[key].metadata["bm25_rank"] = rank

        sorted_keys = sorted(rrf_scores.keys(), key=lambda key: rrf_scores[key], reverse=True)
        final_docs: list[Document] = []
        for key in sorted_keys[: self.top_n]:
            doc = doc_map[key]
            doc.metadata["rrf_score"] = round(rrf_scores[key], 6)
            final_docs.append(doc)
        return final_docs


class RAGEngine:
    """Single-instance RAG engine with tenant isolation."""

    def __init__(self):
        self.vectorstore = None
        self.bm25_retrievers: dict[str, BM25Retriever | None] = {}
        self.compressor = None


    def _build_vectorstore(self):
        return Chroma(
            persist_directory=str(DB_DIR),
            embedding_function=embeddings_model,
        )

    def _get_vectorstore(self):
        if self.vectorstore is None:
            if DB_DIR.exists():
                self.vectorstore = self._build_vectorstore()
            else:
                logger.warning("Local Chroma database not found. Waiting for first document upload.")
        return self.vectorstore

    def _get_reranker(self):
        if self.compressor is not None:
            return self.compressor
        if flashrank is None:
            logger.info("Flashrank is unavailable, falling back to retrieval without reranking.")
            return None
        try:
            logger.info("Initializing Flashrank Reranker (Lazy Loading)...")
            self.compressor = FlashrankRerank(top_n=8)
            logger.info("Flashrank Reranker initialized successfully.")
            return self.compressor
        except Exception as exc:
            logger.warning("Reranker initialization failed: %s", exc)
            return None


    def _bm25_file_for_tenant(self, tenant_id: str) -> Path:
        return BASE_DIR / "data" / f"bm25_{tenant_id}.pkl"

    def _persist_bm25_retriever(self, tenant_id: str, retriever: BM25Retriever | None) -> None:
        bm25_file = self._bm25_file_for_tenant(tenant_id)
        if retriever is None:
            if bm25_file.exists():
                bm25_file.unlink()
            self.bm25_retrievers[tenant_id] = None
            return

        bm25_file.parent.mkdir(parents=True, exist_ok=True)
        with open(bm25_file, "wb") as file:
            pickle.dump(retriever, file)
        self.bm25_retrievers[tenant_id] = retriever

    def _rebuild_bm25_retriever(self, tenant_id: str, vectorstore) -> None:
        all_db_data = vectorstore.get(where={"tenant_id": tenant_id})
        if not all_db_data or not all_db_data.get("documents"):
            self._persist_bm25_retriever(tenant_id, None)
            return

        all_docs = [
            Document(
                page_content=all_db_data["documents"][index],
                metadata=all_db_data["metadatas"][index],
            )
            for index in range(len(all_db_data["documents"]))
        ]
        self._persist_bm25_retriever(tenant_id, BM25Retriever.from_documents(all_docs))

    def _get_bm25_retriever_for_tenant(self, tenant_id: str):
        if tenant_id not in self.bm25_retrievers:
            bm25_file = self._bm25_file_for_tenant(tenant_id)
            try:
                if bm25_file.exists():
                    with open(bm25_file, "rb") as file:
                        self.bm25_retrievers[tenant_id] = pickle.load(file)
                else:
                    self.bm25_retrievers[tenant_id] = None
            except Exception as exc:
                logger.error("Failed to load BM25 retriever for tenant %s: %s", tenant_id, exc)
                self.bm25_retrievers[tenant_id] = None
        return self.bm25_retrievers[tenant_id]

    def _get_tenant_retriever(self, tenant_id: str, doc_type: str = "document"):
        vectorstore = self._get_vectorstore()
        if not vectorstore:
            return None

        # 对齐多租户与知识空间（RAG/Wiki）的双重隔离
        filter_dict = {"$and": [{"tenant_id": tenant_id}, {"doc_type": doc_type}]}
        base_retriever = vectorstore.as_retriever(
            search_kwargs={"filter": filter_dict, "k": 8}
        )
        bm25_retriever = self._get_bm25_retriever_for_tenant(tenant_id)

        if base_retriever and bm25_retriever:
            medium_retriever = MultiTenantRRFRetriever(
                vector_retriever=base_retriever,
                bm25_retriever=bm25_retriever,
                top_n=8,
                doc_type=doc_type,
            )
        else:
            medium_retriever = base_retriever

        if not medium_retriever:
            return None

        reranker = self._get_reranker()
        if reranker:
            try:
                return ContextualCompressionRetriever(
                    base_compressor=reranker,
                    base_retriever=medium_retriever,
                )
            except Exception as exc:
                logger.warning("Tenant reranker creation failed: %s", exc)

        return medium_retriever

    @traceable(run_type="chain", name="critic_context_evaluation")
    async def evaluate_context(self, question: str, context: str) -> bool:
        eval_prompt = ChatPromptTemplate.from_template(
            """你是企业 RAG 系统中的证据相关性判定器。
请判断参考资料是否包含足够证据回答用户问题。

判定规则：
1. 如果参考资料直接包含答案，输出 YES。
2. 如果参考资料包含可推导答案的事实，输出 YES。
3. 如果用户问题是在询问文档是否提到某事，且参考资料主题明显相关，输出 YES。
4. 只有当参考资料与问题完全无关时，才输出 NO。
5. 不确定时优先输出 YES。
6. 只能输出 YES 或 NO，不要输出其他解释。

参考资料：
{context}

用户问题：
{question}
"""
        )
        chain = eval_prompt | flash_llm | StrOutputParser()
        result = await chain.ainvoke({"context": context, "question": question})
        return "YES" in result.upper()

    @traceable(run_type="chain", name="rewrite_query")
    async def rewrite_query(self, user_question: str, history: list) -> str:
        if not history:
            return user_question

        history_text = "\n".join(f"{msg['role']}: {msg['content']}" for msg in history)
        rewrite_prompt = ChatPromptTemplate.from_template(
            """请把用户的最新问题改写成一个独立、完整、无需依赖上下文也能理解的问题。
要求：
1. 只输出改写后的问题，不要解释。
2. 保持用户原本的语言；如果用户用中文提问，必须输出简体中文。
3. 不要改变用户原意，不要补充对话中没有的信息。

对话历史：
{history}

最新问题：
{question}
"""
        )
        chain = rewrite_prompt | flash_llm | StrOutputParser()
        return await chain.ainvoke({"history": history_text, "question": user_question})

    @traceable(run_type="chain", name="classify_question")
    async def classify_question(self, user_question: str) -> str:
        system_prompt = (
            "请判断用户输入类型，只能输出 A 或 B，不要输出其他内容。\n"
            "A：需要检索知识库才能回答的问题。\n"
            "B：闲聊、问候、感谢、自我介绍，或与知识库无关的小范围对话。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question},
        ]
        response = await flash_llm.ainvoke(messages)
        label = response.content.strip().upper()
        if label.startswith("A"):
            return "A"
        if label.startswith("B"):
            return "B"
        logger.warning("Unexpected question classification result: %s", response.content)
        return "A"

    @traceable(run_type="chain", name="ingest_knowledge")
    def ingest_knowledge(
        self,
        md_text: str,
        source_filename: str,
        tenant_id: str = "default_tenant",
        doc_type: str = "document",
    ) -> bool:
        logger.info("Ingesting document for tenant '%s' (type=%s): %s", tenant_id, doc_type, source_filename)
        try:
            md_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[("#", "H1"), ("##", "H2"), ("###", "H3")]
            )
            md_chunks = md_splitter.split_text(md_text)

            text_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
            final_chunks = text_splitter.split_documents(md_chunks)

            ids = []
            for chunk in final_chunks:
                chunk.metadata["source"] = source_filename
                chunk.metadata["tenant_id"] = tenant_id
                chunk.metadata["doc_type"] = doc_type
                ids.append(
                    hashlib.md5(
                        (chunk.page_content + source_filename + tenant_id + doc_type).encode("utf-8")
                    ).hexdigest()
                )

            vectorstore = self._get_vectorstore()
            if not vectorstore:
                DB_DIR.mkdir(parents=True, exist_ok=True)
                self.vectorstore = self._build_vectorstore()
                vectorstore = self.vectorstore

            vectorstore.add_documents(final_chunks, ids=ids)
            self._rebuild_bm25_retriever(tenant_id, vectorstore)

            return True
        except Exception as exc:
            logger.error(
                "Failed to ingest document '%s' for tenant %s (type=%s): %s",
                source_filename,
                tenant_id,
                doc_type,
                exc,
            )
            return False

    def _is_prompt_injection(self, question: str) -> bool:
        normalized_question = question.lower().replace(" ", "")
        for keyword in PROMPT_INJECTION_KEYWORDS:
            if keyword.replace(" ", "") in normalized_question:
                logger.warning("Prompt injection detected by keyword rule: %s", keyword)
                return True
        return False

    def _is_small_talk(self, question: str) -> bool:
        normalized_question = question.strip().lower()
        compact_question = normalized_question.replace(" ", "")
        if compact_question in SMALL_TALK_EXACT_MATCHES:
            return True
        if any(keyword in compact_question for keyword in SMALL_TALK_CONTAINS_MATCHES):
            return True
        return False

    async def _stream_persona_response(self, question: str, history: list | None = None):
        persona_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个友好、专业的企业知识助手。"
                    "默认使用简体中文回答用户，除非用户明确要求使用其他语言。"
                    "闲聊场景下回答要简短、自然，并在合适时引导用户提问与企业知识库相关的问题。"
                ),
            }
        ]
        if history:
            persona_messages.extend(history[-6:])
        persona_messages.append({"role": "user", "content": question})
        async for chunk in flash_llm.astream(persona_messages):
            if chunk.content:
                yield chunk.content


    async def stream_rag_answer(
        self,
        question: str,
        history: list | None = None,
        tenant_id: str = "default_tenant",
        search_mode: str = "RAG_ONLY",
    ):
        logger.info("Processing question for tenant %s (mode=%s): %s", tenant_id, search_mode, question)

        if self._is_prompt_injection(question):
            yield "__STAGE__:GENERATING\n"
            yield PROMPT_BLOCK_MESSAGE
            return

        if self._is_small_talk(question):
            yield "__STAGE__:UNDERSTANDING\n"
            yield "__STAGE__:GENERATING\n"
            async for chunk in self._stream_persona_response(question, history):
                yield chunk
            return

        yield "__STAGE__:UNDERSTANDING\n"

        yield "__STAGE__:REWRITE\n"
        clean_query = await self.rewrite_query(question, history) if history else question
        history_text = ""
        if history:
            history_text = "\n".join(f"{msg['role']}: {msg['content']}" for msg in history)

        if search_mode == "WIKI_ONLY":
            from core.database import SessionLocal
            from core.models import WikiPage, WikiItem
            db = SessionLocal()
            try:
                # 找出当前租户下的 Wiki 页面
                wiki_pages = db.query(WikiPage).filter(WikiPage.tenant_id == tenant_id).all()
                page_ids = [p.id for p in wiki_pages]
                
                matched_items = []
                if page_ids:
                    all_items = db.query(WikiItem).filter(WikiItem.wiki_page_id.in_(page_ids)).all()
                    # 依据 Query 相似度粗筛
                    for item in all_items:
                        score = 0
                        if item.key.lower() in clean_query.lower() or clean_query.lower() in item.key.lower():
                            score += 15
                        common_chars = set(item.key.lower()) & set(clean_query.lower())
                        score += len(common_chars)
                        if score > 0:
                            matched_items.append((item, score))
                    
                    matched_items.sort(key=lambda x: x[1], reverse=True)
                    matched_items = [x[0] for x in matched_items[:5]]
                
                if not matched_items:
                    yield "__STAGE__:GENERATING\n"
                    yield "在已编译的 Wiki 知识库中未匹配到相关专有名词或 FAQ。建议切换为“查原文细节 (RAG)”模式进行全文细粒度检索。"
                    return
                
                # 拼接 Wiki 词条为上下文
                context_parts = []
                for item in matched_items:
                    cat_name = "核心概念" if item.category == "concept" else "关键条款" if item.category == "clause" else "典型问答"
                    context_parts.append(
                        f"【{cat_name}】{item.key}\n内容解析: {item.value}\n原文安全溯源选段: {item.citation or '无'}"
                    )
                context_str = "\n\n---\n\n".join(context_parts)
                
                yield "__STAGE__:RETRIEVING\n" # 使 Trace 显示正确
                yield "__STAGE__:RERANKING\n"
                yield "__STAGE__:GENERATING\n"
                
                answer_prompt = ChatPromptTemplate.from_template(
                    "你是一个专业的企业知识助手。请结合提供的 Wiki 词条与问答，以自然、专业、通顺的语气回答用户的问题。\n\n"
                    "【回答要求】:\n"
                    "1. 必须且只能基于提供的参考 Wiki 数据进行回答。回答结构应当【先进行简明扼要的总结，然后再分点展开详细说明】。\n"
                    "2. 不要机械地照搬原文，要总结概括得有条理。\n"
                    "3. 如果参考 Wiki 数据中没有答案，请说“在 Wiki 知识库中未找到相关概念回答”。\n\n"
                    "参考 Wiki 数据:\n{context}\n\n"
                    "用户问题:\n{input}\n"
                )
                chain = answer_prompt | standard_llm | StrOutputParser()
                async for chunk in chain.astream(
                    {"context": context_str, "input": clean_query}
                ):
                    yield chunk
                
                # 组装证据链
                page_to_doc = {p.id: p.document_id for p in wiki_pages}
                doc_ids = [page_to_doc.get(item.wiki_page_id) for item in matched_items if item.wiki_page_id in page_to_doc]
                doc_map = {}
                if doc_ids:
                    from core.models import DocumentRecord
                    docs = db.query(DocumentRecord).filter(DocumentRecord.id.in_(doc_ids)).all()
                    doc_map = {d.id: d.filename for d in docs}
                
                chunks_payload = []
                for item in matched_items:
                    source_file = "未知来源"
                    doc_id = page_to_doc.get(item.wiki_page_id)
                    if doc_id and doc_id in doc_map:
                        source_file = doc_map[doc_id]
                    chunks_payload.append({
                        "content": f"【{item.key}】: {item.value}",
                        "source": source_file,
                        "rrf_score": 0.99,
                        "vector_rank": 1,
                        "bm25_rank": 1,
                        "h1": item.key,
                        "h2": "",
                        "h3": ""
                    })
                
                metadata_str = json.dumps({"chunks": chunks_payload}, ensure_ascii=False)
                yield f"\n\n{METADATA_START_MARKER}\n{metadata_str}\n{METADATA_END_MARKER}"
                return
            finally:
                db.close()

        yield "__STAGE__:RETRIEVING\n"
        route = await self.classify_question(question)
        if "A" in route:
            doc_type = "wiki" if search_mode == "WIKI_ONLY" else "document"
            tenant_retriever = self._get_tenant_retriever(tenant_id, doc_type=doc_type)
            if not tenant_retriever:
                yield "__STAGE__:GENERATING\n"
                yield MISSING_KNOWLEDGE_MESSAGE
                return

            retrieved_docs = await tenant_retriever.ainvoke(clean_query)
            if not retrieved_docs:
                yield "__STAGE__:GENERATING\n"
                yield NO_MATCH_MESSAGE
                return

            yield "__STAGE__:RERANKING\n"
            context_str = "\n\n".join(doc.page_content for doc in retrieved_docs)
            if not await self.evaluate_context(question, context_str):
                yield "__STAGE__:GENERATING\n"
                yield NO_MATCH_MESSAGE
                return

            yield "__STAGE__:GENERATING\n"
            answer_prompt = ChatPromptTemplate.from_template(
                """你是一个专业的企业知识助手。
请结合提供的对话历史与参考资料，以自然、专业、通顺的语气回答用户的问题。

【回答要求】：
0. 默认必须使用简体中文回答；除非用户明确要求使用其他语言，否则不要输出英文回答。
1. 必须且只能基于提供的参考资料进行回答。回答结构应当【先进行简明扼要的总结，然后再分点展开详细说明】。
2. 表达必须自然、通顺、专业，像资深专家一样对信息进行提炼与归纳，绝对不允许机械地直接复制或照搬参考资料原文。
3. 结构清晰，合理使用标准的 Markdown 格式（如标题、加粗重点、无序或有序列表等）以提高可读性。
4. 如果参考资料中没有相关答案，或者提供的信息不足以回答该问题，请直接明确说明“在参考资料中未找到相关信息”，绝对不要捏造或凭空想象。

对话历史：
{history}

参考资料：
{context}

用户问题：
{input}
"""
            )
            chain = answer_prompt | standard_llm | StrOutputParser()
            async for chunk in chain.astream(
                {"history": history_text, "context": context_str, "input": clean_query}
            ):
                yield chunk

            chunks_payload = [
                {
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", "未知来源"),
                    "rrf_score": doc.metadata.get("rrf_score", 0.0),
                    "vector_rank": doc.metadata.get("vector_rank"),
                    "bm25_rank": doc.metadata.get("bm25_rank"),
                    "h1": doc.metadata.get("H1", ""),
                    "h2": doc.metadata.get("H2", ""),
                    "h3": doc.metadata.get("H3", ""),
                }
                for doc in retrieved_docs
            ]
            metadata_str = json.dumps({"chunks": chunks_payload}, ensure_ascii=False)
            yield f"\n\n{METADATA_START_MARKER}\n{metadata_str}\n{METADATA_END_MARKER}"
            return

        yield "__STAGE__:GENERATING\n"
        async for chunk in self._stream_persona_response(question, history):
            yield chunk

    def clear_all_data(self, tenant_id: str) -> bool:
        vectorstore = self._get_vectorstore()
        if vectorstore:
            all_db_data = vectorstore.get(where={"tenant_id": tenant_id})
            ids = all_db_data.get("ids", [])
            if ids:
                vectorstore.delete(ids=ids)
        self._persist_bm25_retriever(tenant_id, None)
        return True

    def remove_document(self, source_filename: str, tenant_id: str) -> bool:
        vectorstore = self._get_vectorstore()
        if not vectorstore:
            self._persist_bm25_retriever(tenant_id, None)
            return True

        where_filter = {"$and": [{"tenant_id": tenant_id}, {"source": source_filename}]}
        db_data = vectorstore.get(where=where_filter)
        ids = db_data.get("ids", []) if db_data else []
        if ids:
            vectorstore.delete(ids=ids)
            self._rebuild_bm25_retriever(tenant_id, vectorstore)
        else:
            self._persist_bm25_retriever(tenant_id, self._get_bm25_retriever_for_tenant(tenant_id))
        return True


rag_engine = RAGEngine()


async def stream_rag_answer(
    question: str,
    history: list | None = None,
    tenant_id: str = "default_tenant",
    search_mode: str = "RAG_ONLY",
):
    async for chunk in rag_engine.stream_rag_answer(question, history, tenant_id, search_mode):
        yield chunk


def ingest_knowledge(
    md_text: str,
    source_filename: str,
    tenant_id: str = "default_tenant",
    doc_type: str = "document",
) -> bool:
    return rag_engine.ingest_knowledge(md_text, source_filename, tenant_id, doc_type)


def clear_all_data(tenant_id: str) -> bool:
    return rag_engine.clear_all_data(tenant_id)


def remove_document(source_filename: str, tenant_id: str) -> bool:
    return rag_engine.remove_document(source_filename, tenant_id)
