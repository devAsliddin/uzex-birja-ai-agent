"""Read-only AI tools for exchange rates."""

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import BaseTool
from app.db.models.usd_rate import UsdRate


class GetExchangeRateInput(BaseModel):
    rate_date: date = Field(..., description="Дата курса в формате YYYY-MM-DD")


class GetExchangeRateOutput(BaseModel):
    date: str
    rate: float | None = None
    available: bool = False


class GetExchangeRate(BaseTool):
    name = "get_exchange_rate"
    description = "Курс USD на указанную дату (сум за 1 USD). Если курса нет — available=false (только чтение)."
    input_schema = GetExchangeRateInput
    output_schema = GetExchangeRateOutput

    async def _run(self, db: AsyncSession, input_data: GetExchangeRateInput) -> GetExchangeRateOutput:
        res = await db.execute(select(UsdRate).where(UsdRate.date == input_data.rate_date))
        rate = res.scalar_one_or_none()
        if rate is None:
            return GetExchangeRateOutput(
                date=input_data.rate_date.isoformat(), rate=None, available=False
            )
        return GetExchangeRateOutput(
            date=input_data.rate_date.isoformat(), rate=float(rate.rate), available=True
        )
