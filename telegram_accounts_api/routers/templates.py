from __future__ import annotations

from fastapi import APIRouter, Depends, status

from telegram_accounts_api.dependencies import get_template_service
from telegram_accounts_api.models.common import ActionResponse
from telegram_accounts_api.models.template import (
    MessageTemplateCreate,
    MessageTemplateRead,
    MessageTemplateUpdate,
)
from telegram_accounts_api.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[MessageTemplateRead])
async def list_templates(service: TemplateService = Depends(get_template_service)) -> list[MessageTemplateRead]:
    return await service.list_templates()


@router.get("/{template_id}", response_model=MessageTemplateRead)
async def get_template(template_id: str, service: TemplateService = Depends(get_template_service)) -> MessageTemplateRead:
    return await service.get_template(template_id)


@router.post("", response_model=MessageTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: MessageTemplateCreate,
    service: TemplateService = Depends(get_template_service),
) -> MessageTemplateRead:
    return await service.create_template(payload)


@router.put("/{template_id}", response_model=MessageTemplateRead)
async def update_template(
    template_id: str,
    payload: MessageTemplateUpdate,
    service: TemplateService = Depends(get_template_service),
) -> MessageTemplateRead:
    return await service.update_template(template_id, payload)


@router.delete("/{template_id}", response_model=ActionResponse)
async def delete_template(
    template_id: str,
    service: TemplateService = Depends(get_template_service),
) -> ActionResponse:
    await service.delete_template(template_id)
    return ActionResponse(detail=f"Template '{template_id}' deleted.")
