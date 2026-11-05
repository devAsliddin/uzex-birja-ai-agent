"""Participant schemas."""


from pydantic import BaseModel, ConfigDict


class ParticipantBase(BaseModel):
    inn: str
    name: str
    region: str | None = None
    activity: str | None = None
    role: str | None = None
    vat_payer: bool | None = None


class ParticipantCreate(ParticipantBase):
    pass


class ParticipantUpdate(BaseModel):
    name: str | None = None
    region: str | None = None
    activity: str | None = None
    role: str | None = None
    vat_payer: bool | None = None


class ParticipantOut(ParticipantBase):
    model_config = ConfigDict(from_attributes=True)
