"""Read-only AI tools for deals."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import String, and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import MAX_RESULT_ROWS, BaseTool
from app.db.models.deal import Deal


class SearchDealsInput(BaseModel):
    query: str | None = Field(None, description="Поиск по наименованию товара, региону, статусу")
    status: str | None = None
    region: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class SearchDealsOutput(BaseModel):
    deals: list[dict]
    count: int


class SearchDeals(BaseTool):
    name = "search_deals"
    description = "Поиск сделок с фильтрами и пагинацией (только чтение)."
    input_schema = SearchDealsInput
    output_schema = SearchDealsOutput

    async def _run(self, db: AsyncSession, input_data: SearchDealsInput) -> SearchDealsOutput:
        stmt = select(Deal)
        conds: list[Any] = []
        if input_data.query:
            like = f"%{input_data.query}%"
            conds.append(
                Deal.product_name.ilike(like)
                | Deal.region.ilike(like)
                | Deal.status.ilike(like)
                | cast(Deal.deal_number, String).ilike(like)
            )
        if input_data.status:
            conds.append(Deal.status == input_data.status)
        if input_data.region:
            conds.append(Deal.region == input_data.region)
        if input_data.date_from:
            conds.append(Deal.deal_date >= input_data.date_from)
        if input_data.date_to:
            conds.append(Deal.deal_date <= input_data.date_to)
        if conds:
            stmt = stmt.where(and_(*conds))
        stmt = stmt.order_by(Deal.deal_date.desc(), Deal.deal_number.desc()).limit(input_data.limit)
        res = await db.execute(stmt)
        rows = res.scalars().all()
        deals = [
            {
                "deal_number": r.deal_number,
                "deal_date": r.deal_date.isoformat(),
                "product_name": r.product_name,
                "status": r.status,
                "region": r.region,
                "amount": float(r.amount) if r.amount is not None else None,
                "currency": r.unit,
                "quantity": r.quantity,
                "lot_size": r.lot_size,
            }
            for r in rows
        ]
        return SearchDealsOutput(deals=deals, count=len(deals))


class GetDealDetailsInput(BaseModel):
    deal_number: int = Field(..., description="Номер сделки")


class GetDealDetailsOutput(BaseModel):
    deal: dict | None


class GetDealDetails(BaseTool):
    name = "get_deal_details"
    description = "Детали сделки по номеру сделки (только чтение)."
    input_schema = GetDealDetailsInput
    output_schema = GetDealDetailsOutput

    async def _run(self, db: AsyncSession, input_data: GetDealDetailsInput) -> GetDealDetailsOutput:
        res = await db.execute(select(Deal).where(Deal.deal_number == input_data.deal_number))
        deal = res.scalar_one_or_none()
        if deal is None:
            return GetDealDetailsOutput(deal=None)
        return GetDealDetailsOutput(
            deal={
                "deal_number": deal.deal_number,
                "deal_date": deal.deal_date.isoformat(),
                "deal_time": str(deal.deal_time) if deal.deal_time else None,
                "auction_type": deal.auction_type,
                "quantity": deal.quantity,
                "amount": float(deal.amount) if deal.amount is not None else None,
                "start_price": float(deal.start_price) if deal.start_price is not None else None,
                "contract_number": deal.contract_number,
                "product_name": deal.product_name,
                "lot_size": deal.lot_size,
                "unit": deal.unit,
                "region": deal.region,
                "contract_type": deal.contract_type,
                "contract_form": deal.contract_form,
                "status": deal.status,
                "seller_inn": deal.seller_inn,
                "buyer_inn": deal.buyer_inn,
                "broker_seller_code": deal.broker_seller_code,
                "broker_buyer_code": deal.broker_buyer_code,
                "payment_date": deal.payment_date.isoformat() if deal.payment_date else None,
                "delivery_date": deal.delivery_date.isoformat() if deal.delivery_date else None,
                "delivered_quantity": deal.delivered_quantity,
            }
        )
