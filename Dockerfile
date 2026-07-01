# ============================================================
# Stage 1: 依赖安装（利用 Docker 层缓存，仅代码变更时不重装依赖）
# ============================================================
FROM python:3.13-slim AS builder

WORKDIR /app

# 安装 uv 包管理器
RUN pip install --no-cache-dir uv

# 先复制依赖声明文件（代码未变更时此层可复用缓存）
COPY pyproject.toml uv.lock ./

# 将依赖安装到系统 Python，避免在容器内使用虚拟环境的复杂性
ENV UV_PROJECT_ENVIRONMENT=/usr/local
RUN uv sync --frozen --no-dev

# ============================================================
# Stage 2: 运行时镜像
# ============================================================
FROM python:3.13-slim

WORKDIR /app

# 从 builder 阶段复制已安装的依赖
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制后端应用核心代码（避开前端代码及本地 node_modules 冗余包）
COPY api/ ./api/
COPY core/ ./core/
COPY schemas/ ./schemas/
COPY main.py ./

# 创建必要的数据目录
RUN mkdir -p data/uploads data/chroma_db

# 暴露 FastAPI 服务端口
EXPOSE 8000

# 启动后端服务（生产模式不开 reload）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
