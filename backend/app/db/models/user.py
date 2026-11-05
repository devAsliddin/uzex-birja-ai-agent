"""User model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """Registered application user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, comment="Идентификатор пользователя")
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False, comment="Email")
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False, comment="Имя пользователя")
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False, comment="Хэш пароля")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="user", comment="Роль: admin / user / analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="Активен")
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="Суперпользователь")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="user", lazy="selectin")
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User(id={self.id}, username={self.username!r}, role={self.role!r})>"
