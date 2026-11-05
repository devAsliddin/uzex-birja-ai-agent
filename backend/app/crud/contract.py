"""CRUD operations for contracts."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.contract import Contract


class CRUDContract(CRUDBase[Contract, Any, Any]):
    async def get_by_number(self, db: AsyncSession, *, contract_number: str) -> Contract | None:
        result = await db.execute(select(Contract).where(Contract.contract_number == contract_number))
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100, search: str | None = None
    ) -> list[Contract]:
        stmt = select(Contract)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                Contract.contract_number.ilike(like)
                | Contract.product_name.ilike(like)
            )
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())


crud_contract = CRUDContract(Contract)
