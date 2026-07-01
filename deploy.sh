#!/bin/bash
# Enterprise RAG 一键部署与启动脚本
# 运行环境：Ubuntu Server 22.04 LTS

set -e

echo "=== [1/4] 检查 Docker 与 Docker Compose 环境 ==="
if ! command -v docker &> /dev/null; then
    echo "Docker 未安装，正在进行安装..."
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo systemctl start docker
    sudo systemctl enable docker
else
    echo "✔ Docker 已经安装"
fi

if ! docker compose version &> /dev/null; then
    echo "Docker Compose v2 未安装，正在尝试安装..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
else
    echo "✔ Docker Compose 已经安装"
fi

echo ""
echo "=== [2/4] 准备环境变量配置文件 ==="
if [ ! -f .env ]; then
    echo "检测到 .env 配置文件不存在，正在从 .env.example 自动复制生成..."
    cp .env.example .env
    echo "⚠ 请注意：请务必编辑当前目录下的 .env 文件，填入正确的大模型 API 密钥 (OPENAI_API_KEY / BASE_URL)！"
else
    echo "✔ .env 配置文件已存在"
fi

echo ""
echo "=== [3/4] 启动 Docker 容器组合服务 ==="
echo "正在编译镜像并拉起服务，这可能需要几分钟时间，请稍候..."
sudo docker compose up -d --build

echo ""
echo "=== [4/4] 清理残留无用构建缓存以释放磁盘空间 ==="
sudo docker image prune -f

echo ""
echo "=================================================="
echo "🎉 部署服务已成功启动！"
echo "👉 后端服务运行于端口: 8010"
echo "👉 前端服务运行于端口: 5178"
echo "--------------------------------------------------"
echo "⚠ 腾讯云安全放行提示："
echo "   请务必登录腾讯云控制台的「防火墙」页面，手动添加放行以下端口的规则："
echo "   - TCP 8010 (后端接口服务)"
echo "   - TCP 5178 (前端网页服务)"
echo "   否则外网将无法正常加载和请求服务！"
echo "=================================================="
