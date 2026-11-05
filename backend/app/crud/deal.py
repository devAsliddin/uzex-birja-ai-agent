"""CRUD operations for deals with filtering, search and pagination."""

from datetime import date
from typing import Any

from sqlalchemy import String, and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models.deal import Deal


class CRUDDeal(CRUDBase[Deal, Any, Any]):
    async def get_by_number(self, db: AsyncSession, *, deal_number: int) -> Deal | None:
        result = await db.execute(select(Deal).where(Deal.deal_number == deal_number))
        return result.scalar_one_or_none()

    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        status: str | None = None,
        region: str | None = None,
        contract_type: str | None = None,
        contract_form: str | None = None,
        auction_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        seller_inn: str | None = None,
        buyer_inn: str | None = None,
        broker_seller_code: str | None = None,
        broker_buyer_code: str | None = None,
        product_name: str | None = None,
        sort_by: str | None = None,
        sort_desc: bool = False,
    ) -> tuple[list[Deal], int]:
        """Return filtered deals and total count."""
        stmt = select(Deal)
        count_stmt = select(Deal)

        conditions: list[Any] = []
        if search:
            like = f"%{search}%"
            conditions.append(
                Deal.product_name.ilike(like)
                | cast(Deal.deal_number, String).ilike(like)
                | Deal.region.ilike(like)
                | Deal.status.ilike(like)
            )
        if status:
            conditions.append(Deal.status == status)
        if region:
            conditions.append(Deal.region == region)
        if contract_type:
            conditions.append(Deal.contract_type == contract_type)
        if contract_form:
            conditions.append(Deal.contract_form == contract_form)
        if auction_type:
            conditions.append(Deal.auction_type == auction_type)
        if date_from:
            conditions.append(Deal.deal_date >= date_from)
        if date_to:
            conditions.append(Deal.deal_date <= date_to)
        if seller_inn:
            conditions.append(Deal.seller_inn == seller_inn)
        if buyer_inn:
            conditions.append(Deal.buyer_inn == buyer_inn)
        if broker_seller_code:
            conditions.append(Deal.broker_seller_code == broker_seller_code)
        if broker_buyer_code:
            conditions.append(Deal.broker_buyer_code == broker_buyer_code)
        if product_name:
            conditions.append(Deal.product_name.ilike(f"%{product_name}%"))

        if conditions:
            filter_expr = and_(*conditions)
            stmt = stmt.where(filter_expr)
            count_stmt = count_stmt.where(filter_expr)

        # total count
        from sqlalchemy import func
        if conditions:
            count_query = select(func.count()).select_from(Deal.__table__).where(and_(*conditions))
        else:
            count_query = select(func.count()).select_from(Deal.__table__)
        total = (await db.execute(count_query)).scalar_one()

        # sorting
        if sort_by:
            column = getattr(Deal, sort_by, None)
            if column is not None:
                stmt = stmt.order_by(column.desc() if sort_desc else column.asc())
        else:
            stmt = stmt.order_by(Deal.deal_date.desc(), Deal.deal_number.desc())

        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        items = list(result.scalars().all())
        return items, total


crud_deal = CRUDDeal(Deal)
