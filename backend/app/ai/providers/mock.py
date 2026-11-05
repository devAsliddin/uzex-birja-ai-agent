"""Mock LLM provider for offline testing and development."""

from typing import Any

from app.ai.providers.base import BaseProvider, LLMMessage, LLMResponse


class MockProvider(BaseProvider):
    """Deterministic mock provider that never invents data.

    Used when no real LLM is configured. It responds with a safe
    "I don't know" message in the user's language.
    """

    def __init__(self, model: str = "uzex-ai-mock", **kwargs: Any) -> None:
        super().__init__(model, **kwargs)

    async def chat_completion(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: int = 30,
        **kwargs: Any,
    ) -> LLMResponse:
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break
        lang = self._detect_language(user_text)

        if lang == "uz":
            content = (
                "Bu savolga javobni bilmayman. "
                "Mavjud ma'lumotlarda ishonchli javob berish uchun yetarli axborot yo'q."
            )
        else:
            content = (
                "Я не знаю ответа на этот вопрос. "
                "В доступных данных нет достаточной информации, чтобы достоверно ответить."
            )

        return LLMResponse(
            content=content,
            model=self.model,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            raw=None,
        )

    async def close(self) -> None:
        return None

    @staticmethod
    def _detect_language(text: str) -> str:
        low = text.lower()
        uz_words = {"savol", "javob", "bilmayman", "ma'lumot", "broker", "bitim", "qancha", "nimada"}
        ru_words = {"вопрос", "ответ", "не знаю", "данных", "брокер", "сделка", "сколько", "где"}
        if any(w in low for w in uz_words):
            return "uz"
        if any(w in low for w in ru_words):
            return "ru"
        return "ru"
