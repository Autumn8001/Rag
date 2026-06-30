# Task List - Phase 6.0: Thinking Pipeline (Enterprise_RAG_Task.md)

- `[x]` Phase 2.2: Workspace Visual Polish Complete (主控制台视觉打磨完成)
- `[x]` Phase 3.0: 登录页左侧 Brand Panel 视觉与品牌化重构 (像素级还原 Figma)
- `[x]` Phase 4.0: Sprint 1 Design System Polish (UI 像素级细节精细打磨)
  - `[x]` 1. 统一 Workspace 核心组件最大宽度为 800px 并形成垂直切线
  - `[x]` 2. 开启并优化全局 Transition 动效 (all 0.2s cubic-bezier(0.4, 0, 0.2, 1))
  - `[x]` 3. 弱化开发模式下各卡片的视觉权重 (改浅背景，稀释描边，饱和度降为 10B981)
  - `[x]` 4. 紧凑化开发面板模块垂直间距为 16px，各卡片 padding 为 16px
  - `[x]` 5. 限制 Trace Pipeline 与 Chunks 列表最大高度，实行内部局部滚动，避免右面板整体长滚
  - `[x]` 6. 统一 Workspace 元素圆角与投影 (按钮 10px, 卡片 12px, 输入框 16px, 单层微影)
  - `[x]` 7. 确保 Shift + Enter 换行提示与发送按钮保持至少 16px 的水平 Gap
  - `[x]` 8. 弱化三栏物理分割线颜色至 rgba(0, 0, 0, 0.04)
  - `[x]` 9. 执行 npm run build 静态构建编译校验并通过浏览器人工校验

- `[x]` Phase 5.0: Model Prompt Translation & Resizable Collapsible Sidebar (提示词汉化与折叠拖拽拉伸)
  - `[x]` 1. 汉化 `core/rag_engine.py` 中的五个核心大模型系统提示词与溯源参考文字 [MODIFY] [rag_engine.py](file:///d:/Rag/Enterprise_RAG/core/rag_engine.py)
  - `[x]` 2. 删除前端 `App.jsx` 中的 ThumbsUp / ThumbsDown 点赞点踩图标引用和反馈按钮 [MODIFY] [App.jsx](file:///d:/Rag/Enterprise_RAG/frontend/src/App.jsx)
  - `[x]` 3. 在 `App.jsx` 中加入 `sidebarWidth` / `rightPanelWidth` 状态与 `onMouseDown` 拖拽拉伸逻辑 [MODIFY] [App.jsx](file:///d:/Rag/Enterprise_RAG/frontend/src/App.jsx)
  - `[x]` 4. 在 `App.jsx` 中增加左右侧边栏隐藏折叠（Collapse）按钮及优雅悬浮展开按钮 [MODIFY] [App.jsx](file:///d:/Rag/Enterprise_RAG/frontend/src/App.jsx)
  - `[x]` 5. 在 `App.css` 中添加拖拽手柄、毛玻璃悬浮按钮及折叠宽度过渡样式 [MODIFY] [App.css](file:///d:/Rag/Enterprise_RAG/frontend/src/App.css)
  - `[x]` 6. 运行静态编译与浏览器校验，确保拖拽流畅、中文提示词逻辑完备

- `[x]` Phase 6.0: Thinking Pipeline (思考流水线卡片动效与 SSE 同步)
  - `[x]` 1. 修改 `core/rag_engine.py` 在 RAG 执行的各阶段 yield 步骤标记 [MODIFY] [rag_engine.py](file:///d:/Rag/Enterprise_RAG/core/rag_engine.py)
  - `[x]` 2. 修改 `api/chat_routes.py` 过滤掉历史记录中的步骤标记 [MODIFY] [chat_routes.py](file:///d:/Rag/Enterprise_RAG/api/chat_routes.py)
  - `[x]` 3. 修改 `App.jsx` 增加步骤驱动逻辑、过滤步骤标记、在流式阶段渲染 Thinking Card [MODIFY] [App.jsx](file:///d:/Rag/Enterprise_RAG/frontend/src/App.jsx)
  - `[x]` 4. 修改 `App.css` 增加 Thinking Card 整体样式、步骤节点及脉冲和淡出动效 [MODIFY] [App.css](file:///d:/Rag/Enterprise_RAG/frontend/src/App.css)
  - `[x]` 5. 进行全量编译打包校验与人工交互流程测试

- `[x]` Phase 6.1: Thinking Pipeline Localization, Prompt Tuning, Compact Citations, Hover Previews, and Scrolling Fix
  - `[x]` 1. 优化后端模型回答与汉化 (`core/rag_engine.py`)
  - `[x]` 2. 修复前端布局滚动 Bug 与 Thinking 步骤汉化 (`frontend/src/App.jsx`)
  - `[x]` 3. 精修前端样式并支持 Hover 悬浮预览 (`frontend/src/App.css`)
  - `[x]` 4. 编译构建与浏览器人工测试校验

- `[x]` Phase 6.2: AI Reply Optimization, Collapsible Light Citation List, and Sidebar Chunk Preview
  - `[x]` 1. 调优后端系统提示词与回复结构 (`core/rag_engine.py`)
  - `[x]` 2. 前端引入折叠状态与消息 Markdown 块级渲染 (`frontend/src/App.jsx`)
  - `[x]` 3. 实现极简轻量 List 并绑定右侧抽屉预览 (`frontend/src/App.jsx`)
  - `[x]` 4. 进行编译构建校验及浏览器端人工交互验证
