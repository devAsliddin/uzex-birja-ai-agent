"""Ollama local provider."""

from typing import Any

import httpx

from app.ai.providers.base import BaseProvider, LLMMessage, LLMResponse


class OllamaProvider(BaseProvider):
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
        return self._client

    async def chat_completion(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: int = 30,
        **kwargs: Any,
    ) -> LLMResponse:
        client = await self._get_client()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        payload.update(kwargs)
        try:
            resp = await client.post("/api/chat", json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Ollama provider error: {exc}") from exc
        message = data.get("message", {})
        content = message.get("content", "")
        usage = {}
        for key in ("prompt_eval_count", "eval_count"):
            usage[key] = data.get(key, 0)
        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            usage=usage,
            raw=data,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
