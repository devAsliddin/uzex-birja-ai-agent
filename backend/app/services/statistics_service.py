"""Statistics and aggregation services over verified deal data."""

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.broker import Broker
from app.db.models.contract import Contract
from app.db.models.deal import Deal
from app.db.models.participant import Participant
from app.db.models.usd_rate import UsdRate


async def get_deal_statistics(db: AsyncSession) -> dict[str, Any]:
    total = await _scalar(db, select(func.count(Deal.deal_number)))
    total_amount = await _scalar(db, select(func.sum(Deal.amount)))
    # Volume: sum(quantity * lot_size)
    total_volume = await _scalar(
        db, select(func.sum(Deal.quantity * Deal.lot_size)).where(Deal.quantity.is_not(None), Deal.lot_size.is_not(None))
    )

    return {
        "total_deals": total or 0,
        "total_amount": float(total_amount) if total_amount is not None else None,
        "total_volume": float(total_volume) if total_volume is not None else None,
    }


async def get_broker_statistics(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    stmt = (
        select(
            Deal.broker_seller_code.label("broker_code"),
            func.count(Deal.deal_number).label("deal_count"),
            func.sum(Deal.amount).label("total_amount"),
            func.sum(Deal.quantity * Deal.lot_size).label("total_volume"),
        )
        .where(Deal.broker_seller_code.is_not(None))
        .group_by(Deal.broker_seller_code)
        .order_by(func.count(Deal.deal_number).desc())
        .limit(limit)
    )
    rows = await _rows(db, stmt)
    result: list[dict[str, Any]] = []
    for r in rows:
        broker = await _get_broker(db, r["broker_code"])
        result.append(
            {
                "broker_code": r["broker_code"],
                "broker_name": broker.name if broker else None,
                "deal_count": int(r["deal_count"] or 0),
                "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
                "total_volume": float(r["total_volume"]) if r["total_volume"] is not None else None,
            }
        )
    return result


async def get_participant_statistics(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    # Combine seller and buyer sides
    seller_stmt = (
        select(
            Deal.seller_inn.label("inn"),
            func.count(Deal.deal_number).label("deal_count"),
            func.sum(Deal.amount).label("total_amount"),
        )
        .where(Deal.seller_inn.is_not(None))
        .group_by(Deal.seller_inn)
    )
    buyer_stmt = (
        select(
            Deal.buyer_inn.label("inn"),
            func.count(Deal.deal_number).label("deal_count"),
            func.sum(Deal.amount).label("total_amount"),
        )
        .where(Deal.buyer_inn.is_not(None))
        .group_by(Deal.buyer_inn)
    )
    combined = seller_stmt.union_all(buyer_stmt).alias("combined")
    stmt = (
        select(
            combined.c.inn,
            func.sum(combined.c.deal_count).label("deal_count"),
            func.sum(combined.c.total_amount).label("total_amount"),
        )
        .group_by(combined.c.inn)
        .order_by(func.sum(combined.c.deal_count).desc())
        .limit(limit)
    )
    rows = await _rows(db, stmt)
    result: list[dict[str, Any]] = []
    for r in rows:
        participant = await _get_participant(db, r["inn"])
        result.append(
            {
                "inn": r["inn"],
                "name": participant.name if participant else None,
                "role": participant.role if participant else None,
                "deal_count": int(r["deal_count"] or 0),
                "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
            }
        )
    return result


async def get_product_statistics(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    stmt = (
        select(
            Deal.product_name.label("product_name"),
            func.count(Deal.deal_number).label("deal_count"),
            func.sum(Deal.quantity * Deal.lot_size).label("total_volume"),
            func.sum(Deal.amount).label("total_amount"),
        )
        .where(Deal.product_name.is_not(None))
        .group_by(Deal.product_name)
        .order_by(func.count(Deal.deal_number).desc())
        .limit(limit)
    )
    rows = await _rows(db, stmt)
    return [
        {
            "product_name": r["product_name"],
            "deal_count": int(r["deal_count"] or 0),
            "total_volume": float(r["total_volume"]) if r["total_volume"] is not None else None,
            "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
        }
        for r in rows
    ]


async def get_region_statistics(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    stmt = (
        select(
            Deal.region.label("region"),
            func.count(Deal.deal_number).label("deal_count"),
            func.sum(Deal.amount).label("total_amount"),
        )
        .where(Deal.region.is_not(None))
        .group_by(Deal.region)
        .order_by(func.count(Deal.deal_number).desc())
        .limit(limit)
    )
    rows = await _rows(db, stmt)
    return [
        {
            "region": r["region"],
            "deal_count": int(r["deal_count"] or 0),
            "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
        }
        for r in rows
    ]


async def get_industry_statistics(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    stmt = (
        select(
            Contract.industry.label("industry"),
            func.count(Deal.deal_number).label("deal_count"),
            func.sum(Deal.amount).label("total_amount"),
        )
        .join(Deal, Deal.contract_number == Contract.contract_number, isouter=True)
        .where(Contract.industry.is_not(None))
        .group_by(Contract.industry)
        .order_by(func.count(Deal.deal_number).desc())
        .limit(limit)
    )
    rows = await _rows(db, stmt)
    return [
        {
            "industry": r["industry"],
            "deal_count": int(r["deal_count"] or 0),
            "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
        }
        for r in rows
    ]


async def get_status_statistics(db: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(
            Deal.status.label("status"),
            func.count(Deal.deal_number).label("deal_count"),
        )
        .where(Deal.status.is_not(None))
        .group_by(Deal.status)
        .order_by(func.count(Deal.deal_number).desc())
    )
    rows = await _rows(db, stmt)
    return [
        {"status": r["status"], "deal_count": int(r["deal_count"] or 0)} for r in rows
    ]


async def get_period_statistics(
    db: AsyncSession, period: str = "month"
) -> list[dict[str, Any]]:
    """Aggregate deals by period (month or year) using deal_date."""
    if period == "year":
        expr = func.to_char(Deal.deal_date, "YYYY")
    else:
        expr = func.to_char(Deal.deal_date, "YYYY-MM")
    stmt = (
        select(
            expr.label("period"),
            func.count(Deal.deal_number).label("deal_count"),
            func.sum(Deal.amount).label("total_amount"),
            func.sum(Deal.quantity * Deal.lot_size).label("total_volume"),
        )
        .group_by(expr)
        .order_by(expr)
    )
    rows = await _rows(db, stmt)
    return [
        {
            "period": r["period"],
            "deal_count": int(r["deal_count"] or 0),
            "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
            "total_volume": float(r["total_volume"]) if r["total_volume"] is not None else None,
        }
        for r in rows
    ]


async def get_dataset_information(db: AsyncSession) -> dict[str, Any]:
    total_deals = await _scalar(db, select(func.count(Deal.deal_number)))
    total_contracts = await _scalar(db, select(func.count(Contract.contract_number)))
    total_participants = await _scalar(db, select(func.count(Participant.inn)))
    total_brokers = await _scalar(db, select(func.count(Broker.code)))
    total_rates = await _scalar(db, select(func.count(UsdRate.date)))
    date_from = await _scalar(db, select(func.min(Deal.deal_date)))
    date_to = await _scalar(db, select(func.max(Deal.deal_date)))
    statuses = await _rows(db, select(Deal.status).where(Deal.status.is_not(None)).distinct())
    return {
        "total_deals": int(total_deals or 0),
        "total_contracts": int(total_contracts or 0),
        "total_participants": int(total_participants or 0),
        "total_brokers": int(total_brokers or 0),
        "total_usd_rates": int(total_rates or 0),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "currencies": [],
        "statuses": [r["status"] for r in statuses],
    }


async def compare_periods(
    db: AsyncSession, period_from: date, period_to: date
) -> dict[str, Any]:
    async def agg(frm: date, to: date) -> dict[str, Any]:
        stmt = (
            select(
                func.count(Deal.deal_number).label("deals_count"),
                func.sum(Deal.amount).label("total_amount"),
                func.sum(Deal.quantity * Deal.lot_size).label("total_volume"),
            )
            .where(Deal.deal_date >= frm)
            .where(Deal.deal_date <= to)
        )
        row = await _row(db, stmt)
        if row is None:
            return {"deals_count": 0, "total_amount": None, "total_volume": None}
        return {
            "deals_count": int(row["deals_count"] or 0),
            "total_amount": float(row["total_amount"]) if row["total_amount"] is not None else None,
            "total_volume": float(row["total_volume"]) if row["total_volume"] is not None else None,
        }

    a = await agg(period_from, period_to)
    return {"period_from": period_from.isoformat(), "period_to": period_to.isoformat(), **a}


async def get_top_brokers(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    return await get_broker_statistics(db, limit=limit)


async def get_top_products(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    return await get_product_statistics(db, limit=limit)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _scalar(db: AsyncSession, stmt) -> Any:
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _row(db: AsyncSession, stmt) -> dict[str, Any] | None:
    result = await db.execute(stmt)
    row = result.mappings().first()
    return dict(row) if row else None


async def _rows(db: AsyncSession, stmt) -> list[dict[str, Any]]:
    result = await db.execute(stmt)
    return [dict(r) for r in result.mappings().all()]


async def _get_broker(db: AsyncSession, code: str | None) -> Broker | None:
    if not code:
        return None
    result = await db.execute(select(Broker).where(Broker.code == code))
    return result.scalar_one_or_none()


async def _get_participant(db: AsyncSession, inn: str | None) -> Participant | None:
    if not inn:
        return None
    result = await db.execute(select(Participant).where(Participant.inn == inn))
    return result.scalar_one_or_none()
