"""USD exchange rate model (TZ section 3: usd_rates)."""

from sqlalchemy import Date, Numeric
from sqlalchemy.orm import mapped_column

from app.db.base import Base


class UsdRate(Base):
    """Daily USD exchange rate (from usd_rates.csv): UZS per 1 USD."""

    __tablename__ = "usd_rates"

    date = mapped_column("rate_date", Date, primary_key=True)
    rate = mapped_column(Numeric(10, 2, asdecimal=False), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UsdRate(date={self.date!r}, rate={self.rate!r})>"
