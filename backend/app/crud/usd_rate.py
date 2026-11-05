"""CRUD operations for USD rates."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.usd_rate import UsdRate


class CRUDUsdRate(CRUDBase[UsdRate, Any, Any]):
    async def get_by_date(self, db: AsyncSession, *, date: date) -> UsdRate | None:
        result = await db.execute(select(UsdRate).where(UsdRate.date == date))
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> list[UsdRate]:
        stmt = select(UsdRate).order_by(UsdRate.date.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())


crud_usd_rate = CRUDUsdRate(UsdRate)
