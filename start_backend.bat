@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===============================================
echo Starting Enterprise RAG backend service...
echo ===============================================

set PYTHON_EXEC=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXEC=.venv\Scripts\python.exe
    echo Using local virtual environment: .venv
)

echo Launching uvicorn on port 8010...
%PYTHON_EXEC% -m uvicorn main:app --reload --port 8010
pause
