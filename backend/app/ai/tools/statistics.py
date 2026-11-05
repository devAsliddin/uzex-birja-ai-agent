"""Read-only AI tools for general statistics."""


from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import MAX_RESULT_ROWS, BaseTool
from app.db.models.contract import Contract
from app.db.models.deal import Deal


class GetDealStatisticsInput(BaseModel):
    pass


class GetDealStatisticsOutput(BaseModel):
    total_deals: int
    total_amount: float | None = None


class GetDealStatistics(BaseTool):
    name = "get_deal_statistics"
    description = "Общая статистика по сделкам (только чтение)."
    input_schema = GetDealStatisticsInput
    output_schema = GetDealStatisticsOutput

    async def _run(self, db: AsyncSession, input_data: GetDealStatisticsInput) -> GetDealStatisticsOutput:
        total = await db.execute(select(func.count(Deal.deal_number)))
        amount = await db.execute(select(func.sum(Deal.amount)))
        amt = amount.scalar_one()
        return GetDealStatisticsOutput(
            total_deals=int(total.scalar_one() or 0),
            total_amount=float(amt) if amt is not None else None,
        )


class GetProductStatisticsInput(BaseModel):
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class GetProductStatisticsOutput(BaseModel):
    products: list[dict]


class GetProductStatistics(BaseTool):
    name = "get_product_statistics"
    description = "Статистика по товарам (только чтение)."
    input_schema = GetProductStatisticsInput
    output_schema = GetProductStatisticsOutput

    async def _run(self, db: AsyncSession, input_data: GetProductStatisticsInput) -> GetProductStatisticsOutput:
        stmt = (
            select(
                Deal.product_name,
                func.count(Deal.deal_number).label("deal_count"),
                func.sum(Deal.amount).label("total_amount"),
            )
            .where(Deal.product_name.is_not(None))
            .group_by(Deal.product_name)
            .order_by(func.count(Deal.deal_number).desc())
            .limit(input_data.limit)
        )
        res = await db.execute(stmt)
        rows = res.mappings().all()
        return GetProductStatisticsOutput(
            products=[
                {
                    "product_name": r["product_name"],
                    "deal_count": int(r["deal_count"] or 0),
                    "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
                }
                for r in rows
            ]
        )


class GetRegionStatisticsInput(BaseModel):
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class GetRegionStatisticsOutput(BaseModel):
    regions: list[dict]


class GetRegionStatistics(BaseTool):
    name = "get_region_statistics"
    description = "Статистика по регионам (только чтение)."
    input_schema = GetRegionStatisticsInput
    output_schema = GetRegionStatisticsOutput

    async def _run(self, db: AsyncSession, input_data: GetRegionStatisticsInput) -> GetRegionStatisticsOutput:
        stmt = (
            select(
                Deal.region,
                func.count(Deal.deal_number).label("deal_count"),
                func.sum(Deal.amount).label("total_amount"),
            )
            .where(Deal.region.is_not(None))
            .group_by(Deal.region)
            .order_by(func.count(Deal.deal_number).desc())
            .limit(input_data.limit)
        )
        res = await db.execute(stmt)
        rows = res.mappings().all()
        return GetRegionStatisticsOutput(
            regions=[
                {
                    "region": r["region"],
                    "deal_count": int(r["deal_count"] or 0),
                    "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
                }
                for r in rows
            ]
        )


class GetIndustryStatisticsInput(BaseModel):
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class GetIndustryStatisticsOutput(BaseModel):
    industries: list[dict]


class GetIndustryStatistics(BaseTool):
    name = "get_industry_statistics"
    description = "Статистика по отраслям (только чтение)."
    input_schema = GetIndustryStatisticsInput
    output_schema = GetIndustryStatisticsOutput

    async def _run(self, db: AsyncSession, input_data: GetIndustryStatisticsInput) -> GetIndustryStatisticsOutput:
        stmt = (
            select(
                Contract.industry,
                func.count(Deal.deal_number).label("deal_count"),
                func.sum(Deal.amount).label("total_amount"),
            )
            .join(Deal, Deal.contract_number == Contract.contract_number, isouter=True)
            .where(Contract.industry.is_not(None))
            .group_by(Contract.industry)
            .order_by(func.count(Deal.deal_number).desc())
            .limit(input_data.limit)
        )
        res = await db.execute(stmt)
        rows = res.mappings().all()
        return GetIndustryStatisticsOutput(
            industries=[
                {
                    "industry": r["industry"],
                    "deal_count": int(r["deal_count"] or 0),
                    "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
                }
                for r in rows
            ]
        )


class GetTopProductsTool(BaseTool):
    name = "get_top_products"
    description = "Топ товаров по количеству сделок (только чтение)."
    input_schema = GetProductStatisticsInput
    output_schema = GetProductStatisticsOutput

    async def _run(self, db: AsyncSession, input_data: GetProductStatisticsInput) -> GetProductStatisticsOutput:
        return await GetProductStatistics()._run(db, input_data)
