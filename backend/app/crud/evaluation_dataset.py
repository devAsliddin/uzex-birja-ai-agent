"""CRUD operations for evaluation datasets."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.evaluation_dataset import EvaluationDataset


class CRUDEvaluationDataset(CRUDBase[EvaluationDataset, Any, Any]):
    async def get_by_name(self, db: AsyncSession, *, name: str) -> EvaluationDataset | None:
        result = await db.execute(select(EvaluationDataset).where(EvaluationDataset.name == name))
        return result.scalar_one_or_none()


crud_evaluation_dataset = CRUDEvaluationDataset(EvaluationDataset)
