from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator
from telegram_accounts_api.models.channel_template import ChannelTemplateSummary

AccountStatus = Literal["started", "stopped"]


class AccountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone: str = Field(default="", max_length=32)
    path: str = Field(default="")
    branch: str = Field(default="main")
    open_browser: bool = False
    timer_minutes: int = Field(default=5, ge=1, le=1440)
    channel_links: list[str] = Field(default_factory=list)

    @field_validator("name", "phone", "path", "branch", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("channel_links", mode="before")
    @classmethod
    def normalize_links(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("channel_links must be a list")
        return [str(item).strip() for item in value if str(item).strip()]


class AccountCreate(AccountBase):
    pass


class AccountUpdateStatus(BaseModel):
    status: AccountStatus


class AccountRead(AccountBase):
    id: str
    status: AccountStatus = "stopped"
    last_run: str | None = None
    errors: int = 0
    telegram_session_exists: bool = False
    api_credentials_configured: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    channel_templates: list[ChannelTemplateSummary] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)
