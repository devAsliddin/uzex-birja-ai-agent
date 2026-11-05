"""Database session management.

Primary target: PostgreSQL via SQLAlchemy 2.0 async + asyncpg.
A SQLite fallback is available for local testing when PostgreSQL is not installed.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import logger

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

_read_engine: AsyncEngine | None = None
_read_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_database_url(url: str) -> str:
    """Normalize a database URL for the async engine.

    PostgreSQL URLs keep the ``postgresql+asyncpg`` driver.
    SQLite URLs use ``sqlite+aiosqlite``.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _tune_sqlite(engine: AsyncEngine) -> None:
    """WAL + sane pragmas so 500k deals stay fast on SQLite."""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn, _record):  # pragma: no cover - driver glue
        dbapi_conn.create_function("py_casefold", 1, lambda s: s.casefold() if isinstance(s, str) else s, deterministic=True)
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA cache_size=-200000")
        cur.execute("PRAGMA mmap_size=1073741824")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()


def get_engine() -> AsyncEngine:
    """Return the (singleton) async database engine."""
    global _engine, _session_factory
    if _engine is None:
        url = _normalize_database_url(settings.database_url)
        logger.info("Creating database engine: %s", url.split("@")[-1] if "@" in url else url)
        _engine = create_async_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            **(  # pool args only for PostgreSQL
                {
                    "pool_size": 10,
                    "max_overflow": 20,
                    "pool_timeout": 30,
                }
                if url.startswith("postgresql+asyncpg")
                else {}
            ),
        )
        _tune_sqlite(_engine)
        _session_factory = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory, creating the engine if needed."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_read_engine() -> AsyncEngine:
    """Return the read-only engine used by AI tools.

    Falls back to the main engine when no separate read URL is configured.
    """
    global _read_engine, _read_session_factory
    if _read_engine is None:
        url = settings.ai_read_database_url or settings.database_url
        url = _normalize_database_url(url)
        logger.info("Creating read database engine: %s", url.split("@")[-1] if "@" in url else url)
        _read_engine = create_async_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            **(  # pool args only for PostgreSQL
                {
                    "pool_size": 5,
                    "max_overflow": 10,
                }
                if url.startswith("postgresql+asyncpg")
                else {}
            ),
        )
        _tune_sqlite(_read_engine)
        _read_session_factory = async_sessionmaker(
            _read_engine, expire_on_commit=False, class_=AsyncSession
        )
    return _read_engine


def get_read_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the read-only session factory."""
    get_read_engine()
    assert _read_session_factory is not None
    return _read_session_factory


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a read-only database session (used by AI tools)."""
    async with get_read_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_database() -> None:
    """Dispose of database engines (useful on shutdown)."""
    global _engine, _read_engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    if _read_engine is not None:
        await _read_engine.dispose()
        _read_engine = None
