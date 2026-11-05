"""Deals endpoints (public read-only registry; writes require auth)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_read_db, require_user
from app.core.config import settings
from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.core.ratelimit import rate_limit
from app.crud import crud_deal
from app.schemas.deal import DealCreate, DealOut
from app.services import export_service
from app.services import registry_service as rs

router = APIRouter()
_export_limit = rate_limit("export", settings.rate_limit_export)


def conditions_from(
    start_date: date | None,
    end_date: date | None,
    status: list[str] | None,
    broker: str | None,
    region: str | None,
    search: str | None,
    seller_inn: str | None,
    buyer_inn: str | None,
    contract_no: str | None,
    product_names: list[str] | None = None,
):
    return rs.deal_conditions(
        start_date=start_date,
        end_date=end_date,
        statuses=rs.split_multi(status),
        broker=broker,
        region=region,
        search=search,
        seller_inn=seller_inn,
        buyer_inn=buyer_inn,
        contract_no=contract_no,
        product_names=product_names,
    )


@router.get("", summary="List deals (multi-parameter filter, pagination, export=csv|xlsx)")
async def list_deals(
    request: Request,
    start_date: date | None = Query(None, description="deal_date >= (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="deal_date <= (YYYY-MM-DD)"),
    status: Annotated[list[str] | None, Query(description="repeatable / comma separated")] = None,
    broker: str | None = Query(None, max_length=10, description="broker code, seller or buyer side"),
    region: str | None = Query(None, max_length=100),
    search: str | None = Query(None, max_length=100, description="product name or deal number"),
    seller_inn: str | None = Query(None, max_length=9),
    buyer_inn: str | None = Query(None, max_length=9),
    contract_no: str | None = Query(None, max_length=50),
    sort: Literal["deal_date", "deal_no", "amount", "quantity", "status"] = "deal_date",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1, le=1_000_000),
    limit: int = Query(50, ge=1, le=500),
    export: Literal["csv", "xlsx"] | None = Query(None, description="download instead of JSON"),
    with_status_counts: bool = Query(
        False, description="add status_counts for the current filters (excluding the status filter)"
    ),
    db: AsyncSession = Depends(get_read_db),
):
    names = await rs.resolve_search(search)
    cond = conditions_from(
        start_date, end_date, status, broker, region, search, seller_inn, buyer_inn, contract_no, names
    )
    if export:
        await _export_limit(request)
        return export_service.export_response(export, cond)
    sc = (
        conditions_from(start_date, end_date, None, broker, region, search, seller_inn, buyer_inn, contract_no, names)
        if with_status_counts
        else None
    )
    return await rs.list_deals(
        db, conditions=cond, page=page, limit=limit, sort=sort, desc=order == "desc", status_conditions=sc
    )


@router.get("/{deal_no}", summary="Full deal card (contract, parties, brokers, USD rate)")
async def get_deal(deal_no: int, db: AsyncSession = Depends(get_read_db)):
    card = await rs.deal_card(db, deal_no)
    if card is None:
        raise NotFoundError("deal", deal_no)
    return card


@router.post("", response_model=DealOut, status_code=201, summary="Create a deal (auth)")
async def create_deal(deal_in: DealCreate, db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    if await crud_deal.get_by_number(db, deal_number=deal_in.deal_number):
        raise AlreadyExistsError("deal", deal_in.deal_number)
    return await crud_deal.create(db, obj_in=deal_in)
