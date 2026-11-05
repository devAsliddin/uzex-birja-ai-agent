"""CRUD operations for prompt versions."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.prompt_version import PromptVersion


class CRUDPromptVersion(CRUDBase[PromptVersion, Any, Any]):
    async def get_active(self, db: AsyncSession) -> PromptVersion | None:
        result = await db.execute(select(PromptVersion).where(PromptVersion.is_active == True))  # noqa: E712
        return result.scalar_one_or_none()

    async def get_by_version(self, db: AsyncSession, *, version: str) -> PromptVersion | None:
        result = await db.execute(select(PromptVersion).where(PromptVersion.version == version))
        return result.scalar_one_or_none()


crud_prompt_version = CRUDPromptVersion(PromptVersion)
