"""Deal schemas."""

from datetime import date, time

from pydantic import BaseModel, ConfigDict


class DealBase(BaseModel):
    deal_number: int
    deal_date: date
    deal_time: time | None = None
    auction_type: str | None = None
    quantity: int | None = None
    amount: float | None = None
    start_price: float | None = None
    contract_number: str | None = None
    product_name: str | None = None
    lot_size: float | None = None
    unit: str | None = None
    region: str | None = None
    contract_type: str | None = None
    contract_form: str | None = None
    status: str | None = None
    seller_inn: str | None = None
    buyer_inn: str | None = None
    broker_seller_code: str | None = None
    broker_buyer_code: str | None = None
    payment_date: date | None = None
    delivery_date: date | None = None
    delivered_quantity: int | None = None


class DealCreate(DealBase):
    pass


class DealUpdate(BaseModel):
    deal_date: date | None = None
    deal_time: time | None = None
    auction_type: str | None = None
    quantity: int | None = None
    amount: float | None = None
    start_price: float | None = None
    contract_number: str | None = None
    product_name: str | None = None
    lot_size: float | None = None
    unit: str | None = None
    region: str | None = None
    contract_type: str | None = None
    contract_form: str | None = None
    status: str | None = None
    seller_inn: str | None = None
    buyer_inn: str | None = None
    broker_seller_code: str | None = None
    broker_buyer_code: str | None = None
    payment_date: date | None = None
    delivery_date: date | None = None
    delivered_quantity: int | None = None


class DealOut(DealBase):
    volume: float | None = None
    unit_price: float | None = None

    model_config = ConfigDict(from_attributes=True)
