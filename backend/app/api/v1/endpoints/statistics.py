"""Statistics endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_user
from app.services.statistics_service import (
    get_broker_statistics,
    get_deal_statistics,
    get_industry_statistics,
    get_participant_statistics,
    get_period_statistics,
    get_product_statistics,
    get_region_statistics,
    get_status_statistics,
)

router = APIRouter()


@router.get("/deals", response_model=dict, summary="Deal statistics")
async def deals_stats(db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await get_deal_statistics(db)


@router.get("/brokers", response_model=dict, summary="Broker statistics")
async def brokers_stats(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await get_broker_statistics(db, limit=limit)


@router.get("/participants", response_model=dict, summary="Participant statistics")
async def participants_stats(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await get_participant_statistics(db, limit=limit)


@router.get("/products", response_model=dict, summary="Product statistics")
async def products_stats(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await get_product_statistics(db, limit=limit)


@router.get("/regions", response_model=dict, summary="Region statistics")
async def regions_stats(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await get_region_statistics(db, limit=limit)


@router.get("/industries", response_model=dict, summary="Industry statistics")
async def industries_stats(limit: int = Query(50, ge=1, le=500), db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await get_industry_statistics(db, limit=limit)


@router.get("/statuses", response_model=dict, summary="Status statistics")
async def statuses_stats(db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await get_status_statistics(db)


@router.get("/periods", response_model=dict, summary="Period statistics")
async def periods_stats(period: str = Query("month"), db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    return await get_period_statistics(db, period=period)
