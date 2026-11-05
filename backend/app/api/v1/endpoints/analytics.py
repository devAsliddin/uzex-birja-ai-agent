"""Analytics endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_read_db, require_user
from app.services import registry_service as rs
from app.services.statistics_service import compare_periods

router = APIRouter()


@router.get("/summary", summary="Dashboard: turnover, deals, USD rate, dynamics, regions, categories")
async def summary(
    year: int | None = Query(None, ge=2000, le=2100),
    currency: Literal["UZS", "USD", "uzs", "usd"] = "UZS",
    db: AsyncSession = Depends(get_read_db),
):
    return await rs.analytics_summary(db, year, currency)


@router.get("/compare", response_model=dict, summary="Compare two periods (auth)")
async def compare(
    period_from: date = Query(...),
    period_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_user),
):
    return await compare_periods(db, period_from, period_to)
