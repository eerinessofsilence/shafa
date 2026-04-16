from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from telegram_channels import sanitize_channel_links
from telegram_accounts_api.models.channel_template import (
    ChannelTemplateCreate,
    ChannelTemplateRead,
    ChannelTemplateSummary,
    ChannelTemplateUpdate,
    ResolvedTelegramChannel,
)
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.utils.exceptions import BadRequestError, NotFoundError
from telegram_accounts_api.utils.storage import JsonListStorage

LOGGER = logging.getLogger(__name__)


class ChannelTemplateService:
    def __init__(self, storage: JsonListStorage, account_service: AccountService) -> None:
        self.storage = storage
        self.account_service = account_service

    async def list_templates(self, account_id: str | None = None) -> list[ChannelTemplateRead]:
        payload = await self.storage.read()
        if account_id is not None:
            payload = [item for item in payload if str(item.get("account_id")) == account_id]
        return [self._to_model(item) for item in payload]

    async def list_template_summaries(self, account_id: str) -> list[ChannelTemplateSummary]:
        templates = await self.list_templates(account_id)
        return [
            ChannelTemplateSummary(
                id=template.id,
                name=template.name,
                links=template.links,
                resolved_channels=template.resolved_channels,
            )
            for template in templates
        ]

    async def get_template(self, account_id: str, template_id: str) -> ChannelTemplateRead:
        await self.account_service.get_account(account_id)
        for item in await self.storage.read():
            if str(item.get("id")) == template_id and str(item.get("account_id")) == account_id:
                return self._to_model(item)
        raise NotFoundError(f"Channel template '{template_id}' not found for account '{account_id}'.")

    async def get_template_by_name(self, account_id: str, template_name: str) -> ChannelTemplateRead:
        clean_name = template_name.strip()
        await self.account_service.get_account(account_id)
        for item in await self.storage.read():
            if str(item.get("account_id")) != account_id:
                continue
            if str(item.get("name") or "").strip() == clean_name:
                return self._to_model(item)
        raise NotFoundError(f"Channel template '{clean_name}' not found for account '{account_id}'.")

    async def create_template(self, account_id: str, data: ChannelTemplateCreate, telegram_service) -> ChannelTemplateRead:
        await self.account_service.get_account(account_id)
        payload = await self.storage.read()
        if any(
            str(item.get("account_id")) == account_id
            and str(item.get("name") or "").strip() == data.name
            for item in payload
        ):
            raise BadRequestError(
                f"Channel template with name '{data.name}' already exists for account '{account_id}'."
            )
        template_id = uuid4().hex
        while any(str(item.get("id")) == template_id for item in payload):
            template_id = uuid4().hex
        try:
            clean_links = sanitize_channel_links(data.links)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc
        resolved_channels = await telegram_service.resolve_channel_links(account_id, clean_links)
        timestamp = datetime.now(UTC).isoformat()
        record = {
            "id": template_id,
            "account_id": account_id,
            "name": data.name,
            "links": clean_links,
            "resolved_channels": [channel.model_dump() for channel in resolved_channels],
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        payload.append(record)
        await self.storage.write(payload)
        LOGGER.info("Created channel template %s for account %s", template_id, account_id)
        return self._to_model(record)

    async def update_template(
        self,
        account_id: str,
        template_name: str,
        data: ChannelTemplateUpdate,
        telegram_service,
    ) -> ChannelTemplateRead:
        await self.account_service.get_account(account_id)
        payload = await self.storage.read()
        updated_record: dict | None = None
        for item in payload:
            if str(item.get("account_id")) != account_id:
                continue
            if str(item.get("name") or "").strip() != template_name.strip():
                continue
            if data.name is not None:
                if any(
                    str(other.get("account_id")) == account_id
                    and str(other.get("name") or "").strip() == data.name
                    and str(other.get("id")) != str(item.get("id"))
                    for other in payload
                ):
                    raise BadRequestError(
                        f"Channel template with name '{data.name}' already exists for account '{account_id}'."
                    )
                item["name"] = data.name
            if data.links is not None:
                try:
                    clean_links = sanitize_channel_links(data.links)
                except ValueError as exc:
                    raise BadRequestError(str(exc)) from exc
                item["links"] = clean_links
                resolved_channels = await telegram_service.resolve_channel_links(account_id, clean_links)
                item["resolved_channels"] = [channel.model_dump() for channel in resolved_channels]
            item["updated_at"] = datetime.now(UTC).isoformat()
            updated_record = item
            break
        if updated_record is None:
            raise NotFoundError(f"Channel template '{template_name}' not found for account '{account_id}'.")
        await self.storage.write(payload)
        LOGGER.info("Updated channel template %s for account %s", template_name, account_id)
        return self._to_model(updated_record)

    async def delete_template(self, account_id: str, template_name: str) -> None:
        await self.account_service.get_account(account_id)
        payload = await self.storage.read()
        filtered = [
            item
            for item in payload
            if not (
                str(item.get("account_id")) == account_id
                and str(item.get("name") or "").strip() == template_name.strip()
            )
        ]
        if len(filtered) == len(payload):
            raise NotFoundError(f"Channel template '{template_name}' not found for account '{account_id}'.")
        await self.storage.write(filtered)
        LOGGER.info("Deleted channel template %s for account %s", template_name, account_id)

    @staticmethod
    def _to_model(item: dict) -> ChannelTemplateRead:
        created_at = str(item.get("created_at") or datetime.now(UTC).isoformat())
        updated_at = str(item.get("updated_at") or created_at)
        resolved_channels = []
        for channel in item.get("resolved_channels") or []:
            if not isinstance(channel, dict):
                continue
            try:
                resolved_channels.append(
                    ResolvedTelegramChannel(
                        channel_id=int(channel.get("channel_id")),
                        title=str(channel.get("title") or "").strip(),
                        alias=str(channel.get("alias") or "main").strip() or "main",
                    )
                )
            except (TypeError, ValueError):
                continue
        return ChannelTemplateRead(
            id=str(item.get("id") or ""),
            account_id=str(item.get("account_id") or ""),
            name=str(item.get("name") or "").strip(),
            links=sanitize_channel_links(item.get("links") or []),
            resolved_channels=resolved_channels,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )
