"""Statistics schemas."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class BrokerStatistic(BaseModel):
    broker_code: str
    broker_name: str
    deal_count: int
    total_amount: float | None = None
    total_volume: float | None = None


class ParticipantStatistic(BaseModel):
    inn: str
    name: str
    role: str | None = None
    deal_count: int
    total_amount: float | None = None


class ProductStatistic(BaseModel):
    product_name: str
    deal_count: int
    total_volume: float | None = None
    total_amount: float | None = None


class RegionStatistic(BaseModel):
    region: str
    deal_count: int
    total_amount: float | None = None


class IndustryStatistic(BaseModel):
    industry: str
    deal_count: int
    total_amount: float | None = None


class StatusStatistic(BaseModel):
    status: str
    deal_count: int


class PeriodStatistic(BaseModel):
    period: str
    deal_count: int
    total_amount: float | None = None
    total_volume: float | None = None


class DealStatistics(BaseModel):
    total_deals: int
    total_amount: float | None = None
    total_volume: float | None = None
    by_broker: list[BrokerStatistic] = []
    by_participant: list[ParticipantStatistic] = []
    by_product: list[ProductStatistic] = []
    by_region: list[RegionStatistic] = []
    by_industry: list[IndustryStatistic] = []
    by_status: list[StatusStatistic] = []
    by_period: list[PeriodStatistic] = []


class ExchangeRateOut(BaseModel):
    date: date
    rate: float
    available: bool = True

    model_config = ConfigDict(from_attributes=True)
