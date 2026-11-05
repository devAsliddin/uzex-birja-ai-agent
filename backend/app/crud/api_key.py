"""CRUD operations for API keys."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.api_key import ApiKey


class CRUDApiKey(CRUDBase[ApiKey, Any, Any]):
    async def get_by_prefix(self, db: AsyncSession, *, key_prefix: str) -> ApiKey | None:
        result = await db.execute(select(ApiKey).where(ApiKey.key_prefix == key_prefix))
        return result.scalar_one_or_none()

    async def get_multi_by_user(
        self, db: AsyncSession, *, user_id: int, skip: int = 0, limit: int = 100
    ) -> list[ApiKey]:
        result = await db.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).offset(skip).limit(limit)
        )
        return list(result.scalars().all())


crud_api_key = CRUDApiKey(ApiKey)
