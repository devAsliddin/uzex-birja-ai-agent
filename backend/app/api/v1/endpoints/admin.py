"""Admin endpoints (import, evaluation, prompts, audit)."""


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.services.import_service import ImportService

router = APIRouter()


@router.post("/import", summary="Import all CSV files into the database")
async def import_csv(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    service = ImportService()
    reports = await service.import_all(db)
    return {
        "status": "completed",
        "reports": [r.summary_line() for r in reports],
        "details": [
            {
                "file": r.file,
                "table": r.table,
                "total_rows": r.total_rows,
                "inserted": r.inserted,
                "updated": r.updated,
                "skipped": r.skipped,
                "invalid": r.invalid,
                "errors": r.errors,
            }
            for r in reports
        ],
    }


@router.post("/import/{file_name}", summary="Import a single CSV file")
async def import_single(file_name: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    service = ImportService()
    method = getattr(service, f"import_{file_name.replace('.csv','')}", None)
    if method is None:
        return {"status": "error", "message": f"Unknown file: {file_name}"}
    report = await method(db)
    await db.commit()
    return {"status": "completed", "report": report.summary_line()}
