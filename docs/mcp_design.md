# Enterprise RAG MCP (Model Context Protocol) 接口层设计文档

MCP 是由 Anthropic 提出的一项标准通信协议，它允许 AI 客户端（如 Cursor、Claude Desktop 等）以标准化的方式发现并调用外部工具。本项目通过实现一个轻量级的 stdio MCP 代理服务，将企业 RAG 知识检索层的核心能力平滑暴露给开发人员的 IDE Agent。

---

## 🏗️ 整体架构设计

```
[ Cursor / Claude Desktop ] (IDE 客户端)
          │
          │ (启动并监听标准输入输出)
          ▼
[ mcp_server/server.py ] (stdio MCP 代理)
          │
          │ (通过环境变量 RAG_JWT_TOKEN 与 RAG_BASE_URL)
          ▼ (发送 HTTP 协议请求)
[ FastAPI Backend /api/v1/tools/* ] (RAG 核心服务)
```

1. **轻量与隔离**：MCP 运行在开发者的个人工作机上，不需要直接连接 ChromaDB 或 PostgreSQL 数据库，而是作为 API 客户端，将请求转发给后端的 FastAPI 服务。这保持了清晰的架构分层，并复用了后端成熟的 JWT 权限校验逻辑。
2. **高兼容双模启动**：
   - 如果运行环境中安装了官方的 `mcp` Python SDK，则使用 SDK 跑 stdio 通信。
   - 如果运行环境没有 `mcp` SDK，服务器将自动激活降级机制，采用纯 Python 实现的标准 JSON-RPC 2.0 stdio 解析流。**即使没有装任何第三方库，Cursor 也能够顺利拉起！**

---

## 🛠️ MCP Tools Schema 定义

MCP 服务器对外暴露 4 个核心检索与分析工具：

### 1. `search_documents`
* **说明**：检索当前租户关联的手册和文档分片（Chunks），带有相关度打分（RRF）和元数据。
* **参数**：
  - `query` (string, 必填)：检索的问题或词。
  - `top_k` (integer, 可选，默认 5)：最大返回分片数。

### 2. `get_document_detail`
* **说明**：查看指定 ID 的文档详情，检查当前角色的访问权限。
* **参数**：
  - `doc_id` (integer, 必填)：文档在数据库中的自增 ID。

### 3. `answer_with_citations`
* **说明**：非流式 RAG 问答，返回大模型整合检索资料后的最终回答，并明确指出每个事实的引用分片来源。
* **参数**：
  - `question` (string, 必填)：向知识库提出的问题。
  - `session_id` (string, 可选)：进行连续追问时关联的会话 ID。

### 4. `list_documents`
* **说明**：列表展示当前租户下已入库的全部企业文档。
* **参数**：
  - `page` (integer, 可选)：页码。
  - `page_size` (integer, 可选)：每页条数。

---

## 🔑 权限隔离与安全审计

- **不信任前端**：MCP 转发请求时，必须在 HTTP Header 中附带 `Authorization: Bearer <RAG_JWT_TOKEN>`。后端在拦截器中解析该 Token，拒绝接受前端/客户端伪造的 `tenant_id` 和 `user_id`。
- **越权防御**：如果 IDE Agent 试图调用他人租户的 `doc_id`，后端将抛出 `403 Forbidden`，MCP 友好捕获并返回包含“无权限访问该文档”的 JSON-RPC 错误，保护知识隔离边界。
- **拒答熔断**：当 IDE Agent 提问无答案的问题时，后端前置 Critic 触发安全拦截，回答将明确标识“未在知识库中找到相关信息”，防止 Agent 误用有幻觉的生成结果。

---

## 🚀 Cursor & Claude Desktop 挂载指南

### 1. 挂载到 Cursor
打开 Cursor，依次进入 `Settings` -> `Features` -> `MCP`，点击 `+ Add New MCP Server`：

- **Name**：`Enterprise-RAG-MCP`
- **Type**：`command`
- **Command**：
  ```bash
  python d:/Rag/Enterprise_RAG/mcp_server/server.py
  ```
- **环境变量 (Environment Variables)**：
  - `RAG_BASE_URL` = `http://localhost:8010/api/v1/tools`
  - `RAG_JWT_TOKEN` = `您的JWT身份令牌`

点击 `Save` 后，Cursor 会通过标准输入输出拉起服务，当状态灯显示为绿色（`Connected`）即说明成功挂载。您在 Cursor Composer 或 Chat 中可以使用 `@Enterprise-RAG-MCP` 或是直接询问它“检索系统里的促销优惠”来激发 Agent 调用该工具。

### 2. 挂载到 Claude Desktop
打开您的 Claude 配置文件（在 Windows 下一般位于 `C:\Users\<用户名>\AppData\Roaming\Claude\claude_desktop_config.json`），加入如下配置：

```json
{
  "mcpServers": {
    "enterprise_rag": {
      "command": "python",
      "args": [
        "d:/Rag/Enterprise_RAG/mcp_server/server.py"
      ],
      "env": {
        "RAG_BASE_URL": "http://localhost:8010/api/v1/tools",
        "RAG_JWT_TOKEN": "您的JWT身份令牌"
      }
    }
  }
}
```

配置完成后重启 Claude Desktop，在聊天界面右下角将能看到螺丝刀的“工具”图标，点击即可验证挂载。
