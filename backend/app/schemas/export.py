"""Export schemas."""

from datetime import date

from pydantic import BaseModel


class ExportRequest(BaseModel):
    resource: str  # deals | contracts | brokers | participants | usd_rates
    format: str = "csv"  # csv | json
    date_from: date | None = None
    date_to: date | None = None
    filters: dict | None = None


class ExportResponse(BaseModel):
    export_id: str
    resource: str
    format: str
    download_url: str | None = None
    status: str = "pending"
    record_count: int | None = None
