"""Cache service wrapper around Redis with in-memory fallback."""

import json
from typing import Any

from app.core.redis import cache


async def get_cached(key: str) -> Any | None:
    raw = await cache.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


async def set_cached(key: str, value: Any, expire: int | None = None) -> None:
    raw = value if isinstance(value, str) else json.dumps(value, default=str)
    await cache.set(key, raw, expire=expire)


async def delete_cached(key: str) -> None:
    await cache.delete(key)


async def clear_cache() -> None:
    await cache.clear()
