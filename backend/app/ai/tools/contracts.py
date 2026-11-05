"""Read-only AI tools for contracts."""


from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import MAX_RESULT_ROWS, BaseTool
from app.db.models.contract import Contract


class SearchContractsInput(BaseModel):
    query: str | None = None
    limit: int = Field(50, ge=1, le=MAX_RESULT_ROWS)


class SearchContractsOutput(BaseModel):
    contracts: list[dict]
    count: int


class SearchContracts(BaseTool):
    name = "search_contracts"
    description = "Поиск контрактов по номеру или наименованию товара (только чтение)."
    input_schema = SearchContractsInput
    output_schema = SearchContractsOutput

    async def _run(self, db: AsyncSession, input_data: SearchContractsInput) -> SearchContractsOutput:
        stmt = select(Contract)
        if input_data.query:
            like = f"%{input_data.query}%"
            stmt = stmt.where(
                Contract.contract_number.ilike(like) | Contract.product_name.ilike(like)
            )
        stmt = stmt.order_by(Contract.contract_number).limit(input_data.limit)
        res = await db.execute(stmt)
        rows = res.scalars().all()
        contracts = [
            {
                "contract_number": r.contract_number,
                "product_name": r.product_name,
                "currency": r.currency,
                "industry": r.industry,
                "region": r.region,
                "seller_inn": r.seller_inn,
            }
            for r in rows
        ]
        return SearchContractsOutput(contracts=contracts, count=len(contracts))


class GetContractDetailsInput(BaseModel):
    contract_number: str = Field(..., description="Номер контракта")


class GetContractDetailsOutput(BaseModel):
    contract: dict | None


class GetContractDetails(BaseTool):
    name = "get_contract_details"
    description = "Детали контракта по номеру контракта (только чтение)."
    input_schema = GetContractDetailsInput
    output_schema = GetContractDetailsOutput

    async def _run(self, db: AsyncSession, input_data: GetContractDetailsInput) -> GetContractDetailsOutput:
        res = await db.execute(
            select(Contract).where(Contract.contract_number == input_data.contract_number)
        )
        contract = res.scalar_one_or_none()
        if contract is None:
            return GetContractDetailsOutput(contract=None)
        return GetContractDetailsOutput(
            contract={
                "contract_number": contract.contract_number,
                "product_name": contract.product_name,
                "tn_ved_code": contract.tn_ved_code,
                "industry": contract.industry,
                "unit": contract.unit,
                "lot_size": contract.lot_size,
                "currency": contract.currency,
                "base_price": float(contract.base_price) if contract.base_price is not None else None,
                "region": contract.region,
                "contract_type": contract.contract_type,
                "contract_form": contract.contract_form,
                "seller_inn": contract.seller_inn,
                "registration_date": contract.registration_date.isoformat() if contract.registration_date else None,
                "valid_until": contract.valid_until.isoformat() if contract.valid_until else None,
            }
        )
