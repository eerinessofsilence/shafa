from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shafa_logic.utils.proxy import DEFAULT_PROXY_MAX_ACCOUNTS, SUPPORTED_PROXY_SCHEMES

ProxyScheme = Literal["http", "https", "socks5"]
ProxyStatus = Literal["unknown", "healthy", "degraded", "failing", "disabled"]


class ProxyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scheme: ProxyScheme = Field(default="http")
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    username: str = Field(default="", max_length=255)
    password: str = Field(default="", max_length=4096)
    max_accounts: int = Field(default=DEFAULT_PROXY_MAX_ACCOUNTS, ge=1, le=100)
    enabled: bool = True
    notes: str = Field(default="", max_length=4096)

    @field_validator("name", "host", "username", "notes", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("password", mode="before")
    @classmethod
    def normalize_password(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @field_validator("scheme", mode="before")
    @classmethod
    def normalize_scheme(cls, value: Any) -> Any:
        normalized = str(value or "").strip().lower()
        if normalized not in SUPPORTED_PROXY_SCHEMES:
            raise ValueError("Unsupported proxy scheme.")
        return normalized


class ProxyCreate(ProxyBase):
    pass


class ProxyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scheme: ProxyScheme | None = None
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=4096)
    max_accounts: int | None = Field(default=None, ge=1, le=100)
    enabled: bool | None = None
    notes: str | None = Field(default=None, max_length=4096)

    @field_validator("name", "host", "username", "notes", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("password", mode="before")
    @classmethod
    def normalize_password(cls, value: Any) -> Any:
        if value is None:
            return None
        return str(value)

    @field_validator("scheme", mode="before")
    @classmethod
    def normalize_scheme(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = str(value or "").strip().lower()
        if normalized not in SUPPORTED_PROXY_SCHEMES:
            raise ValueError("Unsupported proxy scheme.")
        return normalized


class ProxySummary(BaseModel):
    id: str
    name: str
    scheme: ProxyScheme
    status: ProxyStatus
    assigned_accounts_count: int = 0
    max_accounts: int = DEFAULT_PROXY_MAX_ACCOUNTS
    enabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class ProxyRead(ProxyBase):
    id: str
    status: ProxyStatus = "unknown"
    assigned_accounts_count: int = 0
    total_requests: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    last_used_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

