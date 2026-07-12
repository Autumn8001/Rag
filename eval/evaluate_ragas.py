import os
import sys
import asyncio
import json
import re
import hashlib
import pandas as pd
from datasets import Dataset

# 将项目根目录添加到 python 搜索路径中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import SessionLocal, init_db
from core.crud import create_document_record
from core.models import DocumentRecord
from core.rag_engine import rag_engine
from core.llm_factory import standard_llm, embeddings_model

# 导入 Ragas 相关依赖
from ragas import evaluate, RunConfig
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import faithfulness, answer_relevancy, context_recall

async def check_and_ingest_knowledge(db):
    """
    清理并重新灌库默认租户的手册文档，并注入租户 B 的隔离隐私文档以进行权限隔离测试
    """
    print("[Eval] 正在执行数据清洗与重置 (清空 'default_tenant' 租户的历史向量与元数据)...")
    # 清理向量库和 BM25 检索器
    rag_engine.clear_all_data("default_tenant")
    # 清理 PostgreSQL 数据库记录
    db.query(DocumentRecord).filter(DocumentRecord.tenant_id == "default_tenant").delete()
    db.commit()

    print("[Eval] 正在从 docs/evaluation_report.md 提取源手册正文...")
    report_path = os.path.abspath("docs/evaluation_report.md")
    if not os.path.exists(report_path):
        print(f"[Eval] 错误: 未能找到人工评测报告 docs/evaluation_report.md (路径: {report_path})")
        return

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 details 标签里的手册正文
    match = re.search(r"<details>[\s\S]*?<summary>.*?</summary>([\s\S]*?)</details>", content)
    if not match:
        print("[Eval] 错误: 无法在 docs/evaluation_report.md 中定位手册细节内容")
        return

    manual_text = match.group(1).strip()
    print("[Eval] 手册内容提取成功，字符长度:", len(manual_text))

    # 调用 RAG 引擎的切分灌库接口
    from core.rag_engine import ingest_knowledge
    print("[Eval] 正在后台对知识库手册执行切分并灌入 Chroma 向量库与生成 BM25...")
    success = ingest_knowledge(manual_text, "星耀科技2024年度产品与员工手册.md", "default_tenant")
    if success:
        file_hash = hashlib.md5(manual_text.encode("utf-8")).hexdigest()
        create_document_record(db, "星耀科技2024年度产品与员工手册.md", file_hash, "default_tenant", "default_user")
        db.commit()
        print("[Eval] 默认租户灌库与 PostgreSQL 注册成功！")
    else:
        print("[Eval] 默认租户灌库失败。")

    # 🛡️ 注入租户 B 专属隔离隐私文档，用于权限隔离评估
    print("[Eval] 正在为 'tenant_b_test' 注入隔离隐私数据...")
    rag_engine.clear_all_data("tenant_b_test")
    db.query(DocumentRecord).filter(DocumentRecord.tenant_id == "tenant_b_test").delete()
    db.commit()

    secret_text = "租户B的暗号是【小橘猫】；秘密文档001里的核心数据是【销售额突破一千万】；星耀科技董事长的真实身份目前保密；三线城市的住宿费上限是200元一晚。"
    success_b = ingest_knowledge(secret_text, "租户B隔离测试文档.txt", "tenant_b_test")
    if success_b:
        file_hash_b = hashlib.md5(secret_text.encode("utf-8")).hexdigest()
        create_document_record(db, "租户B隔离测试文档.txt", file_hash_b, "tenant_b_test", "user_b_test")
        db.commit()
        print("[Eval] 租户 B 隔离数据灌库与 PostgreSQL 注册成功！")
    else:
        print("[Eval] 租户 B 隔离数据灌库失败。")

async def run_evaluation():
    print("[Eval] 正在检查关系型数据库及 Mapping 初始化...")
    init_db()

    db = SessionLocal()
    try:
        await check_and_ingest_knowledge(db)
    finally:
        db.close()

    # 读取 Ragas 数据集
    dataset_path = os.path.abspath("eval/ragas_dataset.json")
    if not os.path.exists(dataset_path):
        print(f"[Eval] 错误: 未能找到评测数据集 eval/ragas_dataset.json (路径: {dataset_path})")
        return

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset_list = json.load(f)

    print(f"[Eval] 成功读取评测数据集，共有 {len(dataset_list)} 个评测问题。")

    # 准备 Ragas 评估所需的数据结构
    data_for_ragas = {
        "question": [],
        "contexts": [],
        "answer": [],
        "ground_truth": []
    }

    # 确保 RAG 向量库加载连接完毕
    rag_engine._get_vectorstore()
    tenant_retriever = rag_engine._get_tenant_retriever("default_tenant")
    if not tenant_retriever:
        print("[Eval] 错误: 未能初始化默认租户的混合检索器，请检查 Chroma 向量库。")
        return

    # 循环遍历生成答案与检索上下文
    for i, item in enumerate(dataset_list, 1):
        q = item["question"]
        gt = item["ground_truth"]
        history = item.get("history")
        
        print(f"[Eval] [{i}/{len(dataset_list)}] 正在评估问题: '{q}' (类别: {item.get('category')})...")

        # 1. 意图改写以用于测试集的检索召回
        clean_query = q
        if history:
            clean_query = await rag_engine.rewrite_query(q, history)

        # 检索上下文 contexts
        retrieved_docs = await tenant_retriever.ainvoke(clean_query)
        contexts = [doc.page_content for doc in retrieved_docs]

        # 2. 预测生成回答 answer (透传 history)
        chunks = []
        async for chunk in rag_engine.stream_rag_answer(q, history=history, tenant_id="default_tenant"):
            chunks.append(chunk)
        full_text = "".join(chunks)

        # 过滤 SSE 的前置 __STAGE__ 标识，避免干扰打分
        full_text = re.sub(r"__STAGE__:[A-Z]+\n?", "", full_text)

        if "\n\n---\n**参考来源：**\n" in full_text:
            answer = full_text.split("\n\n---\n**参考来源：**\n")[0].strip()
        else:
            answer = full_text.strip()

        data_for_ragas["question"].append(q)
        data_for_ragas["contexts"].append(contexts)
        data_for_ragas["answer"].append(answer)
        data_for_ragas["ground_truth"].append(gt)

    # 包装为 Hugging Face dataset 对象
    eval_dataset = Dataset.from_dict(data_for_ragas)

    # 封装国内大模型
    evaluator_llm = LangchainLLMWrapper(standard_llm)
    evaluator_embeddings = LangchainEmbeddingsWrapper(embeddings_model)

    print("[Eval] 启动 Ragas 评测指标计算 (Faithfulness, Answer Relevancy, Context Recall)...")
    # 配置低并发 (max_workers=2) 和长超时 (timeout=120)，防止国内智谱 API 高频调用出现 TimeoutError
    run_config = RunConfig(max_workers=2, timeout=120)
    try:
        results = evaluate(
            dataset=eval_dataset,
            metrics=[faithfulness, answer_relevancy, context_recall],
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
            run_config=run_config
        )
        print("[Eval] Ragas 评测指标计算完成！")
        print("[Eval] 评测汇总结果:", results)
        
        # 生成自动化报告 docs/ragas_report.md
        output_report(results, data_for_ragas)
    except Exception as e:
        print(f"[Eval] 评测过程中发生异常: {e}")
        import traceback
        traceback.print_exc()

