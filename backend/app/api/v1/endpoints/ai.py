"""AI endpoints."""


from fastapi import APIRouter, Depends

from app.ai.engine import AIEngine
from app.api.deps import get_read_db, require_ai_access
from app.core.config import settings
from app.core.ratelimit import rate_limit
from app.schemas.ai import AIChatRequest, AIChatResponse

router = APIRouter()
_ai_limit = rate_limit("ai", settings.rate_limit_ai)


@router.post("/chat", response_model=AIChatResponse, summary="Chat with the AI assistant (auth required)")
async def ai_chat(
    req: AIChatRequest,
    db_read=Depends(get_read_db),
    _=Depends(require_ai_access),
    __=Depends(_ai_limit),
):
    engine = AIEngine()
    try:
        result = await engine.process_message(
            req.message,
            language=req.language or "ru",
            conversation_id=req.conversation_id,
        )
    finally:
        await engine.close()
    return AIChatResponse(
        response=result["response"],
        language=result["language"],
        conversation_id=result["conversation_id"] or 0,
        tool_calls=result["tool_calls"],
        sources=["PostgreSQL (UZEX deals dataset)"],
    )


@router.get("/tools", summary="List available AI tools")
async def ai_tools(_=Depends(require_ai_access)):
    engine = AIEngine()
    try:
        return {"tools": engine.registry.schemas()}
    finally:
        await engine.close()
