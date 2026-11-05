"""Evaluation run model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvaluationRun(Base):
    """A single evaluation run comparing a prompt version / model."""

    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Идентификатор прогона")
    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="Название прогона")
    prompt_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_versions.id"), nullable=True, comment="Версия промпта"
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False, comment="Используемая модель")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", comment="running / completed / failed")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON-сводка метрик")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="run", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvaluationRun(id={self.id}, status={self.status!r})>"
