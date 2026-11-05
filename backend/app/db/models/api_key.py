"""API key model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ApiKey(Base):
    """API key for service-to-service authentication."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, comment="Идентификатор ключа")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Название ключа")
    key_hash: Mapped[str] = mapped_column(String(256), nullable=False, comment="Хэш ключа")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, comment="Префикс ключа для идентификации")
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, comment="Владелец ключа"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="Активен")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="api_keys", lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ApiKey(id={self.id}, name={self.name!r})>"
