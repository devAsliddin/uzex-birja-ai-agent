"""CRUD operations for evaluation results."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.evaluation_result import EvaluationResult


class CRUDEvaluationResult(CRUDBase[EvaluationResult, Any, Any]):
    async def get_multi_by_run(
        self, db: AsyncSession, *, run_id: int, skip: int = 0, limit: int = 100
    ) -> list[EvaluationResult]:
        result = await db.execute(
            select(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


crud_evaluation_result = CRUDEvaluationResult(EvaluationResult)
