"""Audit log model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """Immutable audit trail for security-relevant actions."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Идентификатор записи")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Пользователь")
    action: Mapped[str] = mapped_column(String(128), nullable=False, comment="Действие")
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Тип ресурса")
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="Идентификатор ресурса")
    details: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Детали (JSON)")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="IP-адрес")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog(id={self.id}, action={self.action!r})>"
