from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from telegram_channels import parse_id_bot_response, sanitize_channel_links
from shafa_logic.telegram_subscription.client import create_telegram_client
from telegram_accounts_api.models.telegram import (
    SendMessageRequest,
    TelegramDialogResponse,
    TelegramMessageResponse,
    TelegramUserResponse,
)
from telegram_accounts_api.models.channel_template import ResolvedTelegramChannel
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.template_service import TemplateService
from telegram_accounts_api.utils.exceptions import TelegramOperationError

LOGGER = logging.getLogger(__name__)
CHANNEL_ENTITY_TIMEOUT_SECONDS = 10
ID_BOT_RESPONSE_TIMEOUT_SECONDS = 6


class TelegramService:
    def __init__(self, account_service: AccountService, template_service: TemplateService, base_dir: Path) -> None:
        self.account_service = account_service
        self.template_service = template_service
        self.base_dir = base_dir

    async def send_message(self, account_id: str, request: SendMessageRequest) -> TelegramMessageResponse:
        rendered_text = request.text or await self.template_service.render_template(
            request.template_id or "",
            request.template_variables,
        )
        async with self._client(account_id) as client:
            entity = await client.get_entity(request.peer)
            message = await client.send_message(entity, rendered_text)
        LOGGER.info("Sent Telegram message for account %s to %s", account_id, request.peer)
        return TelegramMessageResponse(
            account_id=account_id,
            peer=request.peer,
            message_id=message.id,
            text=rendered_text,
            sent_at=message.date.isoformat() if getattr(message, "date", None) else None,
        )

    async def get_dialogs(self, account_id: str, limit: int) -> list[TelegramDialogResponse]:
        async with self._client(account_id) as client:
            dialogs = await client.get_dialogs(limit=limit)
        return [
            TelegramDialogResponse(
                id=int(dialog.id),
                title=dialog.title or str(dialog.id),
                username=getattr(dialog.entity, "username", None),
                unread_count=int(getattr(dialog, "unread_count", 0) or 0),
                is_user=bool(dialog.is_user),
                is_group=bool(dialog.is_group),
                is_channel=bool(dialog.is_channel),
            )
            for dialog in dialogs
        ]

    async def get_user(self, account_id: str, user_ref: str) -> TelegramUserResponse:
        async with self._client(account_id) as client:
            entity = await client.get_entity(user_ref)
        return TelegramUserResponse(
            id=int(entity.id),
            username=getattr(entity, "username", None),
            first_name=getattr(entity, "first_name", None),
            last_name=getattr(entity, "last_name", None),
            phone=getattr(entity, "phone", None),
            is_bot=bool(getattr(entity, "bot", False)),
            is_self=bool(getattr(entity, "is_self", False)),
        )

    async def resolve_channel_links(self, account_id: str, links: list[str]) -> list[ResolvedTelegramChannel]:
        clean_links = sanitize_channel_links(links)
        if not clean_links:
            raise TelegramOperationError("Нужна хотя бы одна ссылка на Telegram-канал.")
        async with self._client(account_id) as client:
            resolved: list[ResolvedTelegramChannel] = []
            for link in clean_links:
                try:
                    resolved.append(await self._resolve_single_channel(client, link))
                except TelegramOperationError:
                    raise
                except Exception as exc:
                    raise TelegramOperationError(
                        (
                            f"Канал не найден: {link}. Telegram не смог найти публичный канал "
                            "по этой ссылке или у аккаунта, через который выполняется проверка, нет доступа к нему."
                        ),
                        status_code=400,
                    ) from exc
        return resolved

    async def _resolve_credentials(self, account_id: str) -> tuple[int, str, Path]:
        account = await self.account_service.get_account(account_id)
        session_file = self.account_service.session_file(account.id)
        if not session_file.exists():
            raise TelegramOperationError(
                f"Сессия Telegram не найдена для аккаунта '{account_id}'. Сначала подключи Telegram в блоке авторизации.",
                status_code=400,
            )

        credentials = self._read_env_file(self.account_service.credentials_file(account.id))
        if not credentials["SHAFA_TELEGRAM_API_ID"] or not credentials["SHAFA_TELEGRAM_API_HASH"]:
            root_credentials = self._read_env_file(self.base_dir / ".env")
            credentials["SHAFA_TELEGRAM_API_ID"] = credentials["SHAFA_TELEGRAM_API_ID"] or root_credentials["SHAFA_TELEGRAM_API_ID"] or os.getenv("SHAFA_TELEGRAM_API_ID", "")
            credentials["SHAFA_TELEGRAM_API_HASH"] = credentials["SHAFA_TELEGRAM_API_HASH"] or root_credentials["SHAFA_TELEGRAM_API_HASH"] or os.getenv("SHAFA_TELEGRAM_API_HASH", "")

        try:
            api_id = int(credentials["SHAFA_TELEGRAM_API_ID"])
        except (TypeError, ValueError) as exc:
            raise TelegramOperationError(
                f"Telegram API-данные не настроены для аккаунта '{account_id}'.",
                status_code=400,
            ) from exc

        api_hash = str(credentials["SHAFA_TELEGRAM_API_HASH"] or "").strip()
        if not api_hash:
            raise TelegramOperationError(
                f"Telegram API-данные не настроены для аккаунта '{account_id}'.",
                status_code=400,
            )

        return api_id, api_hash, session_file

    async def _get_client(self, account_id: str):
        try:
            from telethon import TelegramClient
        except ImportError as exc:
            raise TelegramOperationError("Telethon не установлен.") from exc

        api_id, api_hash, session_file = await self._resolve_credentials(account_id)
        client = create_telegram_client(
            session_file,
            api_id,
            api_hash,
            save_entities=False,
            telegram_client_cls=TelegramClient,
        )
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise TelegramOperationError(
                f"Сессия Telegram для аккаунта '{account_id}' не авторизована.",
                status_code=400,
            )
        return client

    async def _cleanup_client(self, client) -> None:
        await client.disconnect()

    def _client(self, account_id: str) -> "_TelegramClientContext":
        return _TelegramClientContext(self, account_id)

    @staticmethod
    def _read_env_file(path: Path) -> dict[str, str]:
        result = {
            "SHAFA_TELEGRAM_API_ID": "",
            "SHAFA_TELEGRAM_API_HASH": "",
        }
        if not path.exists():
            return result
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in result:
                result[key] = value.strip().strip("\"'")
        return result

    async def _resolve_single_channel(self, client, link: str) -> ResolvedTelegramChannel:
        resolved_from_entity = await self._resolve_channel_from_entity(client, link)
        if resolved_from_entity is not None:
            return resolved_from_entity

        return await self._resolve_channel_via_id_bot(client, link)

    async def _resolve_channel_from_entity(self, client, link: str) -> ResolvedTelegramChannel | None:
        try:
            entity = await asyncio.wait_for(
                client.get_entity(link),
                timeout=CHANNEL_ENTITY_TIMEOUT_SECONDS,
            )
        except Exception:
            return None
        return _resolved_channel_from_entity(entity)

    async def _resolve_channel_via_id_bot(self, client, link: str) -> ResolvedTelegramChannel:
        async with client.conversation("id_bot") as conversation:
            await conversation.send_message(link)
            response = await asyncio.wait_for(
                conversation.get_response(),
                timeout=ID_BOT_RESPONSE_TIMEOUT_SECONDS,
            )
        channel_id, title = parse_id_bot_response(response.raw_text)
        return ResolvedTelegramChannel(channel_id=channel_id, title=title, alias="main")


def _resolved_channel_from_entity(entity: object | None) -> ResolvedTelegramChannel | None:
    if entity is None:
        return None

    title = str(
        getattr(entity, "title", None) or getattr(entity, "username", None) or ""
    ).strip()
    if not title:
        return None

    try:
        channel_id = int(_get_peer_id(entity))
    except Exception:
        raw_id = getattr(entity, "id", None)
        if not isinstance(raw_id, int):
            return None
        channel_id = raw_id

    return ResolvedTelegramChannel(channel_id=channel_id, title=title, alias="main")


def _get_peer_id(entity: object) -> int:
    from telethon.utils import get_peer_id

    return int(get_peer_id(entity))


class _TelegramClientContext:
    def __init__(self, service: TelegramService, account_id: str) -> None:
        self.service = service
        self.account_id = account_id
        self.client = None

    async def __aenter__(self):
        self.client = await self.service._get_client(self.account_id)
        return self.client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.client is not None:
            await self.service._cleanup_client(self.client)
