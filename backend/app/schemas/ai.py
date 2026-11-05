"""AI engine schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class AIChatRequest(BaseModel):
    message: str
    language: str | None = "ru"  # ru | uz
    conversation_id: int | None = None


class AIChatResponse(BaseModel):
    response: str
    language: str
    conversation_id: int
    tool_calls: list[dict] = []
    sources: list[str] = []


class AIToolInput(BaseModel):
    pass


class AIToolOutput(BaseModel):
    ok: bool
    data: Any | None = None
    error: str | None = None
    tool: str

    model_config = ConfigDict(from_attributes=True)
