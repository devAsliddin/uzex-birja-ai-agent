"""Evaluation result model."""


from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvaluationResult(Base):
    """Result of evaluating a single question in a run."""

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Идентификатор результата")
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id"), nullable=False, comment="Прогон"
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_questions.id"), nullable=False, comment="Вопрос"
    )
    actual_answer: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Полученный ответ")
    actual_tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON вызовов инструментов")
    actual_db_result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON результата из БД")
    passed: Mapped[bool] = mapped_column(Integer, nullable=False, default=0, comment="Пройден")
    scores: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON метрик точности")
    errors: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON ошибок")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Задержка, мс")
    token_usage: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON использование токенов")

    run: Mapped["EvaluationRun"] = relationship("EvaluationRun", back_populates="results", lazy="selectin")
    question: Mapped["EvaluationQuestion"] = relationship(
        "EvaluationQuestion", back_populates="results", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvaluationResult(id={self.id}, passed={self.passed})>"
