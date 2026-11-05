"""USD -> UZS conversion helpers.

Rule (TZ 2.1): for USD contracts the UZS amount = deal amount x rate on the deal
date. If the exact day is missing, the nearest previous available rate is used.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.contract import Contract
from app.db.models.deal import Deal
from app.db.models.usd_rate import UsdRate

CURRENCY_USD = "Доллар США"
STATUS_ANNULLED = "Аннулирован(Не оплачен)"


def resolve_rate(sorted_dates: list[date], rates: list[float], day: date) -> float | None:
    """Rate on ``day`` or the nearest previous one; None if none exists."""
    i = bisect_right(sorted_dates, day)
    return rates[i - 1] if i else None


def rate_subquery():
    """Correlated scalar subquery: rate for Deal.deal_date (nearest previous day)."""
    return (
        select(UsdRate.rate)
        .where(UsdRate.date <= Deal.deal_date)
        .order_by(UsdRate.date.desc())
        .limit(1)
        .correlate(Deal)
        .scalar_subquery()
    )


def is_usd() -> ColumnElement[bool]:
    return Contract.currency == CURRENCY_USD


def amount_uzs_expr() -> ColumnElement:
    """Deal amount in UZS (needs Contract joined to Deal)."""
    return case((is_usd(), Deal.amount * rate_subquery()), else_=Deal.amount)


def amount_usd_expr() -> ColumnElement:
    """Deal amount in USD (needs Contract joined to Deal)."""
    return case((is_usd(), Deal.amount), else_=Deal.amount / rate_subquery())


def amount_expr(currency: str) -> ColumnElement:
    return amount_usd_expr() if currency.upper() == "USD" else amount_uzs_expr()


def executed_amount_expr(currency: str) -> ColumnElement:
    """Amount that counts towards turnover: annulled deals did not happen -> 0."""
    return case((Deal.status == STATUS_ANNULLED, 0), else_=amount_expr(currency))


def sum_expr(currency: str) -> ColumnElement:
    return func.coalesce(func.sum(amount_expr(currency)), 0)
