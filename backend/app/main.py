"""UZEX AI Backend — FastAPI application."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.exceptions import UZEXException
from app.core.logging import configure_logging, logger
from app.core.redis import cache
from app.db.session import close_database, get_engine


async def _warm_caches() -> None:
    """Pre-compute heavy aggregates so the first dashboard request is instant."""
    from app.db.session import get_read_session_factory
    from app.services import registry_service as rs

    try:
        async with get_read_session_factory()() as db:
            await rs.meta_filters(db)
            await rs.broker_aggregates(db)
            await rs.analytics_summary(db, None, "UZS")
        logger.info("cache warm-up done")
    except Exception as exc:  # tables may not exist yet / empty DB
        logger.info("cache warm-up skipped (%s)", type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await cache.connect()
    get_engine()
    warm = asyncio.create_task(_warm_caches())
    logger.info("Backend started (env=%s)", settings.app_env)
    yield
    warm.cancel()
    await cache.disconnect()
    await close_database()
    logger.info("UZEX AI Backend shutdown")


app = FastAPI(
    title="Birja Reyestri API",
    description="Commodity exchange deals and brokers registry (500k deals).",
    version="1.0.0",
    openapi_url=f"{settings.api_v1_str}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

if settings.backend_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in settings.backend_cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        expose_headers=["Content-Disposition"],
    )


@app.exception_handler(UZEXException)
async def uzex_exception_handler(request: Request, exc: UZEXException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "code": exc.code,
            "status_code": exc.status_code,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "internal_error", "status_code": 500},
    )


@app.get("/health", tags=["health"])
async def health():
    engine = get_engine()
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("health: database check failed (%s)", type(exc).__name__)
        db_status = "error"
    redis_status = "ok" if cache.available else "unavailable (in-memory fallback)"
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "1.0.0",
        "database": db_status,
        "redis": redis_status,
    }


app.include_router(api_router, prefix=settings.api_v1_str)


# --- Static frontend (Next.js `output: export`) on the same origin ---------------------------
# Mounted LAST so /api/v1/*, /docs, /redoc and /health keep priority. No X-Frame-Options is set,
# so the Telegram Mini App can embed the dashboard.
import os as _os
from pathlib import Path as _Path

from fastapi.staticfiles import StaticFiles as _StaticFiles

_FRONTEND_DIST = _Path(
    _os.getenv("FRONTEND_DIST", str(_Path(__file__).resolve().parents[2] / "frontend" / "out"))
)
if _FRONTEND_DIST.is_dir():
    app.mount("/", _StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
