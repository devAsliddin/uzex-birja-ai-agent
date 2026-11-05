"""Contract model (TZ section 3: contracts)."""

from datetime import date
from typing import Optional

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _num(p: int, s: int) -> Numeric:
    return Numeric(p, s, asdecimal=False)


class Contract(Base):
    """Contract card (from contracts.csv)."""

    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint("currency IN ('Узбекский сум', 'Доллар США')", name="ck_contracts_currency"),
        CheckConstraint("contract_type IN ('Внутренний', 'Экспортный')", name="ck_contracts_ctype"),
        CheckConstraint(
            "contract_form IN ('Спот', 'Форвард', 'Фьючерс')", name="ck_contracts_cform"
        ),
    )

    contract_number: Mapped[str] = mapped_column("contract_no", String(50), primary_key=True)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    tn_ved_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    product_group: Mapped[str | None] = mapped_column(String(150), nullable=True)
    product_category: Mapped[str | None] = mapped_column(String(150), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(150), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    lot_size: Mapped[float] = mapped_column(_num(15, 3), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    base_price: Mapped[float] = mapped_column(_num(18, 2), nullable=False)
    deposit_percent: Mapped[float | None] = mapped_column(
        "deposit_percentage", _num(5, 2), nullable=True
    )
    delivery_basis: Mapped[str | None] = mapped_column(String(100), nullable=True)
    packaging: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    warehouse_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    auction_type: Mapped[str | None] = mapped_column("trade_type", String(50), nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contract_form: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_term_days: Mapped[int] = mapped_column("payment_days", Integer, nullable=False)
    delivery_term_days: Mapped[int] = mapped_column("delivery_days", Integer, nullable=False)
    seller_inn: Mapped[str | None] = mapped_column(
        String(9), ForeignKey("participants.inn"), nullable=True
    )
    registration_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)

    seller: Mapped[Optional["Participant"]] = relationship("Participant", lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Contract(contract_number={self.contract_number!r})>"
