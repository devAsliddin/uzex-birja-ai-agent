"""Evaluation question model."""


from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvaluationQuestion(Base):
    """A single golden question with expected results."""

    __tablename__ = "evaluation_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Идентификатор вопроса")
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_datasets.id"), nullable=False, comment="Набор вопросов"
    )
    question: Mapped[str] = mapped_column(Text, nullable=False, comment="Текст вопроса")
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ru", comment="ru / uz")
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Ожидаемый ответ")
    expected_tool_calls: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON-список ожидаемых вызовов инструментов"
    )
    expected_db_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Ожидаемый результат из БД (JSON)"
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Категория")
    is_unknown: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0, comment="1 — вопрос, на который ответ 'не знаю'"
    )
    difficulty: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="Сложность")

    dataset: Mapped["EvaluationDataset"] = relationship("EvaluationDataset", back_populates="questions", lazy="selectin")
    results: Mapped[list["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="question", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvaluationQuestion(id={self.id})>"
