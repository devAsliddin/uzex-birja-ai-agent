"""Participants endpoints."""


from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_user
from app.crud import crud_participant
from app.schemas.participant import ParticipantCreate, ParticipantOut

router = APIRouter()


@router.get("", response_model=dict, summary="List participants")
async def list_participants(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_user),
):
    skip = (page - 1) * page_size
    items = await crud_participant.get_multi(db, skip=skip, limit=page_size, search=search)
    return {
        "items": [ParticipantOut.model_validate(i).model_dump() for i in items],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{inn}", response_model=ParticipantOut, summary="Get participant by INN")
async def get_participant(inn: str, db: AsyncSession = Depends(get_db), _=Depends(require_user)):
    participant = await crud_participant.get_by_inn(db, inn=inn)
    if not participant:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("participant", inn)
    return participant


@router.post("", response_model=ParticipantOut, status_code=201, summary="Create a participant")
async def create_participant(
    participant_in: ParticipantCreate, db: AsyncSession = Depends(get_db), _=Depends(require_user)
):
    return await crud_participant.create(db, obj_in=participant_in)
