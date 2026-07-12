# 企业 RAG / 混合双路检索重构任务清单 (RAG_Task.md)

本任务清单记录了本次将 RAG 升级为 **“混合检索（Hybrid Retrieval）—— 两路数据并流”** 核心特性的技术改造细节与完成进度。

## 任务进度一览

- [x] **后端：混合检索两路并流核心逻辑实现**
  - [x] 重构 `stream_rag_answer` 异步生成器，废弃过时单路 RAG 与 WIKI 判断。
  - [x] 底层并发发起双路检索（Chroma 物理切片检索 + PostgreSQL WikiItem 模糊匹配）。
  - [x] 上下文 Context 拼接并流喂给 LLM。
  - [x] 流式生成尾端以 `__METADATA_START__` 与 `__METADATA_END__` 协议传递 `chunks` 及 `wiki_items` 元数据负载。
- [x] **后端：运行时 AttributeError 致命异常修补**
  - [x] 修复 `RAGEngine` 类与全局 `stream_rag_answer` 方法声明的断层冲突。
  - [x] 成功通过 16 个 pytest 单元测试（100% 绿色通过率）。
- [x] **前端：多会话状态独立与零感知 Wiki 知识卡片平铺渲染**
  - [x] 废弃 `searchMode` React 状态，前端对检索模式零感知，自适应渲染。
  - [x] 重构 SSE 解析与会话切换状态，使各条 assistant 消息在落库和渲染时完全剥离 citations 和 wikiItems。
  - [x] 重构 React `expandedCitations` 折叠 Map，使得每条历史消息的引用卡片折叠完全独立控制，消除相互干扰。
  - [x] 精心绘制并排版 WikiItems（核心概念、合规条款、典型问答）的精致矢量卡片，提升产品体验与演示表现力。
- [x] **前端：清理废弃的手动检索药丸组件**
  - [x] 彻底删除欢迎界面底部的检索模式切换按钮组（RAG vs Wiki）。
  - [x] 彻底删除对话输入区域上方的检索模式切换按钮组（RAG vs Wiki）。
- [x] **部署与验证**
  - [x] 更新 `README.md`，升级混合检索架构、Mermaid 数据流图、API 细节与简历亮点。
  - [x] 代码安全入库提交并推送 GitHub 远程仓库（分支 `main`）。
  - [x] SSH 远程腾讯云主机 `106.54.234.136` 并成功拉取最新代码，一键热重启后端并成功上线。

- [ ] **代码审查缺陷修复 (Code Review Fixes)**
  - [x] **P0 (致命)**: 恢复 `stream_rag_answer` 缺失的安全拦截、闲聊分流、问题改写及前置变量初始化。
  - [x] **P1 (严重)**: 补全前端 `wiki_items` 矢量卡片平铺渲染与 `expandedCitations` 独立会话展开 Map 交互逻辑。
  - [x] **P2 (严重)**: 清理 `chat_routes.py` 等文件中对已废弃 `search_mode` 传参及配置声明的残留。
  - [x] **P3 (重要)**: 优化混合检索闲聊分类下的直通兜底以及 WikiItem 的匹配评分过滤算法。
  - [x] **登录身份误判 Bug 修复**: 正式用户登录时未清空上一轮访客生命周期状态，导致身份错乱的严重安全 Bug（已完成前端 `updateVisitorLifecycleCache` 重构）。

---

## 核心改造文件列表
1. 后端引擎层：[rag_engine.py](file:///d:/Rag/Enterprise_RAG/core/rag_engine.py) (重构双路并流与修复定义断层)
2. 前端视图层：[App.jsx](file:///d:/Rag/Enterprise_RAG/frontend/src/App.jsx) (删除药丸切换、精美卡片渲染与多会话折叠防污染)
3. 项目说明：[README.md](file:///d:/Rag/Enterprise_RAG/README.md) (升级说明文档)
