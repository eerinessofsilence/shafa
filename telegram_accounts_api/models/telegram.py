from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class SendMessageRequest(BaseModel):
    peer: str = Field(..., min_length=1, description="Username, phone, or numeric Telegram peer ID")
    text: str | None = Field(default=None, min_length=1)
    template_id: str | None = None
    template_variables: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_text_or_template(self) -> "SendMessageRequest":
        if not self.text and not self.template_id:
            raise ValueError("Either text or template_id must be provided.")
        return self


class TelegramMessageResponse(BaseModel):
    account_id: str
    peer: str
    message_id: int
    text: str
    sent_at: str | None = None


class TelegramDialogResponse(BaseModel):
    id: int
    title: str
    username: str | None = None
    unread_count: int = 0
    is_user: bool = False
    is_group: bool = False
    is_channel: bool = False


class TelegramUserResponse(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    is_bot: bool = False
    is_self: bool = False

