<h1 align="center">Enterprise RAG 企业知识库问答系统</h1>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://github.com/langchain-ai/langchain"><img src="https://img.shields.io/badge/LangChain-RAG-orange" alt="LangChain"></a>
  <a href="https://streamlit.io/"><img src="https://img.shields.io/badge/Streamlit-UI-FF4B4B?logo=streamlit&logoColor=white" alt="Streamlit"></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-15%2B-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License"></a>
</p>

基于 **FastAPI + LangChain + ChromaDB + BM25 + Flashrank Rerank + PostgreSQL** 构建的企业知识库问答系统。项目支持文档上传、向量化入库、混合检索、Query Rewriting、Critic Agent 防幻觉、多租户数据隔离、RAGAS 自动评测和 LangSmith Trace。

这个项目定位为“AI 应用开发/后端方向”的工程化 RAG 项目，重点展示从文档入库、检索增强、流式问答、权限隔离到评测观测的完整链路。

![系统界面截图](docs/screenshot.png)

---

## 核心能力

### 1. JWT 登录与多租户权限隔离

系统以 JWT 登录鉴权为主：用户注册/登录后，后端签发 `Authorization: Bearer <JWT>`，并从服务端用户表中解析当前用户的 `tenant_id` 和 `user_id`，再将租户信息注入到文档管理、向量检索、BM25 缓存和历史会话查询中。

`X-API-Key` 仅作为兼容旧版评测脚本和历史演示入口保留，不作为主认证链路。生产化场景应统一收敛到 JWT / Session / 企业 SSO 等认证体系。

```mermaid
sequenceDiagram
    participant Client as Client
    participant Auth as core/auth.py
    participant DB as PostgreSQL
    participant RAG as RAGEngine
    Client->>Auth: Authorization Bearer JWT
    Auth->>DB: 查询 User
    DB-->>Auth: tenant_id / user_id
    Auth->>RAG: 注入租户上下文
    RAG->>RAG: Chroma metadata filter + tenant BM25
    RAG-->>Client: 返回当前租户的数据结果
```

隔离点包括：

- 文档记录表按 `tenant_id` 过滤。
- ChromaDB 写入和检索时带 `tenant_id` metadata。
- BM25 按租户单独持久化为 `bm25_{tenant_id}.pkl`。
- 历史会话列表和详情按 `tenant_id + user_id` 双重过滤。

该实现适合项目演示和实习简历展示；生产环境还需要角色权限、审计日志、密钥轮换、限流和更完整的认证体系。

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

### 6. 模型工厂解耦与私有化部署预留

项目在工程设计上将所有大模型和向量模型调用统一封装在 `core/llm_factory.py` 中，业务节点不直接依赖任何具体模型厂商。

- 默认使用 OpenAI-compatible 接口调用云端模型。
- 通过 `FLASH_MODEL`、`STANDARD_MODEL`、`PLUS_MODEL` 和 `EMBEDDING_MODEL` 区分路由、生成、闲聊和向量模型。
- 如果企业内网模型服务兼容 OpenAI API，例如 vLLM、Ollama OpenAI-compatible API 或 Xinference，通常只需要调整 `BASE_URL`、`OPENAI_API_KEY` 和模型名等环境变量，RAG 检索、权限隔离与可观测性链路无需重写。

---

## 系统流程

```mermaid
graph TD
    A[用户提问] --> B[FastAPI /api/v1/chat]
    B --> Auth[JWT 鉴权与租户识别]
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
| 权限隔离 | JWT, user_id, tenant_id |
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
│   ├── auth.py              # JWT 鉴权、兼容旧版 API Key
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
FLASH_MODEL="glm-4-flash"
STANDARD_MODEL="glm-4"
PLUS_MODEL="glm-4-plus"
EMBEDDING_MODEL="embedding-3"

# 私有化本地模型部署切换示例 (如 vLLM, Ollama, Xinference)
# OPENAI_API_KEY="local_dummy_key"
# BASE_URL="http://localhost:8000/v1"
# FLASH_MODEL="local-fast-model"
# STANDARD_MODEL="local-chat-model"
# PLUS_MODEL="local-chat-model"
# EMBEDDING_MODEL="local-embedding-model"

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

系统已升级为 **统一 SSO 去中心化 JWT Token 鉴权体系**。客户端需要在 Header 中携带 `Authorization: Bearer <JWT_Token>`。

### 1. 统一认证接口
| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | 用户注册 (用户名限制为字母/数字/下划线/连字符 2-50 位) |
| `POST` | `/api/v1/auth/login` | 用户登录 (密码哈希比对并签发 JWT SSO Token) |

### 2. 知识库与聊天接口
| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `POST` | `/api/v1/chat` | 流式 RAG 问答 (屏蔽前端 history 参数，一律后端强制查库) |
| `POST` | `/api/v1/upload` | 隔离上传文档 (UUID 重命名防穿越落盘) |
| `GET` | `/api/v1/list` | 查看当前租户已索引的文档列表 |
| `DELETE` | `/api/v1/clear` | 清空当前租户知识库和所有会话历史 |
| `GET` | `/api/v1/sessions` | 查看当前租户及对应用户的会话列表 |
| `GET` | `/api/v1/history/{session_id}` | 查看指定会话的历史记录 (用户级强隔离) |
| `DELETE` | `/api/v1/history/{session_id}` | 删除指定会话 (含数据库级联删除) |

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

## 🛡️ 安全加固与越权测试审计

为了达到企业级准生产的安全性标准，本项目实施了六大纵深加固防线，能够抵御各类路径穿越、身份假冒与越权注入风险。

### 1. 六大纵深防御防线
- **用户名强格式正则**：注册用户名仅允许 `^[a-zA-Z0-9_-]{2,50}$`，杜绝通过特殊字符造成路径穿越或 SQL 注入。
- **上传物理 UUID 重命名**：物理落盘时剥离目录前缀，采用 `uuid.uuid4().hex` 作为物理文件名，防范恶意穿越覆盖系统敏感文件。
- **用户级历史强隔离**：聊天历史记录的拉取和删除在 SQL 层面绑定 `user_id` 过滤，消除同一租户不同用户对话历史串色风险。
- **屏蔽前端 history 传入**：彻底废除对前端请求体内历史聊天上下文的直接采用，全部由后端从 PostgreSQL 数据库提取，防御对话内容伪造。
- **会话关系物理表硬校验** (Agent 端)：在 Postgres 数据库建立 `agent_sessions` 关系表，每次对话、拉取及删除时均查表强校验归属。
- **文件绝对路径 resolve 校验** (Agent 端)：CSV 物理文件访问时，采用 `Path.resolve().is_relative_to` 精准校验隔离范围，杜绝 `../` 回退绕过。

### 2. 自动化越权渗透测试脚本
项目在仓库内置了一键自动化集成渗透测试脚本：`scripts/test_security.py`。该脚本可自动对上述漏洞防线发起模拟渗透攻击：
- **运行测试**：
  ```bash
  python scripts/test_security.py
  ```
- **越权测试机制**：
  1. 尝试以非法字符/路径符号注册用户，检验**格式校验器阻断率**；
  2. 尝试以上传包含 `../../` 的恶意文件，检验**上传文件物理名净化及重命名存盘**；
  3. 用户 B 尝试调用 API 强行获取用户 A 的 `session_id` 对话历史，检验**数据库用户级强隔离**；
  4. 用户 B 假冒用户 A 的 thread_id 前缀或跨越其 uploads 隔离目录（`../`）读取文件，检验 **Postgres 关系表拦截率** 与 **Path.resolve 路径隔离阻断率**。

---

## 安全与上传说明

- `.env`、`data/`、`.venv/`、`__pycache__/` 等目录已在 `.gitignore` 中忽略。
- 上传 GitHub 前请确认没有提交真实 API Key、数据库密码或私有文档。
- 本项目已全面升级为去中心化 JWT SSO 认证的多维度隔离架构，为企业生产级多租户开发提供了标准工业界设计思路。