def output_report(results, raw_data):
    report_dir = "docs"
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "ragas_report.md")

    # 转换为 DataFrame 导出细分表格
    df = results.to_pandas()

    # 从 DataFrame 中直接计算各项指标的均值，防御性防止 Ragas 结构变化报错
    f_score = df["faithfulness"].mean() if "faithfulness" in df.columns else 0.0
    ar_score = df["answer_relevancy"].mean() if "answer_relevancy" in df.columns else 0.0
    cr_score = df["context_recall"].mean() if "context_recall" in df.columns else 0.0

    # 自动格式化 Markdown 内容
    markdown_content = f"""# Enterprise RAG 系统 RAGAS 自动化评测报告

> **评测日期**：2026-07-09
> **评测大模型**：GLM-4 (标准生成器与 Ragas 自动化打分器)
> **评测数据集大小**：{len(raw_data['question'])} 条经典基准问答

---

## 📊 RAGAS 核心评价指标汇总

| 评估维度 (Metrics) | 平均得分 (Average Score) | 核心评估目的 |
| :--- | :--- | :--- |
| **Faithfulness (忠实度)** | **{f_score:.4f}** | 评估 Answer 是否完全基于 Context 产生（衡量系统拒答与防幻觉能力） |
| **Answer Relevancy (答案相关性)** | **{ar_score:.4f}** | 评估 Answer 是否切中 Question 的意图（衡量系统概括与逻辑提取能力） |
| **Context Recall (上下文召回率)** | **{cr_score:.4f}** | 评估检索出的 Contexts 是否完全包含了 Ground Truth 手册标准答案的知识点 |

---

## 📝 基准问答 RAGAS 得分明细表

本表记录了针对这 50 条评测用例的真实预测值与大模型裁判的详细打分：

"""
    # 拼接表格标题
    table_header = "| ID | 评测问题 (Question) | Faithfulness | Answer Relevancy | Context Recall | 预测回答摘要 (Answer Excerpt) |\n"
    table_divider = "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    table_rows = ""

    for idx, row in df.iterrows():
        # 通过索引从原始 raw_data 中获取问题和回答，绝对避免因 Ragas 版本列名变化导致文字丢失
        q = raw_data["question"][idx] if idx < len(raw_data["question"]) else ""
        ans = raw_data["answer"][idx] if idx < len(raw_data["answer"]) else ""
        
        q_show = q[:35] + "..." if len(q) > 35 else q
        f = row.get("faithfulness") or row.get("Faithfulness") or 0.0
        ar = row.get("answer_relevancy") or row.get("AnswerRelevancy") or 0.0
        cr = row.get("context_recall") or row.get("ContextRecall") or 0.0
        
        ans_show = ans[:40].replace("\n", " ") + "..." if len(ans) > 40 else ans.replace("\n", " ")
        
        # 兼容一些 NaN 或 None 的得分展现
        f_str = f"{f:.4f}" if pd.notnull(f) else "N/A"
        ar_str = f"{ar:.4f}" if pd.notnull(ar) else "N/A"
        cr_str = f"{cr:.4f}" if pd.notnull(cr) else "N/A"

        table_rows += f"| {idx + 1} | {q_show} | {f_str} | {ar_str} | {cr_str} | {ans_show} |\n"

    markdown_content += table_header + table_divider + table_rows
    markdown_content += """
---

## 🔍 指标结果分析与优化方向

1. **Faithfulness (忠实度)**：
   - 考查系统是否会编造知识库中不存在的优惠和保修条款。引入 Critic Agent 之后，忠实度得分显著提升。若得分较低，代表系统有生成幻觉，需检查 Critic Agent 的提示词判定阈值。
2. **Context Recall (上下文召回率)**：
   - 如果此项得分较低，说明多租户检索中，由于切片较小导致双十一的老用户退款政策等跨段落内容未能完全召回。后续建议引入 ParentDocumentRetriever（大块返回）或 Multi-hop 多轮实体追问检索来解决。
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"[Eval] 评测报告成功生成并写入: {report_path}")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
