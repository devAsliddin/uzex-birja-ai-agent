"""Abstract LLM provider interface.

The AI Engine depends only on this interface — not on any single provider.
"""

from abc import ABC, abstractmethod
from typing import Any

LLMMessage = dict[str, str]
"""A chat message: {role, content}."""


class LLMResponse:
    """Structured response from a provider."""

    def __init__(
        self,
        content: str,
        model: str,
        usage: dict[str, int] | None = None,
        raw: Any | None = None,
    ) -> None:
        self.content = content
        self.model = model
        self.usage = usage or {}
        self.raw = raw


class BaseProvider(ABC):
    """Every provider must implement chat_completion."""

    def __init__(self, model: str, **kwargs: Any) -> None:
        self.model = model
        self.config = kwargs

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: int = 30,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a chat completion. Must return structured LLMResponse."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release provider resources."""
        raise NotImplementedError
