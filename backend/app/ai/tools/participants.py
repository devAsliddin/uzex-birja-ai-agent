"""Read-only AI tools for participants."""


from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import MAX_RESULT_ROWS, BaseTool
from app.db.models.deal import Deal
from app.db.models.participant import Participant


class SearchParticipantsInput(BaseModel):
    query: str | None = None
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class SearchParticipantsOutput(BaseModel):
    participants: list[dict]
    count: int


class SearchParticipants(BaseTool):
    name = "search_participants"
    description = "Поиск участников (компаний) по ИНН или наименованию (только чтение)."
    input_schema = SearchParticipantsInput
    output_schema = SearchParticipantsOutput

    async def _run(self, db: AsyncSession, input_data: SearchParticipantsInput) -> SearchParticipantsOutput:
        stmt = select(Participant)
        if input_data.query:
            like = f"%{input_data.query}%"
            stmt = stmt.where(Participant.name.ilike(like) | Participant.inn.ilike(like))
        stmt = stmt.order_by(Participant.inn).limit(input_data.limit)
        res = await db.execute(stmt)
        rows = res.scalars().all()
        participants = [
            {
                "inn": r.inn,
                "name": r.name,
                "region": r.region,
                "activity": r.activity,
                "role": r.role,
                "vat_payer": r.vat_payer,
            }
            for r in rows
        ]
        return SearchParticipantsOutput(participants=participants, count=len(participants))


class GetParticipantDetailsInput(BaseModel):
    inn: str = Field(..., description="ИНН участника")


class GetParticipantDetailsOutput(BaseModel):
    participant: dict | None


class GetParticipantDetails(BaseTool):
    name = "get_participant_details"
    description = "Детали участника по ИНН (только чтение)."
    input_schema = GetParticipantDetailsInput
    output_schema = GetParticipantDetailsOutput

    async def _run(self, db: AsyncSession, input_data: GetParticipantDetailsInput) -> GetParticipantDetailsOutput:
        res = await db.execute(select(Participant).where(Participant.inn == input_data.inn))
        participant = res.scalar_one_or_none()
        if participant is None:
            return GetParticipantDetailsOutput(participant=None)
        return GetParticipantDetailsOutput(
            participant={
                "inn": participant.inn,
                "name": participant.name,
                "region": participant.region,
                "activity": participant.activity,
                "role": participant.role,
                "vat_payer": participant.vat_payer,
            }
        )


class GetParticipantStatisticsInput(BaseModel):
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class GetParticipantStatisticsOutput(BaseModel):
    participants: list[dict]


class GetParticipantStatistics(BaseTool):
    name = "get_participant_statistics"
    description = "Статистика по участникам (количество сделок, сумма) (только чтение)."
    input_schema = GetParticipantStatisticsInput
    output_schema = GetParticipantStatisticsOutput

    async def _run(self, db: AsyncSession, input_data: GetParticipantStatisticsInput) -> GetParticipantStatisticsOutput:
        seller = (
            select(
                Deal.seller_inn.label("inn"),
                func.count(Deal.deal_number).label("deal_count"),
                func.sum(Deal.amount).label("total_amount"),
            )
            .where(Deal.seller_inn.is_not(None))
            .group_by(Deal.seller_inn)
        )
        buyer = (
            select(
                Deal.buyer_inn.label("inn"),
                func.count(Deal.deal_number).label("deal_count"),
                func.sum(Deal.amount).label("total_amount"),
            )
            .where(Deal.buyer_inn.is_not(None))
            .group_by(Deal.buyer_inn)
        )
        combined = seller.union_all(buyer).alias("combined")
        stmt = (
            select(
                combined.c.inn,
                func.sum(combined.c.deal_count).label("deal_count"),
                func.sum(combined.c.total_amount).label("total_amount"),
            )
            .group_by(combined.c.inn)
            .order_by(func.sum(combined.c.deal_count).desc())
            .limit(input_data.limit)
        )
        res = await db.execute(stmt)
        rows = res.mappings().all()
        out = []
        for r in rows:
            part_res = await db.execute(select(Participant).where(Participant.inn == r["inn"]))
            part = part_res.scalar_one_or_none()
            out.append(
                {
                    "inn": r["inn"],
                    "name": part.name if part else None,
                    "role": part.role if part else None,
                    "deal_count": int(r["deal_count"] or 0),
                    "total_amount": float(r["total_amount"]) if r["total_amount"] is not None else None,
                }
            )
        return GetParticipantStatisticsOutput(participants=out)
