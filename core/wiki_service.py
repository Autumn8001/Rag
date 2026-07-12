import json
import re
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from core.llm_factory import standard_llm
from core.models import WikiPage, WikiItem, DocumentRecord
from core.rag_engine import ingest_knowledge

logger = logging.getLogger(__name__)

def clean_and_parse_json(text: str) -> dict:
    """健壮地尝试从 LLM 输出中解析 JSON 块"""
    text_clean = text.strip()
    
    # 1. 尝试直接解析
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass
        
    # 2. 尝试移除 Markdown ```json 围栏
    if text_clean.startswith("```"):
        # 移除开头的 ```json 或 ```
        text_clean = re.sub(r"^```(?:json)?\n", "", text_clean)
        # 移除结尾的 ```
        text_clean = re.sub(r"\n```$", "", text_clean)
        try:
            return json.loads(text_clean.strip())
        except json.JSONDecodeError:
            pass

    # 3. 用正则表达式搜索匹配第一个花括号包围的 JSON 块
    match = re.search(r"(\{.*\})", text_clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError("Failed to extract and parse any valid JSON content from response")


async def generate_and_save_wiki(
    db: Session,
    document_id: int,
    tenant_id: str,
    user_id: str,
    orig_filename: str,
    md_text: str
) -> bool:
    """
    大模型编译 Wiki 服务：
    1. 限制输入字符为前 30,000 字以防爆 Token。
    2. 提炼文档摘要、核心概念、关键条款和常见 FAQs 并记录原文出处。
    3. 支持 JSON 损坏时的自动降级防御，生成兜底 Wiki，绝不阻断上传。
    4. 将编译出的每一项 Wiki 条目转化为 doc_type='wiki' 虚拟分片写入 Chroma 向量数据库。
    """
    logger.info("Starting Wiki compilation for document ID %s, tenant %s", document_id, tenant_id)
    
    # 防御保护 1：限制文档最大字符长度
    truncated_text = md_text[:30000]
    
    prompt = f"""你是一个专业的高级知识编译器。请为以下文档生成结构化的 Wiki 知识页面。
默认必须使用【简体中文】进行提炼和回答。

你必须且只能输出以下精确的 JSON 格式，且不要包含任何其他说明性文本或 Markdown 代码块围栏。
如果文档内容太短以至于无法提取相应概念或条款，请在相应数组中保持为空，不要删除任何字段。

输出格式规范：
{{
  "title": "根据文档内容提炼一个精炼大气的 Wiki 页面标题",
  "summary": "全局宏观摘要，概括文档的核心主旨（字数控制在 100-200 字之间）",
  "concepts": [
    {{
      "name": "概念名称",
      "definition": "名词定义与解释",
      "citation": "文档原文中对应的核心证据片段，不要虚构"
    }}
  ],
  "clauses": [
    {{
      "title": "关键条款标题",
      "content": "条款规则详细内容",
      "citation": "文档原文中对应的核心规则段落"
    }}
  ],
  "faqs": [
    {{
      "question": "针对此文档用户可能关心的常见或高频典型问题？",
      "answer": "基于文档内容的准确回答",
      "citation": "文档原文中对应解答的具体片段"
    }}
  ]
}}

待编译的原始文档：
{truncated_text}
"""
    
    wiki_data = None
    try:
        # 调用大模型执行同步/异步提炼
        response = await standard_llm.ainvoke([
            {"role": "user", "content": prompt}
        ])
        llm_response = response.content
        
        # 尝试强解析
        wiki_data = clean_and_parse_json(llm_response)
        logger.info("Wiki content compiled successfully by LLM for doc ID %s", document_id)
    except Exception as exc:
        # 防御保护 2：JSON 损坏或大模型超时异常降级保护
        logger.error("LLM Wiki generation or JSON parsing failed for doc ID %s: %s. Initiating fallback...", document_id, exc)
        
        # 兜底降级方案：创建一份高容错的基础 Wiki 结构
        wiki_data = {
            "title": orig_filename,
            "summary": f"该文档已成功导入知识库。因文档格式复杂或大模型提炼超时，已触发工程防线自动降级编译。文档前 300 字符预览：\n{truncated_text[:300]}...",
            "concepts": [
                {
                    "name": "自动降级提示",
                    "definition": "本 Wiki 页面为工程高容错降级生成。系统已成功对原始文档进行了分片向量化，不影响全文细节问答。",
                    "citation": "系统自动生成"
                }
            ],
            "clauses": [],
            "faqs": [
                {
                    "question": "如何查询此文档的详细细节？",
                    "answer": "请在智能问答面板中，切换至 'RAG 模式' 进行针对性提问，即可从原始文档分片中直接检索到所有精确的原文细节。",
                    "citation": "系统自动生成"
                }
            ]
        }

    # 3. 将 Wiki 内容转换并拼接为完整的 Markdown 页面存储
    title = wiki_data.get("title") or orig_filename
    summary = wiki_data.get("summary") or "暂无摘要"
    
    md_content = f"# {title}\n\n"
    md_content += f"## 📖 文档摘要\n{summary}\n\n"
    
    if wiki_data.get("concepts"):
        md_content += "## 📚 核心概念词典\n"
        for idx, c in enumerate(wiki_data["concepts"]):
            md_content += f"### {idx+1}. {c.get('name')}\n"
            md_content += f"- **名词定义**: {c.get('definition')}\n"
            if c.get("citation"):
                md_content += f"- *📌 原文依据*: {c.get('citation')}\n"
            md_content += "\n"
            
    if wiki_data.get("clauses"):
        md_content += "## ⚖️ 关键合规条款\n"
        for idx, c in enumerate(wiki_data["clauses"]):
            md_content += f"### {idx+1}. {c.get('title')}\n"
            md_content += f"- **规则条款**: {c.get('content')}\n"
            if c.get("citation"):
                md_content += f"- *📌 原文依据*: {c.get('citation')}\n"
            md_content += "\n"
            
    if wiki_data.get("faqs"):
        md_content += "## ❓ 常见问题 FAQs\n"
        for idx, f in enumerate(wiki_data["faqs"]):
            md_content += f"### Q: {f.get('question')}\n"
            md_content += f"- **A**: {f.get('answer')}\n"
            if f.get("citation"):
                md_content += f"- *📌 原文依据*: {f.get('citation')}\n"
            md_content += "\n"

    try:
        # 4. 写入关系型数据库
        wiki_page = WikiPage(
            tenant_id=tenant_id,
            user_id=user_id,
            document_id=document_id,
            title=title,
            summary=summary,
            markdown_content=md_content,
            created_at=datetime.now()
        )
        db.add(wiki_page)
        db.commit()
        db.refresh(wiki_page)
        
        # 保存细化条目 WikiItems 用于单独索引与出处溯源展示
        for c in wiki_data.get("concepts", []):
            db.add(WikiItem(
                wiki_page_id=wiki_page.id,
                category="concept",
                key=c.get("name", "未知"),
                value=c.get("definition", "无"),
                citation=c.get("citation", "")
            ))
        for c in wiki_data.get("clauses", []):
            db.add(WikiItem(
                wiki_page_id=wiki_page.id,
                category="clause",
                key=c.get("title", "未知"),
                value=c.get("content", "无"),
                citation=c.get("citation", "")
            ))
        for f in wiki_data.get("faqs", []):
            db.add(WikiItem(
                wiki_page_id=wiki_page.id,
                category="faq",
                key=f.get("question", "未知"),
                value=f.get("answer", "无"),
                citation=f.get("citation", "")
            ))
        db.commit()
        
        # 5. 虚拟分片灌库（灌入 Chroma 向量和 BM25 库，doc_type="wiki"）
        # 将所有的编译知识项单独序列化为一个 Wiki MD 字符串，方便以 doc_type="wiki" 检索出来
        wiki_ingest_md = f"# Wiki: {title}\n\n"
        wiki_ingest_md += f"## 摘要: {summary}\n\n"
        
        for c in wiki_data.get("concepts", []):
            wiki_ingest_md += f"概念: {c.get('name')}\n定义解释: {c.get('definition')}\n原文出处: {c.get('citation')}\n\n"
        for c in wiki_data.get("clauses", []):
            wiki_ingest_md += f"条款: {c.get('title')}\n条款内容: {c.get('content')}\n原文出处: {c.get('citation')}\n\n"
        for f in wiki_data.get("faqs", []):
            wiki_ingest_md += f"问题: {f.get('question')}\n解答内容: {f.get('answer')}\n原文出处: {f.get('citation')}\n\n"
            
        success = ingest_knowledge(
            md_text=wiki_ingest_md,
            source_filename=orig_filename,
            tenant_id=tenant_id,
            doc_type="wiki"
        )
        if success:
            logger.info("Wiki chunks successfully indexed in Chroma vector store for doc %s", orig_filename)
        else:
            logger.warning("Wiki chunks indexing in Chroma failed, but SQL record was kept.")
            
        return True
    except Exception as e:
        db.rollback()
        logger.exception("Failed to write compiled Wiki to database for document %s: %s", orig_filename, e)
        return False
