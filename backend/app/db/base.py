"""Declarative base for SQLAlchemy models."""

from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all ORM models.

    Provides async attribute loading and a shared registry.
    """

    __abstract__ = True

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        cls_name = self.__class__.__name__
        return f"<{cls_name}(id={getattr(self, 'id', None)})>"
