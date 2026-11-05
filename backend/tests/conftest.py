"""Pytest configuration: isolated SQLite DB loaded from small fixture CSVs."""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="birja_test_"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["AI_READ_DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["APP_ENV"] = "test"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seeded():
    """Create schema (from models) and import the fixture CSVs once."""
    from app.db.base import Base
    from app.db.session import get_engine, get_session_factory
    from app.services.import_service import ImportService

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    service = ImportService(data_dir=str(FIXTURES))
    async with get_session_factory()() as db:
        reports = await service.import_all(db)
    yield {r.table: r for r in reports}
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def client(seeded):
    from app.core.ratelimit import reset_rate_limits
    from app.core.ttl_cache import clear_ttl_cache
    from app.main import app

    reset_rate_limits()
    clear_ttl_cache()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture(loop_scope="session")
async def db(seeded):
    from app.db.session import get_session_factory

    async with get_session_factory()() as session:
        yield session
