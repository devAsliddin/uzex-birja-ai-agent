"""Deal model (TZ section 3: deals + 4 indexes)."""

from datetime import date, time
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_PK = BigInteger().with_variant(Integer, "sqlite")


def _num(p: int, s: int) -> Numeric:
    return Numeric(p, s, asdecimal=False)


class Deal(Base):
    """Exchange deal (from deals_*.csv)."""

    __tablename__ = "deals"
    __table_args__ = (
        Index("idx_deals_date_status", text("deal_date DESC"), "status"),
        Index("idx_deals_brokers", "seller_broker", "buyer_broker"),
        Index("idx_deals_participants", "seller_inn", "buyer_inn"),
        Index("idx_deals_contract", "contract_no"),
    )

    deal_number: Mapped[int] = mapped_column("deal_no", _PK, primary_key=True, autoincrement=False)
    deal_date: Mapped[date] = mapped_column(Date, nullable=False)
    deal_time: Mapped[time] = mapped_column(Time, nullable=False)
    auction_type: Mapped[str] = mapped_column("trade_type", String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(_num(18, 2), nullable=False)
    start_price: Mapped[float] = mapped_column(_num(18, 2), nullable=False)
    contract_number: Mapped[str | None] = mapped_column(
        "contract_no", String(50), ForeignKey("contracts.contract_no"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    lot_size: Mapped[float] = mapped_column(_num(15, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contract_form: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    seller_inn: Mapped[str | None] = mapped_column(
        String(9), ForeignKey("participants.inn"), nullable=True
    )
    buyer_inn: Mapped[str | None] = mapped_column(
        String(9), ForeignKey("participants.inn"), nullable=True
    )
    broker_seller_code: Mapped[str | None] = mapped_column(
        "seller_broker", String(10), ForeignKey("brokers.broker_code"), nullable=True
    )
    broker_buyer_code: Mapped[str | None] = mapped_column(
        "buyer_broker", String(10), ForeignKey("brokers.broker_code"), nullable=True
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivered_quantity: Mapped[int | None] = mapped_column("delivered_lots", Integer, nullable=True)

    # Forward relationships only (reverse collections would load 500k rows).
    contract: Mapped[Optional["Contract"]] = relationship("Contract", lazy="selectin")
    seller: Mapped[Optional["Participant"]] = relationship(
        "Participant", foreign_keys=[seller_inn], lazy="selectin"
    )
    buyer: Mapped[Optional["Participant"]] = relationship(
        "Participant", foreign_keys=[buyer_inn], lazy="selectin"
    )
    broker_seller: Mapped[Optional["Broker"]] = relationship(
        "Broker", foreign_keys=[broker_seller_code], lazy="selectin"
    )
    broker_buyer: Mapped[Optional["Broker"]] = relationship(
        "Broker", foreign_keys=[broker_buyer_code], lazy="selectin"
    )

    @property
    def volume(self) -> float | None:
        """Volume in units = quantity x lot size."""
        if self.quantity is None or self.lot_size is None:
            return None
        return self.quantity * self.lot_size

    @property
    def unit_price(self) -> float | None:
        """Price per unit = amount / (quantity x lot size)."""
        vol = self.volume
        if vol is None or vol == 0 or self.amount is None:
            return None
        return self.amount / vol

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Deal(deal_number={self.deal_number}, date={self.deal_date!r})>"
