"""Evaluation dataset model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvaluationDataset(Base):
    """A dataset of golden questions for AI evaluation."""

    __tablename__ = "evaluation_datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Идентификатор набора")
    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="Название набора")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Описание")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    questions: Mapped[list["EvaluationQuestion"]] = relationship(
        "EvaluationQuestion", back_populates="dataset", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvaluationDataset(id={self.id}, name={self.name!r})>"
