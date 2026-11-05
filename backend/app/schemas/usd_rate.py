"""USD rate schemas."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class UsdRateBase(BaseModel):
    date: date
    rate: float


class UsdRateCreate(UsdRateBase):
    pass


class UsdRateOut(UsdRateBase):
    model_config = ConfigDict(from_attributes=True)
