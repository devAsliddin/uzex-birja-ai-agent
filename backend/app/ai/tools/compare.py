"""Read-only AI tool for comparing periods."""

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import BaseTool, ToolError
from app.db.models.deal import Deal


class ComparePeriodsInput(BaseModel):
    period_from: date = Field(..., description="Начало периода YYYY-MM-DD")
    period_to: date = Field(..., description="Конец периода YYYY-MM-DD")


class ComparePeriodsOutput(BaseModel):
    period_from: str
    period_to: str
    deals_count: int
    total_amount: float | None = None
    total_volume: float | None = None


class ComparePeriods(BaseTool):
    name = "compare_periods"
    description = "Сравнить показатели за период (количество сделок, сумма, объём) (только чтение)."
    input_schema = ComparePeriodsInput
    output_schema = ComparePeriodsOutput

    async def _run(self, db: AsyncSession, input_data: ComparePeriodsInput) -> ComparePeriodsOutput:
        if input_data.period_to < input_data.period_from:
            raise ToolError("period_to не может быть раньше period_from")
        stmt = (
            select(
                func.count(Deal.deal_number).label("deals_count"),
                func.sum(Deal.amount).label("total_amount"),
                func.sum(Deal.quantity * Deal.lot_size).label("total_volume"),
            )
            .where(Deal.deal_date >= input_data.period_from)
            .where(Deal.deal_date <= input_data.period_to)
        )
        res = await db.execute(stmt)
        row = res.mappings().one()
        return ComparePeriodsOutput(
            period_from=input_data.period_from.isoformat(),
            period_to=input_data.period_to.isoformat(),
            deals_count=int(row["deals_count"] or 0),
            total_amount=float(row["total_amount"]) if row["total_amount"] is not None else None,
            total_volume=float(row["total_volume"]) if row["total_volume"] is not None else None,
        )
