from __future__ import annotations

import logging
from datetime import datetime, UTC
from uuid import uuid4

from telegram_accounts_api.models.template import (
    MessageTemplateCreate,
    MessageTemplateRead,
    MessageTemplateUpdate,
)
from telegram_accounts_api.utils.exceptions import ConflictError, NotFoundError
from telegram_accounts_api.utils.storage import JsonListStorage

LOGGER = logging.getLogger(__name__)


class SafeFormatDict(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class TemplateService:
    def __init__(self, storage: JsonListStorage) -> None:
        self.storage = storage

    async def list_templates(self) -> list[MessageTemplateRead]:
        return [self._to_model(item) for item in await self.storage.read()]

    async def get_template(self, template_id: str) -> MessageTemplateRead:
        for item in await self.storage.read():
            if str(item.get("id")) == template_id:
                return self._to_model(item)
        raise NotFoundError(f"Template '{template_id}' not found.")

    async def create_template(self, data: MessageTemplateCreate) -> MessageTemplateRead:
        payload = await self.storage.read()
        template_id = data.id or uuid4().hex
        if any(str(item.get("id")) == template_id for item in payload):
            raise ConflictError(f"Template '{template_id}' already exists.")
        timestamp = datetime.now(UTC).isoformat()
        record = {
            "id": template_id,
            "name": data.name,
            "content": data.content,
            "description": data.description,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        payload.append(record)
        await self.storage.write(payload)
        LOGGER.info("Created template %s", template_id)
        return self._to_model(record)

    async def update_template(self, template_id: str, data: MessageTemplateUpdate) -> MessageTemplateRead:
        payload = await self.storage.read()
        target: dict | None = None
        for item in payload:
            if str(item.get("id")) != template_id:
                continue
            for field in ("name", "content", "description"):
                value = getattr(data, field)
                if value is not None:
                    item[field] = value
            item["updated_at"] = datetime.now(UTC).isoformat()
            target = item
            break
        if target is None:
            raise NotFoundError(f"Template '{template_id}' not found.")
        await self.storage.write(payload)
        LOGGER.info("Updated template %s", template_id)
        return self._to_model(target)

    async def delete_template(self, template_id: str) -> None:
        payload = await self.storage.read()
        filtered = [item for item in payload if str(item.get("id")) != template_id]
        if len(filtered) == len(payload):
            raise NotFoundError(f"Template '{template_id}' not found.")
        await self.storage.write(filtered)
        LOGGER.info("Deleted template %s", template_id)

    async def render_template(self, template_id: str, variables: dict[str, object] | None = None) -> str:
        template = await self.get_template(template_id)
        return template.content.format_map(SafeFormatDict(variables or {}))

    @staticmethod
    def _to_model(item: dict) -> MessageTemplateRead:
        created_at = str(item.get("created_at") or datetime.now(UTC).isoformat())
        updated_at = str(item.get("updated_at") or created_at)
        return MessageTemplateRead(
            id=str(item.get("id") or ""),
            name=str(item.get("name") or "").strip(),
            content=str(item.get("content") or ""),
            description=str(item.get("description") or "").strip() or None,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )
