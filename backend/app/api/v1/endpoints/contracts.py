"""Contracts endpoints."""


from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_user
from app.crud import crud_contract
from app.schemas.contract import ContractCreate, ContractOut

router = APIRouter()


@router.get("", response_model=dict, summary="List contracts")
async def list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_user),
):
    skip = (page - 1) * page_size
    items = await crud_contract.get_multi(db, skip=skip, limit=page_size, search=search)
    return {
        "items": [ContractOut.model_validate(i).model_dump() for i in items],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{contract_number}", response_model=ContractOut, summary="Get contract by number")
async def get_contract(contract_number: str, db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    contract = await crud_contract.get_by_number(db, contract_number=contract_number)
    if not contract:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("contract", contract_number)
    return contract


@router.post("", response_model=ContractOut, status_code=201, summary="Create a contract")
async def create_contract(contract_in: ContractCreate, db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await crud_contract.create(db, obj_in=contract_in)
