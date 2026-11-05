"""Export endpoint: GET /api/v1/export/deals (CSV / Excel, streamed)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.v1.endpoints.deals import _export_limit, conditions_from
from app.services import export_service
from app.services import registry_service as rs

router = APIRouter()


@router.get(
    "/deals",
    summary="Download filtered deals as CSV or Excel (max EXPORT_MAX_ROWS)",
    dependencies=[Depends(_export_limit)],
)
async def export_deals(
    format: Literal["csv", "xlsx"] = "csv",
    start_date: date | None = None,
    end_date: date | None = None,
    status: Annotated[list[str] | None, Query()] = None,
    broker: str | None = Query(None, max_length=10),
    region: str | None = Query(None, max_length=100),
    search: str | None = Query(None, max_length=100),
    seller_inn: str | None = Query(None, max_length=9),
    buyer_inn: str | None = Query(None, max_length=9),
    contract_no: str | None = Query(None, max_length=50),
):
    names = await rs.resolve_search(search)
    cond = conditions_from(
        start_date, end_date, status, broker, region, search, seller_inn, buyer_inn, contract_no, names
    )
    return export_service.export_response(format, cond)
