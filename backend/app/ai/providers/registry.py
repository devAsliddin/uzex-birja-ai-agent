"""Provider factory / registry."""


from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import BaseProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.mock import MockProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai import OpenAIProvider
from app.core.config import settings


def create_provider(
    provider_name: str | None = None,
    model: str | None = None,
) -> BaseProvider:
    """Create an LLM provider based on configuration."""
    name = (provider_name or settings.ai_provider).lower()
    model_name = model or settings.ai_model
    if name == "openai":
        return OpenAIProvider(
            model=model_name,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=settings.ai_temperature,
        )
    if name == "anthropic":
        return AnthropicProvider(
            model=model_name,
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
        )
    if name == "gemini":
        return GeminiProvider(
            model=model_name,
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
        )
    if name == "ollama":
        return OllamaProvider(
            model=model_name,
            base_url=settings.ollama_base_url,
        )
    # default: mock (safe offline provider)
    return MockProvider(model=model_name)
