"""Google Gemini provider (native generateContent API, key sent in x-goog-api-key header)."""

from typing import Any

import httpx

from app.ai.providers.base import BaseProvider, LLMMessage, LLMResponse


class GeminiProvider(BaseProvider):
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        self.api_key = api_key
        self.base_url = (base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key or ""}
            self._client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=60.0)
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
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            text = m.get("content", "")
            if role == "system":
                system_parts.append(text)
            else:
                contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
        gen_cfg: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            # short factual answers: no hidden reasoning (cheaper, faster)
            "thinkingConfig": {"thinkingBudget": 0},
        }
        # optional overrides (backwards compatible): thinking_config=None omits it,
        # a dict replaces it; response_mime_type / response_schema enable JSON mode.
        if "thinking_config" in kwargs:
            tc = kwargs["thinking_config"]
            if tc is None:
                gen_cfg.pop("thinkingConfig", None)
            else:
                gen_cfg["thinkingConfig"] = tc
        if kwargs.get("response_mime_type"):
            gen_cfg["responseMimeType"] = kwargs["response_mime_type"]
        if kwargs.get("response_schema"):
            gen_cfg["responseSchema"] = kwargs["response_schema"]
        payload: dict[str, Any] = {"contents": contents, "generationConfig": gen_cfg}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        try:
            resp = await client.post(f"/models/{self.model}:generateContent", json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            # never include the request (it carries the key header) in the error text
            raise RuntimeError(f"Gemini provider error: HTTP {exc.response.status_code}") from None
        except Exception as exc:
            raise RuntimeError(f"Gemini provider error: {type(exc).__name__}") from None
        candidates = data.get("candidates") or [{}]
        parts = (candidates[0].get("content") or {}).get("parts") or []
        content = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        usage = data.get("usageMetadata", {}) or {}
        return LLMResponse(
            content=content,
            model=data.get("modelVersion", self.model),
            usage={
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            },
            raw=data,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
