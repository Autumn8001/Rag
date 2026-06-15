# Enterprise RAG 企业知识库问答系统

基于 **FastAPI + LangChain + ChromaDB + BM25 + Flashrank Rerank + PostgreSQL** 构建的企业知识库问答系统。项目支持文档上传、向量化入库、混合检索、Query Rewriting、Critic Agent 防幻觉、多租户数据隔离、RAGAS 自动评测和 LangSmith Trace。

这个项目定位为“AI 应用开发/后端方向”的工程化 RAG 项目，重点展示从文档入库、检索增强、流式问答、权限隔离到评测观测的完整链路。

![系统界面截图](docs/screenshot.png)

---

## 核心能力

### 1. API Key 映射的多租户隔离

系统通过 `X-API-Key` 请求头识别用户身份，后端在 PostgreSQL 的 `api_key_maps` 表中查询对应的 `tenant_id` 和 `user_id`，再将租户信息注入到文档管理、向量检索、BM25 缓存和历史会话查询中。

```mermaid
sequenceDiagram
    participant Client as Client
    participant Auth as core/auth.py
    participant DB as PostgreSQL
    participant RAG as RAGEngine
    Client->>Auth: X-API-Key
    Auth->>DB: 查询 APIKeyMap
    DB-->>Auth: tenant_id / user_id
    Auth->>RAG: 注入租户上下文
    RAG->>RAG: Chroma metadata filter + tenant BM25
    RAG-->>Client: 返回当前租户的数据结果
```

隔离点包括：

- 文档记录表按 `tenant_id` 过滤。
- ChromaDB 写入和检索时带 `tenant_id` metadata。
- BM25 按租户单独持久化为 `bm25_{tenant_id}.pkl`。
- 历史会话列表和详情按 `tenant_id` 查询。

该实现适合项目演示和实习简历展示；生产环境还需要密钥哈希、过期时间、权限角色、审计日志和更完整的认证体系。

### 2. 混合检索与重排序

```text
用户问题
  -> Query Rewriting
  -> ChromaDB 向量检索 + BM25 关键词检索
  -> EnsembleRetriever 加权融合
  -> FlashrankRerank 精排
  -> Top-K 上下文
  -> Critic Agent 相关性判断
  -> LLM 流式生成答案
```

设计目的：

- 向量检索负责语义相似召回。
- BM25 负责关键词、产品名、政策名等精确匹配。
- Rerank 对候选片段重新排序，减少低相关上下文进入生成阶段。
- Query Rewriting 用于多轮对话中消除“它、这个、刚才那个”等指代。

### 3. Critic Agent 防幻觉

在最终生成前，系统使用轻量模型判断检索上下文是否与问题相关、是否包含可用于回答的证据。若上下文完全无关，则直接拒答，降低模型在知识库无依据时编造答案的概率。

后续优化中，Critic Prompt 从“资料是否已经包含完整答案”调整为“资料是否包含回答所需证据”，使计算题、条件判断题和“文档未提及”类问题不再被过度拒答。

### 4. 流式响应与历史会话

后端使用 FastAPI 返回 `StreamingResponse`，将模型输出以 SSE 形式逐步推送给前端。对话结束后，系统将完整问答保存到 PostgreSQL，支持按会话查看历史记录。

当前实现中，LLM 和检索链路使用异步调用；部分 SQLAlchemy 数据库操作仍是同步 ORM 查询，适合本地演示和中小规模项目。

### 5. RAGAS 评测与 LangSmith Trace

项目内置 15 条评测集，覆盖基础事实抽取、条件过滤、数值计算、跨段落综合和拒答防幻觉。评测方式包括人工评测和 RAGAS 自动化评测。

项目还通过 `@traceable` 接入 LangSmith，用于观察 RAG 主链路、意图路由、Query Rewrite、Critic 评估和知识入库过程。

### 6. 模型工厂解耦与平滑私有化切换

项目在工程设计上将所有大模型和向量模型调用统一封装在 `core/llm_factory.py` 中，业务节点不直接依赖任何具体模型厂商。
- **云端与私有化一键切换**：系统支持标准的 OpenAI-compatible 接口。在实际企业落地部署时，仅需在环境变量中修改 `BASE_URL` 和 `OPENAI_API_KEY`，即可一键将云端模型平滑切换为企业内网私有化部署的模型服务（如 vLLM、Ollama、Xinference 等），而底层的 RAG 检索、Agent 流程编排、多租户隔离与可观测性链路完全无需做任何代码级修改。

---

## 系统流程

```mermaid
graph TD
    A[用户提问] --> B[FastAPI /api/v1/chat]
    B --> Auth[API Key 鉴权与租户识别]
    Auth --> C{语义路由}
    C -->|知识库问题| D[Query Rewriting]
    C -->|闲聊/无关问题| E[轻量模型直接回复]
    D --> F[ChromaDB 向量检索]
    D --> G[BM25 关键词检索]
    F --> H[Ensemble 融合]
    G --> H
    H --> I[Flashrank Rerank]
    I --> J{Critic Agent}
    J -->|证据相关| K[LLM 流式生成]
    J -->|资料无关| L[安全拒答]
    K --> M[返回答案与来源]
    E --> M
    L --> M
```

