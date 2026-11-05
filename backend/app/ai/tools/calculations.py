"""Read-only AI calculation tools."""


from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import BaseTool, ToolError


class CalculateDealVolumeInput(BaseModel):
    quantity: int = Field(..., description="Количество лотов")
    lot_size: int = Field(..., description="Размер лота")


class CalculateDealVolumeOutput(BaseModel):
    volume: float
    unit: str = "единиц"


class CalculateDealVolume(BaseTool):
    name = "calculate_deal_volume"
    description = "Объём сделки = Количество × Лот."
    input_schema = CalculateDealVolumeInput
    output_schema = CalculateDealVolumeOutput

    async def _run(self, db, input_data: CalculateDealVolumeInput) -> CalculateDealVolumeOutput:
        if input_data.quantity < 0 or input_data.lot_size < 0:
            raise ToolError("Количество и размер лота не могут быть отрицательными")
        return CalculateDealVolumeOutput(volume=input_data.quantity * input_data.lot_size)


class CalculateUnitPriceInput(BaseModel):
    amount: float = Field(..., description="Сумма сделки")
    quantity: int = Field(..., description="Количество лотов")
    lot_size: int = Field(..., description="Размер лота")


class CalculateUnitPriceOutput(BaseModel):
    unit_price: float | None = None
    currency: str = "валюта контракта"


class CalculateUnitPrice(BaseTool):
    name = "calculate_unit_price"
    description = "Цена за единицу = Сумма сделки / (Количество × Лот)."
    input_schema = CalculateUnitPriceInput
    output_schema = CalculateUnitPriceOutput

    async def _run(self, db, input_data: CalculateUnitPriceInput) -> CalculateUnitPriceOutput:
        if input_data.quantity <= 0 or input_data.lot_size <= 0:
            return CalculateUnitPriceOutput(unit_price=None)
        volume = input_data.quantity * input_data.lot_size
        return CalculateUnitPriceOutput(unit_price=input_data.amount / volume)


class CalculateAmountUzsInput(BaseModel):
    amount_usd: float = Field(..., description="Сумма в USD")
    date: str = Field(..., description="Дата сделки YYYY-MM-DD")


class CalculateAmountUzsOutput(BaseModel):
    amount_uzs: float | None = None
    rate: float | None = None
    rate_available: bool = False


class CalculateAmountUzs(BaseTool):
    name = "calculate_amount_uzs"
    description = "Сумма в сумах = Сумма × курс на дату. Если курса нет — rate_available=false."
    input_schema = CalculateAmountUzsInput
    output_schema = CalculateAmountUzsOutput

    async def _run(self, db: AsyncSession, input_data: CalculateAmountUzsInput) -> CalculateAmountUzsOutput:
        from datetime import date as _date
        try:
            d = _date.fromisoformat(input_data.date)
        except ValueError as exc:
            raise ToolError("Неверный формат даты, ожидается YYYY-MM-DD") from exc
        from sqlalchemy import select

        from app.db.models.usd_rate import UsdRate
        res = await db.execute(select(UsdRate).where(UsdRate.date == d))
        rate_row = res.scalar_one_or_none()
        if rate_row is None:
            return CalculateAmountUzsOutput(
                amount_uzs=None, rate=None, rate_available=False
            )
        rate = float(rate_row.rate)
        return CalculateAmountUzsOutput(
            amount_uzs=round(input_data.amount_usd * rate, 2),
            rate=rate,
            rate_available=True,
        )
