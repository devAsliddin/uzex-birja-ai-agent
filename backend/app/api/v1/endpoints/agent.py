"""Public deal-registry Q&A agent (no auth; rate-limited per IP)."""

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agent.engine import get_agent
from app.core.ratelimit import rate_limit

router = APIRouter()
_agent_limit = rate_limit("agent", 20)


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)


class AgentAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    language: Literal["auto", "ru", "uz"] = "auto"
    history: list[HistoryTurn] = Field(default_factory=list, max_length=20)
    conversation_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]*$")


class AgentAskResponse(BaseModel):
    answer: str
    language: str
    status: Literal["ok", "no_data", "error"]
    sql: list[str] = []
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    basis: str = ""
    model: str = ""
    latency_ms: int = 0
    tokens: dict[str, Any] = {}
    conversation_id: str = ""
    suggestions: list[str] = []


@router.post("/ask", response_model=AgentAskResponse, summary="Ask a question about the deal data (public)")
async def agent_ask(req: AgentAskRequest, _=Depends(_agent_limit)) -> AgentAskResponse:
    result = await get_agent().ask(
        req.question,
        req.language,
        history=[h.model_dump() for h in req.history[-6:]],
        conversation_id=req.conversation_id,
    )
    return AgentAskResponse(**result.to_dict())
