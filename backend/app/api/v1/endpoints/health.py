"""Health endpoint."""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.redis import cache
from app.db.session import get_engine
from app.schemas.common import HealthResponse

router = APIRouter()


@router.get("", response_model=HealthResponse, summary="Health check")
async def health():
    engine = get_engine()
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    redis_status = "ok" if cache.available else "unavailable (in-memory fallback)"
    return HealthResponse(
        status="ok",
        service="uzex-ai-backend",
        database=db_status,
        redis=redis_status,
    )
