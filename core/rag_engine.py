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
        self._initialize_reranker()

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

    def _initialize_reranker(self):
        if flashrank is None:
            logger.info("Flashrank is unavailable, falling back to retrieval without reranking.")
            return
        try:
            self.compressor = FlashrankRerank(top_n=8)
        except Exception as exc:
            logger.warning("Reranker initialization failed: %s", exc)

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

    def _get_tenant_retriever(self, tenant_id: str):
        vectorstore = self._get_vectorstore()
        if not vectorstore:
            return None

        base_retriever = vectorstore.as_retriever(
            search_kwargs={"filter": {"tenant_id": tenant_id}, "k": 8}
        )
        bm25_retriever = self._get_bm25_retriever_for_tenant(tenant_id)

        if base_retriever and bm25_retriever:
            medium_retriever = MultiTenantRRFRetriever(
                vector_retriever=base_retriever,
                bm25_retriever=bm25_retriever,
                top_n=8,
            )
        else:
            medium_retriever = base_retriever

        if not medium_retriever:
            return None

        if self.compressor:
            try:
                return ContextualCompressionRetriever(
                    base_compressor=self.compressor,
                    base_retriever=medium_retriever,
                )
            except Exception as exc:
                logger.warning("Tenant reranker creation failed: %s", exc)
        return medium_retriever

    @traceable(run_type="chain", name="critic_context_evaluation")
    async def evaluate_context(self, question: str, context: str) -> bool:
        eval_prompt = ChatPromptTemplate.from_template(
            """You are a relevance checker for an enterprise RAG system.
Decide whether the reference material contains enough evidence to answer the user's question.

Rules:
1. Output YES if the reference directly contains the answer.
2. Output YES if the reference contains facts that allow the answer to be derived.
3. Output YES if the question asks whether the document mentions something and the material is clearly about the same topic.
4. Output NO only if the reference is completely unrelated to the question.
5. When unsure, prefer YES.
6. Output only YES or NO.

Reference:
{context}

Question:
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
            """Rewrite the latest user question into a self-contained question.
Return only the rewritten question.

History:
{history}

Latest question:
{question}
"""
        )
        chain = rewrite_prompt | flash_llm | StrOutputParser()
        return await chain.ainvoke({"history": history_text, "question": user_question})

    @traceable(run_type="chain", name="classify_question")
    async def classify_question(self, user_question: str) -> str:
        system_prompt = (
            "Classify the user input. Output only A or B.\n"
            "A: knowledge-base question that needs retrieval.\n"
            "B: casual conversation or unrelated small talk."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question},
        ]
        response = await flash_llm.ainvoke(messages)
        return response.content.strip()

    @traceable(run_type="chain", name="ingest_knowledge")
    def ingest_knowledge(
        self,
        md_text: str,
        source_filename: str,
        tenant_id: str = "default_tenant",
    ) -> bool:
        logger.info("Ingesting document for tenant '%s': %s", tenant_id, source_filename)
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
                ids.append(
                    hashlib.md5(
                        (chunk.page_content + source_filename + tenant_id).encode("utf-8")
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
                "Failed to ingest document '%s' for tenant %s: %s",
                source_filename,
                tenant_id,
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
                    "You are a helpful enterprise assistant. "
                    "For casual chat, be brief, friendly, and guide the user back to knowledge-base questions when appropriate."
                ),
            }
        ]
        if history:
            persona_messages.extend(history[-6:])
        persona_messages.append({"role": "user", "content": question})
        async for chunk in flash_llm.astream(persona_messages):
            if chunk.content:
                yield chunk.content

    @traceable(run_type="chain", name="stream_rag_answer")
    async def stream_rag_answer(
        self,
        question: str,
        history: list | None = None,
        tenant_id: str = "default_tenant",
    ):
        logger.info("Processing question for tenant %s: %s", tenant_id, question)

        if self._is_prompt_injection(question):
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

        yield "__STAGE__:RETRIEVING\n"
        route = await self.classify_question(question)
        if "A" in route:
            tenant_retriever = self._get_tenant_retriever(tenant_id)
            if not tenant_retriever:
                yield MISSING_KNOWLEDGE_MESSAGE
                return

            retrieved_docs = await tenant_retriever.ainvoke(clean_query)
            if not retrieved_docs:
                yield NO_MATCH_MESSAGE
                return

            yield "__STAGE__:RERANKING\n"
            context_str = "\n\n".join(doc.page_content for doc in retrieved_docs)
            if not await self.evaluate_context(question, context_str):
                yield NO_MATCH_MESSAGE
                return

            yield "__STAGE__:GENERATING\n"
            answer_prompt = ChatPromptTemplate.from_template(
                """你是一个专业的企业知识助手。
请结合提供的对话历史与参考资料，以自然、专业、通顺的语气回答用户的问题。

【回答要求】：
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
):
    async for chunk in rag_engine.stream_rag_answer(question, history, tenant_id):
        yield chunk


def ingest_knowledge(
    md_text: str,
    source_filename: str,
    tenant_id: str = "default_tenant",
) -> bool:
    return rag_engine.ingest_knowledge(md_text, source_filename, tenant_id)


def clear_all_data(tenant_id: str) -> bool:
    return rag_engine.clear_all_data(tenant_id)


def remove_document(source_filename: str, tenant_id: str) -> bool:
    return rag_engine.remove_document(source_filename, tenant_id)
