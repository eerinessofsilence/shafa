from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MessageTemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name", "content", "description", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class MessageTemplateCreate(MessageTemplateBase):
    id: str | None = Field(default=None, max_length=64)


class MessageTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name", "content", "description", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class MessageTemplateRead(MessageTemplateBase):
    id: str
    created_at: datetime
    updated_at: datetime

