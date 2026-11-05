"""Participant model (TZ section 3: participants)."""

from sqlalchemy import Boolean, CheckConstraint, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Participant(Base):
    """Company participant - seller or buyer (from participants.csv)."""

    __tablename__ = "participants"
    __table_args__ = (
        CheckConstraint("role IN ('Продавец', 'Покупатель')", name="ck_participants_role"),
    )

    inn: Mapped[str] = mapped_column(String(9), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    activity: Mapped[str | None] = mapped_column("activity_type", String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vat_payer: Mapped[bool | None] = mapped_column(
        "is_vat_payer", Boolean, nullable=True, server_default=false()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Participant(inn={self.inn!r}, name={self.name!r})>"
