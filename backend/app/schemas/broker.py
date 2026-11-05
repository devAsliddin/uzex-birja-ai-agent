"""Broker schemas."""


from pydantic import BaseModel, ConfigDict


class BrokerBase(BaseModel):
    code: str
    name: str
    inn: str | None = None
    region: str | None = None


class BrokerCreate(BrokerBase):
    pass


class BrokerUpdate(BaseModel):
    name: str | None = None
    inn: str | None = None
    region: str | None = None


class BrokerOut(BrokerBase):
    model_config = ConfigDict(from_attributes=True)
