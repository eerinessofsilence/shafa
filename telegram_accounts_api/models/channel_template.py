from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ChannelTemplateType = Literal["clothes", "shoes"]


class ResolvedTelegramChannel(BaseModel):
    channel_id: int
    title: str
    alias: str = "main"


class ChannelTemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: ChannelTemplateType = "clothes"
    links: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Any) -> Any:
        if value is None:
            return "clothes"
        normalized = str(value).strip().lower()
        return "shoes" if normalized == "sneakers" else normalized

    @field_validator("links", mode="before")
    @classmethod
    def normalize_links(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("links must be a list")
        return [str(item).strip() for item in value if str(item).strip()]


class ChannelTemplateCreate(ChannelTemplateBase):
    links: list[str] = Field(default_factory=list, min_length=1)


class ChannelTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: ChannelTemplateType | None = None
    links: list[str] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return "shoes" if normalized == "sneakers" else normalized

    @field_validator("links", mode="before")
    @classmethod
    def normalize_links(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("links must be a list")
        return [str(item).strip() for item in value if str(item).strip()]


class ChannelTemplateRead(ChannelTemplateBase):
    id: str
    account_id: str | None = None
    resolved_channels: list[ResolvedTelegramChannel] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ChannelTemplateSummary(BaseModel):
    id: str
    name: str
    type: ChannelTemplateType = "clothes"
    links: list[str] = Field(default_factory=list)
    resolved_channels: list[ResolvedTelegramChannel] = Field(default_factory=list)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Any) -> Any:
        if value is None:
            return "clothes"
        normalized = str(value).strip().lower()
        return "shoes" if normalized == "sneakers" else normalized


class ChannelTemplateResolveRequest(BaseModel):
    links: list[str] = Field(default_factory=list, min_length=1)

    @field_validator("links", mode="before")
    @classmethod
    def normalize_links(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("links must be a list")
        return [str(item).strip() for item in value if str(item).strip()]
