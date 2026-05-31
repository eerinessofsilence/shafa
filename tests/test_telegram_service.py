from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from shafa_logic.telegram_subscription.client import TelegramSessionInUseError
from telegram_accounts_api.utils.exceptions import TelegramOperationError
from telegram_accounts_api.services.telegram_service import TelegramService, _extract_public_telegram_username


def _service() -> TelegramService:
    account_service = SimpleNamespace(
        account_dir=lambda account_id: Path("."),
        runtime=SimpleNamespace(proxy_db_path=None),
    )
    return TelegramService(
        account_service=account_service,  # type: ignore[arg-type]
        template_service=None,  # type: ignore[arg-type]
        base_dir=Path("."),
    )


class _FakeConversation:
    def __init__(self, raw_text: str) -> None:
        self.send_message = AsyncMock()
        self.get_response = AsyncMock(return_value=SimpleNamespace(raw_text=raw_text))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _SlowConversation:
    def __init__(self) -> None:
        self.send_message = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get_response(self):
        await asyncio.sleep(1)
        return SimpleNamespace(raw_text="ID: -1001\nTitle: Too Late")


def test_resolve_single_channel_prefers_entity_without_id_bot() -> None:
    service = _service()
    entity = SimpleNamespace(id=123, title="Fast Channel")
    client = SimpleNamespace(
        get_entity=AsyncMock(return_value=entity),
        conversation=Mock(),
    )

    with patch(
        "telegram_accounts_api.services.telegram_service._get_peer_id",
        return_value=-100123,
    ):
        result = asyncio.run(
            service._resolve_single_channel(client, "https://t.me/fast_channel")
        )

    assert result.channel_id == -100123
    assert result.title == "Fast Channel"
    client.get_entity.assert_awaited_once_with("https://t.me/fast_channel")
    client.conversation.assert_not_called()


def test_extract_public_telegram_username_from_link() -> None:
    assert _extract_public_telegram_username("https://t.me/Turbodrop") == "Turbodrop"
    assert _extract_public_telegram_username("t.me/s/Turbodrop") == "Turbodrop"
    assert _extract_public_telegram_username("https://t.me/+inviteHash") is None


def test_resolve_single_channel_uses_public_username_request() -> None:
    service = _service()
    entity = SimpleNamespace(id=123, title="TurboDrop")
    request_calls = []

    class _ResolveUsernameRequest:
        def __init__(self, username: str) -> None:
            self.username = username

    class _Client:
        get_entity = AsyncMock(side_effect=RuntimeError("not found"))
        conversation = Mock()

        async def __call__(self, request):
            request_calls.append(request.username)
            return SimpleNamespace(chats=[entity])

    client = _Client()

    with (
        patch(
            "telegram_accounts_api.services.telegram_service._get_peer_id",
            return_value=-100123,
        ),
        patch(
            "telethon.tl.functions.contacts.ResolveUsernameRequest",
            _ResolveUsernameRequest,
        ),
    ):
        result = asyncio.run(
            service._resolve_single_channel(client, "https://t.me/Turbodrop")
        )

    assert result.channel_id == -100123
    assert result.title == "TurboDrop"
    assert request_calls == ["Turbodrop"]
    client.get_entity.assert_not_called()
    client.conversation.assert_not_called()


def test_resolve_single_channel_falls_back_to_id_bot() -> None:
    service = _service()
    conversation = _FakeConversation("ID: -100777\nTitle: Bot Channel")
    client = SimpleNamespace(
        get_entity=AsyncMock(side_effect=RuntimeError("not found")),
        conversation=Mock(return_value=conversation),
    )

    result = asyncio.run(
        service._resolve_single_channel(client, "https://t.me/bot_channel")
    )

    assert result.channel_id == -100777
    assert result.title == "Bot Channel"
    client.get_entity.assert_awaited_once_with("https://t.me/bot_channel")
    client.conversation.assert_called_once_with("id_bot")
    conversation.send_message.assert_awaited_once_with("https://t.me/bot_channel")
    conversation.get_response.assert_awaited_once()


def test_resolve_single_channel_limits_id_bot_wait_time() -> None:
    service = _service()
    client = SimpleNamespace(
        get_entity=AsyncMock(side_effect=RuntimeError("not found")),
        conversation=Mock(return_value=_SlowConversation()),
    )

    with patch(
        "telegram_accounts_api.services.telegram_service.ID_BOT_RESPONSE_TIMEOUT_SECONDS",
        0.01,
    ):
        try:
            asyncio.run(
                service._resolve_single_channel(client, "https://t.me/slow_channel")
            )
        except TimeoutError:
            pass
        else:
            raise AssertionError("id_bot response wait should be limited")


def test_get_client_returns_conflict_when_session_is_busy() -> None:
    service = _service()

    class _BusyClient:
        async def connect(self):
            raise TelegramSessionInUseError("session is busy")

    service._resolve_credentials = AsyncMock(return_value=(777000, "hash", Path("telegram.session")))  # type: ignore[method-assign]

    with patch(
        "telegram_accounts_api.services.telegram_service.create_telegram_client",
        return_value=_BusyClient(),
    ):
        with pytest.raises(TelegramOperationError) as exc_info:
            asyncio.run(service._get_client("acc-1"))

    assert exc_info.value.status_code == 409
    assert "session is busy" in exc_info.value.message
