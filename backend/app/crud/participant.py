"""CRUD operations for participants."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.participant import Participant


class CRUDParticipant(CRUDBase[Participant, Any, Any]):
    async def get_by_inn(self, db: AsyncSession, *, inn: str) -> Participant | None:
        result = await db.execute(select(Participant).where(Participant.inn == inn))
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100, search: str | None = None
    ) -> list[Participant]:
        stmt = select(Participant)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(Participant.name.ilike(like) | Participant.inn.ilike(like))
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())


crud_participant = CRUDParticipant(Participant)
