@echo off
chcp 65001
:: 切换到前端子目录并启动 Vite 开发服务器
cd /d "%~dp0frontend"
echo 正在启动 Enterprise RAG 前端开发服务器...
npm run dev
pause
