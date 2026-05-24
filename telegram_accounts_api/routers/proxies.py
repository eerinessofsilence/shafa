from __future__ import annotations

from fastapi import APIRouter, Depends, status

from telegram_accounts_api.dependencies import get_proxy_service
from telegram_accounts_api.models.common import ActionResponse
from telegram_accounts_api.models.proxy import ProxyCreate, ProxyRead, ProxyUpdate
from telegram_accounts_api.services.proxy_service import ProxyService

router = APIRouter(prefix="/proxies", tags=["proxies"])


@router.get("", response_model=list[ProxyRead])
async def list_proxies(
    service: ProxyService = Depends(get_proxy_service),
) -> list[ProxyRead]:
    return service.list_proxies()


@router.get("/{proxy_id}", response_model=ProxyRead)
async def get_proxy(
    proxy_id: str,
    service: ProxyService = Depends(get_proxy_service),
) -> ProxyRead:
    return service.get_proxy(proxy_id)


@router.post("", response_model=ProxyRead, status_code=status.HTTP_201_CREATED)
async def create_proxy(
    payload: ProxyCreate,
    service: ProxyService = Depends(get_proxy_service),
) -> ProxyRead:
    return service.create_proxy(payload)


@router.patch("/{proxy_id}", response_model=ProxyRead)
async def update_proxy(
    proxy_id: str,
    payload: ProxyUpdate,
    service: ProxyService = Depends(get_proxy_service),
) -> ProxyRead:
    return service.update_proxy(proxy_id, payload)


@router.delete("/{proxy_id}", response_model=ActionResponse)
async def delete_proxy(
    proxy_id: str,
    service: ProxyService = Depends(get_proxy_service),
) -> ActionResponse:
    service.delete_proxy(proxy_id)
    return ActionResponse(detail=f"Proxy '{proxy_id}' deleted.")