---

## 技术栈

| 模块 | 技术 |
| :--- | :--- |
| 后端服务 | FastAPI, StreamingResponse, SSE |
| RAG 框架 | LangChain |
| 向量库 | ChromaDB |
| 关键词检索 | BM25Retriever |
| 结果重排 | FlashrankRerank |
| 关系型数据库 | PostgreSQL, SQLAlchemy |
| 权限隔离 | API Key, tenant_id |
| 评测 | RAGAS, 自定义 15 问测试集 |
| 可观测性 | LangSmith Trace |
| 前端 | Streamlit |
| 部署 | Docker Compose |
| 依赖管理 | uv |

---

## 项目结构

```text
Enterprise_RAG/
├── api/
│   ├── chat_routes.py       # 流式问答、历史会话接口
│   └── admin_routes.py      # 文档上传、列表、清空接口
├── core/
│   ├── auth.py              # API Key 鉴权与租户识别
│   ├── config.py            # 环境变量配置与 LangSmith 环境同步
│   ├── crud.py              # 数据库 CRUD
│   ├── database.py          # SQLAlchemy 连接与初始化
│   ├── llm_factory.py       # 模型工厂
│   ├── models.py            # ORM 模型
│   └── rag_engine.py        # RAG 检索生成主流程
├── eval/
│   ├── ragas_dataset.json   # RAGAS 评测数据集
│   └── evaluate_ragas.py    # 自动化评测脚本
├── docs/
│   ├── evaluation_report.md # 人工评测报告
│   ├── ragas_report.md      # RAGAS 自动化评测报告
│   └── screenshot.png       # 项目界面截图
├── docker-compose.yml
├── main.py
├── web_app.py
├── pyproject.toml
└── .env.example
```

---

## 快速启动

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

示例配置：

```env
# 云端大模型 (以智谱 GLM 为例)
OPENAI_API_KEY="your_api_key_here"
BASE_URL="https://open.bigmodel.cn/api/paas/v4"

# 私有化本地模型部署切换示例 (如 vLLM, Ollama, Xinference)
# OPENAI_API_KEY="local_dummy_key"
# BASE_URL="http://localhost:8000/v1"

DATABASE_URL="postgresql://postgres:postgres@localhost:5432/enterprise_rag"

# LangSmith 可选
LANGSMITH_TRACING=true
LANGSMITH_API_KEY="your_langsmith_api_key"
LANGSMITH_PROJECT="enterprise-rag"
```

### 3. 启动服务

Docker Compose 一键启动：

```bash
docker compose up --build -d
```

或本地分步启动：

```bash
docker compose up -d db
uvicorn main:app --reload --port 8000
streamlit run web_app.py
```

访问地址：

| 服务 | 地址 |
| :--- | :--- |
| 前端 | http://localhost:8501 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

---

## API 概览

业务接口需要携带 `X-API-Key` 请求头。系统初始化时会写入演示用 Key：

- `key_company_a`：绑定 `tenant_company_A`。
- `key_company_b`：绑定 `tenant_company_B`。
- `key_default`：绑定 `default_tenant`。

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `POST` | `/api/v1/chat` | 流式 RAG 问答 |
| `POST` | `/api/v1/upload` | 上传并索引文档 |
| `GET` | `/api/v1/list` | 查看当前租户文档列表 |
| `DELETE` | `/api/v1/clear` | 清空当前租户知识库和历史 |
| `GET` | `/api/v1/sessions` | 查看当前租户会话列表 |
| `GET` | `/api/v1/history/{session_id}` | 查看指定会话历史 |
| `DELETE` | `/api/v1/history/{session_id}` | 删除指定会话 |

---

## 评测结果

### 人工评测

基于《星耀科技 2024 年度产品与员工手册》构建 15 条压力测试，覆盖基础抽取、条件过滤、数值计算、跨段落综合和拒答防幻觉。

- 初始版本：11 / 15，准确率 73.3%。
- 优化后：13 / 15，准确率 86.7%。

完整报告见：[docs/evaluation_report.md](docs/evaluation_report.md)

### RAGAS 自动评测

RAGAS 评测用于观察回答忠实度、答案相关性和上下文召回率。优化 Critic Prompt 和检索参数后，报告显示：

| 指标 | 优化前 | 优化后 |
| :--- | :---: | :---: |
| Faithfulness | 0.5426 | 0.6767 |
| Answer Relevancy | 0.2647 | 0.3590 |
| Context Recall | 1.0000 | 0.9333 |

完整报告见：[docs/ragas_report.md](docs/ragas_report.md)

这些分数不代表系统已经达到生产级准确率，而是用于展示如何通过评测发现问题并迭代 RAG 链路。

---

## 安全与上传说明

- `.env`、`data/`、`.venv/`、`__pycache__/` 等目录已在 `.gitignore` 中忽略。
- 上传 GitHub 前请确认没有提交真实 API Key、数据库密码或私有文档。
- 本项目的 API Key 隔离用于演示多租户思路，生产环境应增加密钥哈希、权限角色、审计日志和密钥轮换机制。
