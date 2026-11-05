"""Read-only AI tools for brokers."""


from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import MAX_RESULT_ROWS, BaseTool
from app.db.models.broker import Broker
from app.db.models.deal import Deal


class SearchBrokersInput(BaseModel):
    query: str | None = None
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class SearchBrokersOutput(BaseModel):
    brokers: list[dict]
    count: int


class SearchBrokers(BaseTool):
    name = "search_brokers"
    description = "Поиск брокеров по коду или наименованию (только чтение)."
    input_schema = SearchBrokersInput
    output_schema = SearchBrokersOutput

    async def _run(self, db: AsyncSession, input_data: SearchBrokersInput) -> SearchBrokersOutput:
        stmt = select(Broker)
        if input_data.query:
            like = f"%{input_data.query}%"
            stmt = stmt.where(Broker.name.ilike(like) | Broker.code.ilike(like))
        stmt = stmt.order_by(Broker.code).limit(input_data.limit)
        res = await db.execute(stmt)
        rows = res.scalars().all()
        brokers = [
            {
                "code": r.code,
                "name": r.name,
                "inn": r.inn,
                "region": r.region,
            }
            for r in rows
        ]
        return SearchBrokersOutput(brokers=brokers, count=len(brokers))


class GetBrokerDetailsInput(BaseModel):
    broker_code: str = Field(..., description="Код брокера, например BK001")


class GetBrokerDetailsOutput(BaseModel):
    broker: dict | None


class GetBrokerDetails(BaseTool):
    name = "get_broker_details"
    description = "Детали брокера по коду (только чтение)."
    input_schema = GetBrokerDetailsInput
    output_schema = GetBrokerDetailsOutput

    async def _run(self, db: AsyncSession, input_data: GetBrokerDetailsInput) -> GetBrokerDetailsOutput:
        res = await db.execute(select(Broker).where(Broker.code == input_data.broker_code))
        broker = res.scalar_one_or_none()
        if broker is None:
            return GetBrokerDetailsOutput(broker=None)
        return GetBrokerDetailsOutput(
            broker={
                "code": broker.code,
                "name": broker.name,
                "inn": broker.inn,
                "region": broker.region,
            }
        )


class GetBrokerStatisticsInput(BaseModel):
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class GetBrokerStatisticsOutput(BaseModel):
    brokers: list[dict]


class GetBrokerStatistics(BaseTool):
    name = "get_broker_statistics"
    description = "Статистика по брокерам (количество сделок, сумма) (только чтение)."
    input_schema = GetBrokerStatisticsInput
    output_schema = GetBrokerStatisticsOutput

    async def _run(self, db: AsyncSession, input_data: GetBrokerStatisticsInput) -> GetBrokerStatisticsOutput:
        stmt = (
            select(
                Deal.broker_seller_code,
                func.count(Deal.deal_number).label("deal_count"),
                func.sum(Deal.amount).label("total_amount"),
            )
            .where(Deal.broker_seller_code.is_not(None))
            .group_by(Deal.broker_seller_code)
            .order_by(func.count(Deal.deal_number).desc())
            .limit(input_data.limit)
        )
        res = await db.execute(stmt)
        rows = res.mappings().all()
        out = []
        for r in rows:
            broker_res = await db.execute(select(Broker).where(Broker.code == r["broker_seller_code"]))
            broker = broker_res.scalar_one_or_none()
            out.append(
                {
                    "broker_code": r["broker_seller_code"],
                    "broker_name": broker.name if broker else None,
                    "deal_count": int(r["deal_count"] or 0),
                    "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
                }
            )
        return GetBrokerStatisticsOutput(brokers=out)


class GetTopBrokersTool(BaseTool):
    name = "get_top_brokers"
    description = "Топ брокеров по количеству сделок (только чтение)."
    input_schema = GetBrokerStatisticsInput
    output_schema = GetBrokerStatisticsOutput

    async def _run(self, db: AsyncSession, input_data: GetBrokerStatisticsInput) -> GetBrokerStatisticsOutput:
        return await GetBrokerStatistics()._run(db, input_data)
