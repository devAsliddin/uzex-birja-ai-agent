"""CRUD operations for messages."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.message import Message


class CRUDMessage(CRUDBase[Message, Any, Any]):
    async def get_multi_by_conversation(
        self, db: AsyncSession, *, conversation_id: int, skip: int = 0, limit: int = 100
    ) -> list[Message]:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


crud_message = CRUDMessage(Message)
