from __future__ import annotations

from fastapi import APIRouter, Depends, status

from telegram_accounts_api.dependencies import get_account_service
from telegram_accounts_api.models.account import AccountCreate, AccountRead, AccountUpdate
from telegram_accounts_api.models.common import ActionResponse
from telegram_accounts_api.services.account_service import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountRead])
async def list_accounts(service: AccountService = Depends(get_account_service)) -> list[AccountRead]:
    return await service.list_accounts()


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(account_id: str, service: AccountService = Depends(get_account_service)) -> AccountRead:
    return await service.get_account(account_id)


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    service: AccountService = Depends(get_account_service),
) -> AccountRead:
    return await service.create_account(payload)


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: str,
    payload: AccountUpdate,
    service: AccountService = Depends(get_account_service),
) -> AccountRead:
    return await service.update_account(account_id, payload)


@router.delete("/{account_id}", response_model=ActionResponse)
async def delete_account(account_id: str, service: AccountService = Depends(get_account_service)) -> ActionResponse:
    await service.delete_account(account_id)
    return ActionResponse(detail=f"Account '{account_id}' deleted.")


@router.post("/{account_id}/start", response_model=AccountRead)
async def start_account(account_id: str, service: AccountService = Depends(get_account_service)) -> AccountRead:
    return await service.set_status(account_id, "started")


@router.post("/{account_id}/stop", response_model=AccountRead)
async def stop_account(account_id: str, service: AccountService = Depends(get_account_service)) -> AccountRead:
    return await service.set_status(account_id, "stopped")
