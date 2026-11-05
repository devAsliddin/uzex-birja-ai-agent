"""Authentication token schemas."""


from typing import Any

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str | None = None
    type: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: dict[str, Any]
    tokens: Token


class RefreshRequest(BaseModel):
    refresh_token: str
