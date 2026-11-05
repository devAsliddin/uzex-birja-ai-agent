"""Redis cache client with graceful fallback to in-memory cache.

If Redis is unavailable, a simple in-memory dict cache is used so the
application remains functional (with a warning logged).
"""

from typing import Any, cast

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import logger


class RedisCache:
    """Async wrapper around Redis with in-memory fallback."""

    def __init__(self) -> None:
        self._client: Any = None
        self._fallback: dict = {}
        self._available: bool = False

    async def connect(self) -> None:
        """Connect to Redis, or fall back to in-memory cache."""
        if not settings.redis_url:
            self._available = False
            logger.warning("REDIS_URL not set — using in-memory cache fallback")
            return
        try:
            self._client = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
            await self._client.ping()
            self._available = True
            logger.info("Redis cache connected")
        except Exception as exc:
            logger.warning("Redis unavailable (%s) — using in-memory cache fallback", exc)
            self._client = None
            self._available = False

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
        self._client = None
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    async def get(self, key: str) -> str | None:
        if self._client is not None:
            try:
                return cast(str | None, await self._client.get(key))
            except Exception as exc:
                logger.warning("Redis get failed (%s) — fallback", exc)
        return cast(str | None, self._fallback.get(key))

    async def set(self, key: str, value: Any, expire: int | None = None) -> None:
        if self._client is not None:
            try:
                if expire:
                    await self._client.set(key, value, ex=expire)
                else:
                    await self._client.set(key, value)
                return
            except Exception as exc:
                logger.warning("Redis set failed (%s) — fallback", exc)
        self._fallback[key] = value

    async def delete(self, key: str) -> None:
        if self._client is not None:
            try:
                await self._client.delete(key)
                return
            except Exception as exc:
                logger.warning("Redis delete failed (%s) — fallback", exc)
        self._fallback.pop(key, None)

    async def clear(self) -> None:
        if self._client is not None:
            try:
                await self._client.flushdb()
                return
            except Exception as exc:
                logger.warning("Redis flush failed (%s) — fallback", exc)
        self._fallback.clear()


cache = RedisCache()
