"""CRUD operations for evaluation runs."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.evaluation_run import EvaluationRun


class CRUDEvaluationRun(CRUDBase[EvaluationRun, Any, Any]):
    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> list[EvaluationRun]:
        result = await db.execute(
            select(EvaluationRun)
            .order_by(EvaluationRun.started_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


crud_evaluation_run = CRUDEvaluationRun(EvaluationRun)
