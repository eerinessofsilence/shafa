from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from telegram_accounts_api.dependencies import get_channel_template_service, get_telegram_service
from telegram_accounts_api.models.channel_template import (
    ChannelTemplateCreate,
    ChannelTemplateRead,
    ChannelTemplateResolveRequest,
    ChannelTemplateType,
    ChannelTemplateUpdate,
    ResolvedTelegramChannel,
)
from telegram_accounts_api.models.common import ActionResponse
from telegram_accounts_api.services.channel_template_service import ChannelTemplateService
from telegram_accounts_api.services.telegram_service import TelegramService

router = APIRouter(prefix="/accounts/{account_id}/channel-templates", tags=["channel-templates"])
global_router = APIRouter(prefix="/channel-templates", tags=["channel-templates"])


@global_router.get("", response_model=list[ChannelTemplateRead])
async def list_global_channel_templates(
    template_type: ChannelTemplateType | None = Query(default=None, alias="type"),
    service: ChannelTemplateService = Depends(get_channel_template_service),
) -> list[ChannelTemplateRead]:
    return await service.list_global_templates(template_type)


@global_router.post("/resolve", response_model=list[ResolvedTelegramChannel])
async def resolve_global_channel_templates(
    payload: ChannelTemplateResolveRequest,
    service: ChannelTemplateService = Depends(get_channel_template_service),
    telegram_service: TelegramService = Depends(get_telegram_service),
) -> list[ResolvedTelegramChannel]:
    return await service.resolve_global_channel_links(payload.links, telegram_service)


@global_router.get("/{template_id}", response_model=ChannelTemplateRead)
async def get_global_channel_template(
    template_id: str,
    service: ChannelTemplateService = Depends(get_channel_template_service),
) -> ChannelTemplateRead:
    return await service.get_global_template(template_id)


@global_router.post("", response_model=ChannelTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_global_channel_template(
    payload: ChannelTemplateCreate,
    service: ChannelTemplateService = Depends(get_channel_template_service),
) -> ChannelTemplateRead:
    return await service.create_global_template(payload)


@global_router.put("/{template_id}", response_model=ChannelTemplateRead)
async def update_global_channel_template(
    template_id: str,
    payload: ChannelTemplateUpdate,
    service: ChannelTemplateService = Depends(get_channel_template_service),
) -> ChannelTemplateRead:
    return await service.update_global_template(template_id, payload)


@global_router.delete("/{template_id}", response_model=ActionResponse)
async def delete_global_channel_template(
    template_id: str,
    service: ChannelTemplateService = Depends(get_channel_template_service),
) -> ActionResponse:
    await service.delete_global_template(template_id)
    return ActionResponse(detail=f"Channel template '{template_id}' deleted.")


@router.get("", response_model=list[ChannelTemplateRead])
async def list_channel_templates(
    account_id: str,
    service: ChannelTemplateService = Depends(get_channel_template_service),
) -> list[ChannelTemplateRead]:
    return await service.list_templates(account_id)


@router.get("/{template_name}", response_model=ChannelTemplateRead)
async def get_channel_template(
    account_id: str,
    template_name: str,
    service: ChannelTemplateService = Depends(get_channel_template_service),
) -> ChannelTemplateRead:
    return await service.get_template_by_name(account_id, template_name)


@router.post("", response_model=ChannelTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_channel_template(
    account_id: str,
    payload: ChannelTemplateCreate,
    service: ChannelTemplateService = Depends(get_channel_template_service),
    telegram_service: TelegramService = Depends(get_telegram_service),
) -> ChannelTemplateRead:
    return await service.create_template(account_id, payload, telegram_service)


@router.put("/{template_name}", response_model=ChannelTemplateRead)
async def update_channel_template(
    account_id: str,
    template_name: str,
    payload: ChannelTemplateUpdate,
    service: ChannelTemplateService = Depends(get_channel_template_service),
    telegram_service: TelegramService = Depends(get_telegram_service),
) -> ChannelTemplateRead:
    return await service.update_template(account_id, template_name, payload, telegram_service)


@router.delete("/{template_name}", response_model=ActionResponse)
async def delete_channel_template(
    account_id: str,
    template_name: str,
    service: ChannelTemplateService = Depends(get_channel_template_service),
) -> ActionResponse:
    await service.delete_template(account_id, template_name)
    return ActionResponse(detail=f"Channel template '{template_name}' deleted for account '{account_id}'.")
