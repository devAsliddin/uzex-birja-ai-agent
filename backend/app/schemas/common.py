"""Common schemas: error responses, pagination."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Single error detail."""

    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    """Consistent error response envelope."""

    model_config = ConfigDict(from_attributes=True)

    error: str
    code: str
    status_code: int
    details: dict | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginationParams(BaseModel):
    """Pagination query parameters."""

    page: int = Field(1, ge=1, description="Номер страницы (начиная с 1)")
    page_size: int = Field(50, ge=1, le=1000, description="Размер страницы")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list envelope."""

    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str = "1.0.0"
    database: str
    redis: str

    model_config = ConfigDict(from_attributes=True)
