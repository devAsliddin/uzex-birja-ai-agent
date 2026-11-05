"""Simple in-memory sliding-window rate limiter (per client IP, per bucket)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.exceptions import RateLimitError

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def rate_limit(bucket: str, per_minute: int):
    """FastAPI dependency factory: ``Depends(rate_limit("export", 10))``."""

    async def _dep(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        q = _hits[(bucket, ip)]
        now = time.monotonic()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= per_minute:
            raise RateLimitError()
        q.append(now)

    return _dep


def reset_rate_limits() -> None:
    _hits.clear()
