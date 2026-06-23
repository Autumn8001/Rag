"""
Enterprise RAG Service — 应用入口

启动 FastAPI 服务，注册路由，配置 CORS 中间件。
"""

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat_routes import router as chat_router
from api.admin_routes import router as admin_router
from api.auth_routes import router as auth_router
from core.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

init_db()

app = FastAPI(
    title="Enterprise RAG Service",
    description="Enterprise knowledge base Q&A microservice — FastAPI + LangChain + ChromaDB",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://localhost:8501"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/", tags=["System"])
async def root():
    return {
        "service": "Enterprise RAG Service",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)