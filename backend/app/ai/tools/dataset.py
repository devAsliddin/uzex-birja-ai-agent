"""Read-only AI tool for dataset information."""


from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import BaseTool
from app.db.models.broker import Broker
from app.db.models.contract import Contract
from app.db.models.deal import Deal
from app.db.models.participant import Participant
from app.db.models.usd_rate import UsdRate


class GetDatasetInformationInput(BaseModel):
    pass


class GetDatasetInformationOutput(BaseModel):
    total_deals: int
    total_contracts: int
    total_participants: int
    total_brokers: int
    total_usd_rates: int
    date_from: str | None = None
    date_to: str | None = None
    statuses: list[str] = []


class GetDatasetInformation(BaseTool):
    name = "get_dataset_information"
    description = "Общая информация о наборе данных (количество записей, диапазон дат, статусы) (только чтение)."
    input_schema = GetDatasetInformationInput
    output_schema = GetDatasetInformationOutput

    async def _run(self, db: AsyncSession, input_data: GetDatasetInformationInput) -> GetDatasetInformationOutput:
        total_deals = await db.execute(select(func.count(Deal.deal_number)))
        total_contracts = await db.execute(select(func.count(Contract.contract_number)))
        total_participants = await db.execute(select(func.count(Participant.inn)))
        total_brokers = await db.execute(select(func.count(Broker.code)))
        total_rates = await db.execute(select(func.count(UsdRate.date)))
        date_from = await db.execute(select(func.min(Deal.deal_date)))
        date_to = await db.execute(select(func.max(Deal.deal_date)))
        statuses = await db.execute(select(Deal.status).where(Deal.status.is_not(None)).distinct())
        return GetDatasetInformationOutput(
            total_deals=int(total_deals.scalar_one() or 0),
            total_contracts=int(total_contracts.scalar_one() or 0),
            total_participants=int(total_participants.scalar_one() or 0),
            total_brokers=int(total_brokers.scalar_one() or 0),
            total_usd_rates=int(total_rates.scalar_one() or 0),
            date_from=date_from.scalar_one().isoformat() if date_from.scalar_one() else None,
            date_to=date_to.scalar_one().isoformat() if date_to.scalar_one() else None,
            statuses=[r[0] for r in statuses.all()],
        )
