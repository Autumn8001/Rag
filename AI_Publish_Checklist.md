# 🚀 GitHub 源码上传终极安全与整理核对清单 (AI_Publish_Checklist)

本清单用于协助您在将 `Enterprise_RAG` 与 `DataViz_Agent` 上传至 GitHub 前，进行最后的安全性防御、脏数据清理及代码整理，以确保仓库整洁专业，同时杜绝敏感密钥泄漏。

---

## 🔒 1. 核心安全核对清单 (防泄漏)

在执行 `git push` 前，请务必确认以下敏感文件已**被 Git 排除**（均已写入 `.gitignore` 中）：
*   [ ] **`.env` 配置文件**：包含您的真实 OpenAI/智谱 API 密钥与数据库连接串，**绝对不能**上传。
*   [ ] **`data/` 目录**：包含本地测试上传的 PDF/Excel 企业文档以及本地导出的 Chroma 向量数据。
*   [ ] **数据库持久化文件**：包括 SQLite 数据库文件（如 `*.db`）及 BM25 序列化缓存（如 `*.pkl`）。

> **💡 双保险提示**：在提交时，请**避免**使用 `git add -f` (强制添加) 命令，防止绕过 `.gitignore` 将敏感文件提交。如果不小心提交了密钥，请立即在云服务后台吊销 API 密钥。

---

## 🧹 2. 本地临时缓存与脏数据清理

在上传前，建议您在终端中运行以下命令，清理项目内因开发测试产生的 `__pycache__` 编译缓存与临时输出，以减小体积并保持目录纯净：

```powershell
# 清除 Python 编译缓存 (在两个项目根目录下分别执行)
Get-ChildItem -Path . -Filter "__pycache__" -Recurse | Remove-Item -Force -Recurse
Get-ChildItem -Path . -Filter "*.pyc" -Recurse | Remove-Item -Force
```

---

## 📂 3. 两个项目待提交的文件范围检查

目前两个项目的 Git 状态已整理完毕，推荐提交的 Untracked 文件与修改如下：

### 📁 Enterprise_RAG (企业 RAG)
*   **修改的文件**：
    *   `.env.example` (最新补充的私有化模型配置模板)
    *   `.gitignore` (已自动过滤 `AI_Plan` 与 `EnterpriseRAG_Task` 个人计划文件)
    *   `README.md` (已重构的极高质量说明文档)
    *   业务代码 (`api/`, `core/`, `web_app.py`, `pyproject.toml`, `docker-compose.yml` 等)
*   **新增需提交的 Untracked 文件** (执行 `git add` 即可)：
    *   `core/auth.py` (多租户 API Key 映射自注入拦截器)
    *   `docs/ragas_report.md` (Ragas 自动化打分报告)
    *   `eval/` (Ragas 数据集与自动化评测主程序)

### 📁 DataViz_Agent (数据智能体)
*   **修改的文件**：
    *   `.env.example` (最新补充的私有化模型配置模板)
    *   `README.md` (已重构的极高质量说明文档)
    *   业务代码 (`api/`, `core/`, `utils/`, `web_app.py`, `pyproject.toml` 等)
*   **新增需提交的 Untracked 文件** (执行 `git add` 即可)：
    *   `core/config.py` (外置可视化审美与 DPI 主题配置加载器)
    *   `tests/` (自动化集成测试目录)

---

## 🚀 4. 增量更新与推送命令流水线

既然您的项目此前已经在 GitHub 提交过一个版本，本次更新只需要将新修改的代码、重构文档和新增的 Untracked 文件进行增量提交并推送即可：

```bash
# 1. 确保在正确的本地开发分支 (如 main)
git checkout main

# 2. 将所有新增文件 (如 auth.py、Ragas 脚本与文档) 及修改加入暂存区
git add .

# 3. 提交本地更新，注明版本迭代记录
git commit -m "update: add multi-tenant auth, ragas eval, langsmith tracing and prompt tuning"

# 4. 直接推送更新到 GitHub 远程仓库
git push
```
