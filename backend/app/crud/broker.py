"""CRUD operations for brokers."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.broker import Broker


class CRUDBroker(CRUDBase[Broker, Any, Any]):
    async def get_by_code(self, db: AsyncSession, *, code: str) -> Broker | None:
        result = await db.execute(select(Broker).where(Broker.code == code))
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100, search: str | None = None
    ) -> list[Broker]:
        stmt = select(Broker)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(Broker.name.ilike(like) | Broker.code.ilike(like))
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())


crud_broker = CRUDBroker(Broker)
