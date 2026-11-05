"""CRUD operations for evaluation questions."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.evaluation_question import EvaluationQuestion


class CRUDEvaluationQuestion(CRUDBase[EvaluationQuestion, Any, Any]):
    async def get_multi_by_dataset(
        self, db: AsyncSession, *, dataset_id: int, skip: int = 0, limit: int = 100
    ) -> list[EvaluationQuestion]:
        result = await db.execute(
            select(EvaluationQuestion)
            .where(EvaluationQuestion.dataset_id == dataset_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


crud_evaluation_question = CRUDEvaluationQuestion(EvaluationQuestion)
