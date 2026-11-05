"""Meta endpoints for frontend filters."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_read_db
from app.services import registry_service as rs

router = APIRouter()


@router.get("/filters", summary="Distinct statuses, regions, trade types and years")
async def filters(db: AsyncSession = Depends(get_read_db)):
    return await rs.meta_filters(db)
