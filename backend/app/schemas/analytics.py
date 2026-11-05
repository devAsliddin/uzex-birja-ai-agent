"""Analytics schemas."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class ComparePeriods(BaseModel):
    period_from: date
    period_to: date
    deals_count: int
    total_amount: float | None = None
    total_volume: float | None = None
    avg_unit_price: float | None = None


class TopBrokers(BaseModel):
    broker_code: str
    broker_name: str
    deal_count: int
    total_amount: float | None = None


class TopProducts(BaseModel):
    product_name: str
    deal_count: int
    total_volume: float | None = None
    total_amount: float | None = None


class DatasetInformation(BaseModel):
    total_deals: int
    total_contracts: int
    total_participants: int
    total_brokers: int
    total_usd_rates: int
    date_from: date | None = None
    date_to: date | None = None
    currencies: list[str] = []
    statuses: list[str] = []


class AnalyticsSummary(BaseModel):
    deals: ComparePeriods
    top_brokers: list[TopBrokers] = []
    top_products: list[TopProducts] = []
    dataset: DatasetInformation

    model_config = ConfigDict(from_attributes=True)
