from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class TelegramCredentialsRequest(BaseModel):
    api_id: str = Field(..., min_length=1, max_length=32)
    api_hash: str = Field(..., min_length=1, max_length=255)


class TelegramPhoneRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=32)


class TelegramCodeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=16)


class TelegramPasswordRequest(BaseModel):
    password: str = Field(..., max_length=4096)


class TelegramSessionCopyRequest(BaseModel):
    source_account_id: str = Field(..., min_length=1, max_length=255)


class TelegramAuthStatusResponse(BaseModel):
    account_id: str
    connected: bool
    has_api_credentials: bool
    current_step: str
    next_step: str | None = None
    phone_number: str = ""
    message: str


class ShafaCookieInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    value: str = Field(default="", max_length=4096)
    domain: str = Field(default=".shafa.ua", max_length=255)
    path: str = Field(default="/", max_length=255)
    expires: float | int | None = None
    httpOnly: bool = False
    secure: bool = False
    sameSite: str | None = Field(default=None, max_length=32)


class ShafaStorageStateRequest(BaseModel):
    cookies: list[ShafaCookieInput] = Field(default_factory=list)
    origins: list[dict[str, Any]] = Field(default_factory=list)
    storage_state: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "ShafaStorageStateRequest":
        if self.storage_state is None and not self.cookies:
            raise ValueError("Provide either storage_state or cookies.")
        return self


class ShafaAuthStatusResponse(BaseModel):
    account_id: str
    connected: bool
    cookies_count: int = 0
    message: str
