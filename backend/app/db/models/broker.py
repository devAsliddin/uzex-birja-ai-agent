"""Broker model (TZ section 3: brokers)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Broker(Base):
    """Brokerage company (from brokers.csv)."""

    __tablename__ = "brokers"

    code: Mapped[str] = mapped_column("broker_code", String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str] = mapped_column(String(9), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Broker(code={self.code!r}, name={self.name!r})>"
