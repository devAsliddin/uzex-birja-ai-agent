"""Message model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Message(Base):
    """Message within an AI conversation."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Идентификатор сообщения")
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, comment="Беседа"
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, comment="Роль: user / assistant / tool")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="Содержимое сообщения")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Message(id={self.id}, role={self.role!r})>"
