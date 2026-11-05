"""Brokers endpoints (public read-only; writes require auth)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_read_db, require_user
from app.core.exceptions import NotFoundError
from app.crud import crud_broker
from app.schemas.broker import BrokerCreate, BrokerOut
from app.services import registry_service as rs

router = APIRouter()


@router.get("", summary="Brokers registry with rating (turnover rank + deal count)")
async def list_brokers(
    page: int = Query(1, ge=1, le=100_000),
    limit: int = Query(50, ge=1, le=200),
    region: str | None = Query(None, max_length=100),
    search: str | None = Query(None, max_length=100, description="name, code or INN"),
    sort: Literal["rating", "name", "deals", "turnover"] = "rating",
    db: AsyncSession = Depends(get_read_db),
):
    return await rs.list_brokers(db, page=page, limit=limit, region=region, search=search, sort=sort)


@router.get("/{code}", summary="Broker profile, deal statistics and turnover")
async def get_broker(code: str, db: AsyncSession = Depends(get_read_db)):
    profile = await rs.broker_profile(db, code.upper())
    if profile is None:
        raise NotFoundError("broker", code)
    return profile


@router.post("", response_model=BrokerOut, status_code=201, summary="Create a broker (auth)")
async def create_broker(broker_in: BrokerCreate, db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await crud_broker.create(db, obj_in=broker_in)
