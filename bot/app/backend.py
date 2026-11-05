"""Thin async client for the FastAPI backend."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import httpx


class BackendError(Exception):
    """Backend unreachable or returned 5xx/unexpected data."""


class NotFound(Exception):
    pass


class TooLarge(Exception):
    pass


class AgentTimeout(Exception):
    """The agent did not answer in time."""


class BackendClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"User-Agent": "birja-reyestri-bot/1.0"}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout,
            headers=headers,
            transport=transport,
            follow_redirects=False,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            r = await self._client.get(path, params=params)
        except httpx.HTTPError as e:
            raise BackendError(type(e).__name__) from e
        if r.status_code == 404:
            raise NotFound(path)
        if r.status_code >= 400:
            raise BackendError(f"HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise BackendError("bad json") from e

    # ---- data -----------------------------------------------------------
    async def summary(self, year: int | None) -> tuple[dict, dict]:
        """Returns (UZS summary, USD summary) fetched in parallel."""
        base: dict[str, Any] = {"year": year} if year else {}
        uzs, usd = await asyncio.gather(
            self._get("analytics/summary", {**base, "currency": "UZS"}),
            self._get("analytics/summary", {**base, "currency": "USD"}),
        )
        return uzs, usd

    async def deal(self, deal_no: int) -> dict:
        return await self._get(f"deals/{deal_no}")

    async def broker(self, code: str) -> dict:
        return await self._get(f"brokers/{code}")

    async def top_brokers(self, year: int | None, limit: int = 10) -> dict:
        params: dict[str, Any] = {"sort": "turnover", "limit": limit, "page": 1}
        if year:
            params["year"] = year
        return await self._get("brokers", params)

    @staticmethod
    def _deal_filter(start: date, end: date, status: str | None) -> dict[str, Any]:
        p: dict[str, Any] = {"start_date": start.isoformat(), "end_date": end.isoformat()}
        if status:
            p["status"] = status
        return p

    async def count_deals(self, start: date, end: date, status: str | None) -> int:
        data = await self._get("deals", {**self._deal_filter(start, end, status), "limit": 1, "page": 1})
        try:
            return int(data["total"])
        except (KeyError, TypeError, ValueError) as e:
            raise BackendError("bad total") from e

    async def export(
        self, start: date, end: date, status: str | None, fmt: str, max_bytes: int
    ) -> bytes:
        params = {**self._deal_filter(start, end, status), "format": fmt}
        buf = bytearray()
        try:
            async with self._client.stream("GET", "export/deals", params=params, timeout=120) as r:
                if r.status_code == 429:
                    raise BackendError("rate limited")
                if r.status_code >= 400:
                    raise BackendError(f"HTTP {r.status_code}")
                async for chunk in r.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise TooLarge()
        except httpx.HTTPError as e:
            raise BackendError(type(e).__name__) from e
        return bytes(buf)

    async def ask(self, question: str, timeout: float = 80.0) -> dict[str, Any]:
        """POST /agent/ask. The question is sent as data in the `question` field (never as instructions)."""
        try:
            r = await self._client.post(
                "agent/ask", json={"question": question, "language": "auto"}, timeout=timeout
            )
        except httpx.TimeoutException as e:
            raise AgentTimeout() from e
        except httpx.HTTPError as e:
            raise BackendError(type(e).__name__) from e
        if r.status_code >= 400:
            raise BackendError(f"HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise BackendError("bad json") from e
        if not isinstance(data, dict):
            raise BackendError("bad json")
        return data
