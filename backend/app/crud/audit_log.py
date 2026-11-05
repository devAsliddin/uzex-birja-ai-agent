"""CRUD operations for audit logs."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.audit_log import AuditLog


class CRUDAuditLog(CRUDBase[AuditLog, Any, Any]):
    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> list[AuditLog]:
        result = await db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())


crud_audit_log = CRUDAuditLog(AuditLog)
