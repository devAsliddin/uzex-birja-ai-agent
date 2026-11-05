"""Exchange rates endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_user
from app.crud import crud_usd_rate
from app.schemas.usd_rate import UsdRateOut

router = APIRouter()


@router.get("", response_model=dict, summary="List USD exchange rates")
async def list_rates(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_user),
):
    skip = (page - 1) * page_size
    items = await crud_usd_rate.get_multi(db, skip=skip, limit=page_size)
    return {
        "items": [UsdRateOut.model_validate(i).model_dump() for i in items],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{rate_date}", response_model=UsdRateOut, summary="Get USD rate by date")
async def get_rate(rate_date: date, db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    rate = await crud_usd_rate.get_by_date(db, date=rate_date)
    if not rate:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("usd_rate", rate_date.isoformat())
    return rate
