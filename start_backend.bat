@echo off
chcp 65001
:: 切换到当前目录并检测 Python 虚拟环境
cd /d "%~dp0"
echo ===================================================
echo   正在检测环境并拉起 Enterprise RAG 后端服务...
echo ===================================================

set PYTHON_EXEC=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXEC=.venv\Scripts\python.exe
    echo 已检测到局部 .venv 虚拟环境，将优先采用该环境。
)

echo 正在启动 uvicorn 后端服务器 (监听端口: 8000)...
%PYTHON_EXEC% -m uvicorn main:app --reload --port 8000
pause
