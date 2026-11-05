"""Contract schemas."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class ContractBase(BaseModel):
    contract_number: str
    product_name: str | None = None
    tn_ved_code: str | None = None
    product_group: str | None = None
    product_category: str | None = None
    industry: str | None = None
    unit: str | None = None
    lot_size: float | None = None
    currency: str | None = None
    base_price: float | None = None
    deposit_percent: float | None = None
    delivery_basis: str | None = None
    region: str | None = None
    warehouse_address: str | None = None
    auction_type: str | None = None
    contract_type: str | None = None
    contract_form: str | None = None
    payment_term_days: int | None = None
    delivery_term_days: int | None = None
    packaging: str | None = None
    seller_inn: str | None = None
    registration_date: date | None = None
    valid_until: date | None = None


class ContractCreate(ContractBase):
    pass


class ContractUpdate(BaseModel):
    product_name: str | None = None
    tn_ved_code: str | None = None
    product_group: str | None = None
    product_category: str | None = None
    industry: str | None = None
    unit: str | None = None
    lot_size: float | None = None
    currency: str | None = None
    base_price: float | None = None
    deposit_percent: float | None = None
    delivery_basis: str | None = None
    region: str | None = None
    warehouse_address: str | None = None
    auction_type: str | None = None
    contract_type: str | None = None
    contract_form: str | None = None
    payment_term_days: int | None = None
    delivery_term_days: int | None = None
    packaging: str | None = None
    seller_inn: str | None = None
    registration_date: date | None = None
    valid_until: date | None = None


class ContractOut(ContractBase):
    model_config = ConfigDict(from_attributes=True)
