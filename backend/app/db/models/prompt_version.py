"""Prompt version model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PromptVersion(Base):
    """Versioned system prompt for the AI engine."""

    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Идентификатор версии")
    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="Версия prompts, например v1.0")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="Текст системного промпта")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="Активная версия")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="Кто создал")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PromptVersion(version={self.version!r}, active={self.is_active})>"
