from __future__ import annotations

from fastapi import APIRouter, Depends, status

from telegram_accounts_api.dependencies import get_auth_service
from telegram_accounts_api.models.auth import (
    ShafaAuthStatusResponse,
    ShafaStorageStateRequest,
    TelegramAuthStatusResponse,
    TelegramCodeRequest,
    TelegramCredentialsRequest,
    TelegramPasswordRequest,
    TelegramPhoneRequest,
)
from telegram_accounts_api.services.auth_service import AccountAuthService

router = APIRouter(prefix="/accounts/{account_id}/auth", tags=["auth"])


@router.get("/telegram", response_model=TelegramAuthStatusResponse)
async def get_telegram_status(
    account_id: str,
    service: AccountAuthService = Depends(get_auth_service),
) -> TelegramAuthStatusResponse:
    return await service.get_telegram_status(account_id)


@router.post("/telegram/credentials", response_model=TelegramAuthStatusResponse)
async def save_telegram_credentials(
    account_id: str,
    payload: TelegramCredentialsRequest,
    service: AccountAuthService = Depends(get_auth_service),
) -> TelegramAuthStatusResponse:
    return await service.save_telegram_credentials(account_id, payload)


@router.post("/telegram/request-code", response_model=TelegramAuthStatusResponse)
async def request_telegram_code(
    account_id: str,
    payload: TelegramPhoneRequest,
    service: AccountAuthService = Depends(get_auth_service),
) -> TelegramAuthStatusResponse:
    return await service.request_telegram_code(account_id, payload)


@router.post("/telegram/submit-code", response_model=TelegramAuthStatusResponse)
async def submit_telegram_code(
    account_id: str,
    payload: TelegramCodeRequest,
    service: AccountAuthService = Depends(get_auth_service),
) -> TelegramAuthStatusResponse:
    return await service.submit_telegram_code(account_id, payload)


@router.post("/telegram/submit-password", response_model=TelegramAuthStatusResponse)
async def submit_telegram_password(
    account_id: str,
    payload: TelegramPasswordRequest,
    service: AccountAuthService = Depends(get_auth_service),
) -> TelegramAuthStatusResponse:
    return await service.submit_telegram_password(account_id, payload)


@router.get("/shafa", response_model=ShafaAuthStatusResponse)
async def get_shafa_status(
    account_id: str,
    service: AccountAuthService = Depends(get_auth_service),
) -> ShafaAuthStatusResponse:
    return await service.get_shafa_status(account_id)


@router.post("/shafa/cookies", response_model=ShafaAuthStatusResponse)
async def save_shafa_cookies(
    account_id: str,
    payload: ShafaStorageStateRequest,
    service: AccountAuthService = Depends(get_auth_service),
) -> ShafaAuthStatusResponse:
    return await service.save_shafa_storage_state(account_id, payload)


@router.post(
    "/shafa/browser-login",
    response_model=ShafaAuthStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_shafa_browser_login(
    account_id: str,
    service: AccountAuthService = Depends(get_auth_service),
) -> ShafaAuthStatusResponse:
    return await service.start_shafa_browser_login(account_id)
