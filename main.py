import logging
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.admin_routes import router as admin_router
from api.auth_routes import router as auth_router
from api.chat_routes import router as chat_router
from api.tool_routes import router as tool_router
from api.wiki_routes import router as wiki_router
from core.config import settings
from core.database import cleanup_expired_temporary_visitors, init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def temporary_visitor_cleanup_loop() -> None:
    interval = max(30, settings.TEMP_VISITOR_CLEANUP_INTERVAL_SECONDS)
    while True:
        try:
            cleaned_count = cleanup_expired_temporary_visitors()
            if cleaned_count:
                logger.info("Temporary visitor cleanup removed %s expired tenant(s)", cleaned_count)
        except Exception:
            logger.exception("Temporary visitor cleanup loop failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    cleanup_task = None
    if settings.ENABLE_TEMP_VISITOR_CLEANUP:
        cleanup_task = asyncio.create_task(temporary_visitor_cleanup_loop())
    try:
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                logger.info("Temporary visitor cleanup loop stopped")


app = FastAPI(
    title="Enterprise RAG Service",
    description="Enterprise knowledge base Q&A microservice powered by FastAPI + LangChain + ChromaDB",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5178",
        "http://127.0.0.1:5178",
        "http://stellarbit.site:5178",  # 允许公网前端服务跨域请求
        "http://localhost:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(tool_router, prefix="/api/v1")
app.include_router(wiki_router)



@app.get("/", tags=["System"])
async def root():
    return {
        "service": "Enterprise RAG Service",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)
