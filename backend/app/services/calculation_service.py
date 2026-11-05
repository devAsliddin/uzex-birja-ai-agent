"""Business calculation services.

All calculations use verified database values only. Missing exchange rates
are reported explicitly — no random substitution.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.deal import Deal
from app.db.models.usd_rate import UsdRate


def calculate_volume(quantity: int | None, lot_size: int | None) -> float | None:
    """Объём сделки в единицах измерения = Количество × Лот."""
    if quantity is None or lot_size is None:
        return None
    return quantity * lot_size


def calculate_unit_price(amount: float | None, quantity: int | None, lot_size: int | None) -> float | None:
    """Цена за единицу = Сумма сделки / (Количество × Лот)."""
    if amount is None:
        return None
    volume = calculate_volume(quantity, lot_size)
    if volume is None or volume == 0:
        return None
    return amount / volume


async def calculate_amount_uzs(
    amount_usd: float | None, deal_date: date | None, db: AsyncSession
) -> dict[str, Any]:
    """Сумма в сумах = Сумма сделки × курс на дату сделки.

    Returns dict with amount_uzs, rate, rate_available.
    If no rate exists for the date, amount_uzs is None and rate_available=False.
    """
    result: dict[str, Any] = {
        "amount_usd": amount_usd,
        "deal_date": deal_date.isoformat() if deal_date else None,
        "rate": None,
        "rate_available": False,
        "amount_uzs": None,
    }
    if amount_usd is None or deal_date is None:
        return result
    rate_row = await _get_rate(db, deal_date)
    if rate_row is None:
        return result
    rate = float(rate_row.rate)
    result["rate"] = rate
    result["rate_available"] = True
    result["amount_uzs"] = round(float(Decimal(str(amount_usd)) * Decimal(str(rate))), 2)
    return result


async def _get_rate(db: AsyncSession, deal_date: date) -> UsdRate | None:
    result = await db.execute(select(UsdRate).where(UsdRate.date == deal_date))
    return result.scalar_one_or_none()


async def compute_deal_metrics(db: AsyncSession, deal: Deal) -> dict[str, Any]:
    """Compute all derived metrics for a deal from verified values."""
    volume = calculate_volume(deal.quantity, deal.lot_size)
    unit_price = calculate_unit_price(deal.amount, deal.quantity, deal.lot_size)
    uzs = await calculate_amount_uzs(deal.amount, deal.deal_date, db)
    return {
        "deal_number": deal.deal_number,
        "volume": volume,
        "unit_price": unit_price,
        "amount_usd": float(deal.amount) if deal.amount is not None else None,
        "amount_uzs": uzs["amount_uzs"],
        "rate": uzs["rate"],
        "rate_available": uzs["rate_available"],
        "currency": "USD" if deal.contract and deal.contract.currency and "доллар" in str(deal.contract.currency).lower() else None,
    }
