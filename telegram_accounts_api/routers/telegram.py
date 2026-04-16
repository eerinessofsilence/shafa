from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from telegram_accounts_api.dependencies import get_telegram_service
from telegram_accounts_api.models.telegram import (
    SendMessageRequest,
    TelegramDialogResponse,
    TelegramMessageResponse,
    TelegramUserResponse,
)
from telegram_accounts_api.services.telegram_service import TelegramService

router = APIRouter(prefix="/accounts/{account_id}", tags=["telegram"])


@router.post("/messages", response_model=TelegramMessageResponse)
async def send_message(
    account_id: str,
    payload: SendMessageRequest,
    service: TelegramService = Depends(get_telegram_service),
) -> TelegramMessageResponse:
    return await service.send_message(account_id, payload)


@router.get("/dialogs", response_model=list[TelegramDialogResponse])
async def get_dialogs(
    account_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    service: TelegramService = Depends(get_telegram_service),
) -> list[TelegramDialogResponse]:
    return await service.get_dialogs(account_id, limit)


@router.get("/users/{user_ref}", response_model=TelegramUserResponse)
async def get_user(
    account_id: str,
    user_ref: str,
    service: TelegramService = Depends(get_telegram_service),
) -> TelegramUserResponse:
    return await service.get_user(account_id, user_ref)
