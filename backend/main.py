from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.core.config import settings
from backend.db.base import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
        await conn.run_sync(Base.metadata.create_all)

    # Initialize Redis (for debounce and future caching)
    import redis.asyncio as aioredis
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=False)

    yield

    # Shutdown
    await app.state.redis.close()
    await engine.dispose()


app = FastAPI(
    title="Tanger Med / CIRES Technologies RAG Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# ── Routes ──

@app.get("/health")
async def health():
    """Health check with dependency verification."""
    checks = {"service": "cires-tanger-med-rag-api"}

    # Check PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Check Weaviate
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.weaviate_url}/v1/.well-known/ready")
            checks["weaviate"] = "ok" if resp.status_code == 200 else f"status {resp.status_code}"
    except Exception as e:
        checks["weaviate"] = f"error: {e}"

    all_ok = all(v == "ok" for k, v in checks.items() if k != "service")
    checks["status"] = "ok" if all_ok else "degraded"

    return checks


# Import and include module routers
from backend.api.routes import router as api_router  # noqa: E402

app.include_router(api_router, prefix="/api")
