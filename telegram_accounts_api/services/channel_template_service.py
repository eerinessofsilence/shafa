from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from telegram_channels import sanitize_channel_links
from telegram_accounts_api.models.channel_template import (
    ChannelTemplateCreate,
    ChannelTemplateRead,
    ChannelTemplateSummary,
    ChannelTemplateType,
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

    async def list_global_templates(
        self,
        template_type: ChannelTemplateType | None = None,
    ) -> list[ChannelTemplateRead]:
        payload = await self._read_payload()
        templates = [item for item in payload if self._is_global_template(item)]
        if template_type is not None:
            templates = [
                item
                for item in templates
                if self._normalize_template_type(item.get("type")) == template_type
            ]
        return [self._to_model(item) for item in templates]

    async def get_global_template(self, template_id: str) -> ChannelTemplateRead:
        for item in await self._read_payload():
            if self._is_global_template(item) and str(item.get("id")) == template_id:
                return self._to_model(item)
        raise NotFoundError(f"Channel template '{template_id}' not found.")

    async def create_global_template(self, data: ChannelTemplateCreate) -> ChannelTemplateRead:
        payload = await self._read_payload()
        if self._has_global_template_name(payload, data.name, data.type):
            raise BadRequestError(
                f"Channel template with name '{data.name}' already exists for type '{data.type}'."
            )
        template_id = self._create_unique_template_id(payload)
        try:
            clean_links = sanitize_channel_links(data.links)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc
        timestamp = datetime.now(UTC).isoformat()
        record = {
            "id": template_id,
            "account_id": None,
            "name": data.name,
            "type": data.type,
            "links": clean_links,
            "resolved_channels": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        payload.append(record)
        await self.storage.write(payload)
        LOGGER.info("Created global channel template %s", template_id)
        return self._to_model(record)

    async def resolve_global_channel_links(
        self,
        links: list[str],
        telegram_service,
    ) -> list[ResolvedTelegramChannel]:
        try:
            clean_links = sanitize_channel_links(links)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc
        if not clean_links:
            raise BadRequestError("Нужна хотя бы одна ссылка на Telegram-канал.")

        accounts = await self.account_service.list_accounts()
        candidate_accounts = [
            account for account in accounts if account.telegram_session_exists
        ]
        if not candidate_accounts:
            raise BadRequestError(
                "Для проверки канала сначала подключите Telegram хотя бы в одном аккаунте."
            )

        last_error: Exception | None = None
        for account in candidate_accounts:
            try:
                return await telegram_service.resolve_channel_links(
                    account.id,
                    clean_links,
                )
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise BadRequestError("Не удалось проверить Telegram-канал.")

    async def update_global_template(
        self,
        template_id: str,
        data: ChannelTemplateUpdate,
    ) -> ChannelTemplateRead:
        payload = await self._read_payload()
        updated_record: dict | None = None
        for item in payload:
            if not self._is_global_template(item) or str(item.get("id")) != template_id:
                continue

            next_name = data.name if data.name is not None else str(item.get("name") or "").strip()
            next_type = data.type if data.type is not None else self._normalize_template_type(item.get("type"))
            if self._has_global_template_name(payload, next_name, next_type, excluding_id=template_id):
                raise BadRequestError(
                    f"Channel template with name '{next_name}' already exists for type '{next_type}'."
                )

            item["name"] = next_name
            item["type"] = next_type
            if data.links is not None:
                try:
                    item["links"] = sanitize_channel_links(data.links)
                except ValueError as exc:
                    raise BadRequestError(str(exc)) from exc
                item["resolved_channels"] = []
            item["updated_at"] = datetime.now(UTC).isoformat()
            updated_record = item
            break

        if updated_record is None:
            raise NotFoundError(f"Channel template '{template_id}' not found.")
        await self.storage.write(payload)
        LOGGER.info("Updated global channel template %s", template_id)
        return self._to_model(updated_record)

    async def delete_global_template(self, template_id: str) -> None:
        payload = await self._read_payload()
        filtered = [
            item
            for item in payload
            if not (self._is_global_template(item) and str(item.get("id")) == template_id)
        ]
        if len(filtered) == len(payload):
            raise NotFoundError(f"Channel template '{template_id}' not found.")
        await self.storage.write(filtered)
        LOGGER.info("Deleted global channel template %s", template_id)

    async def list_templates(self, account_id: str | None = None) -> list[ChannelTemplateRead]:
        payload = await self._read_payload()
        if account_id is not None:
            payload = [item for item in payload if str(item.get("account_id")) == account_id]
        else:
            payload = [item for item in payload if not self._is_global_template(item)]
        return [self._to_model(item) for item in payload]

    async def list_template_summaries(self, account_id: str) -> list[ChannelTemplateSummary]:
        templates = await self.list_templates(account_id)
        return [
            ChannelTemplateSummary(
                id=template.id,
                name=template.name,
                type=template.type,
                links=template.links,
                resolved_channels=template.resolved_channels,
            )
            for template in templates
        ]

    async def get_template(self, account_id: str, template_id: str) -> ChannelTemplateRead:
        await self.account_service.get_account(account_id)
        for item in await self._read_payload():
            if str(item.get("id")) == template_id and str(item.get("account_id")) == account_id:
                return self._to_model(item)
        raise NotFoundError(f"Channel template '{template_id}' not found for account '{account_id}'.")

    async def get_template_by_name(self, account_id: str, template_name: str) -> ChannelTemplateRead:
        clean_name = template_name.strip()
        await self.account_service.get_account(account_id)
        for item in await self._read_payload():
            if str(item.get("account_id")) != account_id:
                continue
            if str(item.get("name") or "").strip() == clean_name:
                return self._to_model(item)
        raise NotFoundError(f"Channel template '{clean_name}' not found for account '{account_id}'.")

    async def create_template(self, account_id: str, data: ChannelTemplateCreate, telegram_service) -> ChannelTemplateRead:
        await self.account_service.get_account(account_id)
        payload = await self._read_payload()
        if any(
            str(item.get("account_id")) == account_id
            and str(item.get("name") or "").strip() == data.name
            for item in payload
        ):
            raise BadRequestError(
                f"Channel template with name '{data.name}' already exists for account '{account_id}'."
            )
        template_id = self._create_unique_template_id(payload)
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
            "type": data.type,
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
        payload = await self._read_payload()
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
            if data.type is not None:
                item["type"] = data.type
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
        payload = await self._read_payload()
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

    async def _read_payload(self) -> list[dict]:
        payload = await self.storage.read()
        normalized_payload, changed = self._normalize_storage_payload(payload)
        if changed:
            await self.storage.write(normalized_payload)
        return normalized_payload

    @classmethod
    def _normalize_storage_payload(cls, payload: list[dict]) -> tuple[list[dict], bool]:
        timestamp = datetime.now(UTC).isoformat()
        normalized_payload: list[dict] = []
        changed = False
        for item in payload:
            legacy_entries = [
                (key, value)
                for key, value in item.items()
                if str(key).strip().lower() in {"clothes", "shoes", "sneakers"}
                and isinstance(value, dict)
            ]
            if legacy_entries and "id" not in item and "links" not in item:
                changed = True
                for legacy_type, legacy_payload in legacy_entries:
                    record = dict(legacy_payload)
                    record.setdefault("id", uuid4().hex)
                    record["account_id"] = record.get("account_id")
                    record["name"] = str(record.get("name") or legacy_type).strip()
                    record["type"] = cls._normalize_template_type(record.get("type") or legacy_type)
                    record["links"] = sanitize_channel_links(record.get("links") or [])
                    record.setdefault("resolved_channels", [])
                    record.setdefault("created_at", timestamp)
                    record.setdefault("updated_at", record["created_at"])
                    normalized_payload.append(record)
                continue

            record = dict(item)
            if not str(record.get("id") or "").strip():
                record["id"] = uuid4().hex
                changed = True
            inferred_type = record.get("type")
            if inferred_type is None:
                name = str(record.get("name") or "").strip().lower()
                inferred_type = name if name in {"clothes", "shoes", "sneakers"} else "clothes"
                changed = True
            normalized_type = cls._normalize_template_type(inferred_type)
            if record.get("type") != normalized_type:
                record["type"] = normalized_type
                changed = True
            record.setdefault("created_at", timestamp)
            record.setdefault("updated_at", record["created_at"])
            normalized_payload.append(record)
        return normalized_payload, changed

    @staticmethod
    def _is_global_template(item: dict) -> bool:
        return not str(item.get("account_id") or "").strip()

    @staticmethod
    def _normalize_template_type(value) -> ChannelTemplateType:
        normalized = str(value or "clothes").strip().lower()
        if normalized == "sneakers":
            return "shoes"
        return "shoes" if normalized == "shoes" else "clothes"

    @staticmethod
    def _create_unique_template_id(payload: list[dict]) -> str:
        template_id = uuid4().hex
        while any(str(item.get("id")) == template_id for item in payload):
            template_id = uuid4().hex
        return template_id

    @classmethod
    def _has_global_template_name(
        cls,
        payload: list[dict],
        name: str,
        template_type: ChannelTemplateType,
        excluding_id: str | None = None,
    ) -> bool:
        clean_name = name.strip()
        return any(
            cls._is_global_template(item)
            and str(item.get("id")) != str(excluding_id)
            and str(item.get("name") or "").strip() == clean_name
            and cls._normalize_template_type(item.get("type")) == template_type
            for item in payload
        )

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
            account_id=str(item.get("account_id") or "").strip() or None,
            name=str(item.get("name") or "").strip(),
            type=ChannelTemplateService._normalize_template_type(item.get("type")),
            links=sanitize_channel_links(item.get("links") or []),
            resolved_channels=resolved_channels,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )
