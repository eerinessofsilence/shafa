from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from shafa_control import Account, AccountSessionStore
from shafa_logic.telegram_subscription.client import TelegramSessionInUseError
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.auth_service import AccountAuthService
from telegram_accounts_api.utils.exceptions import TelegramOperationError
from telegram_accounts_api.utils.storage import JsonListStorage


def test_connect_direct_telegram_client_returns_conflict_when_session_is_busy(
    tmp_path: Path,
) -> None:
    accounts_file = tmp_path / "accounts_state.json"
    accounts_dir = tmp_path / "accounts"
    storage = JsonListStorage(accounts_file)
    account_service = AccountService(storage=storage, accounts_dir=accounts_dir)
    store = AccountSessionStore(tmp_path, accounts_dir, accounts_file)
    service = AccountAuthService(account_service=account_service, store=store)
    account = Account(id="acc-1", name="Busy", path=str(tmp_path / "project"))

    class _BusyClient:
        async def connect(self):
            raise TelegramSessionInUseError("session is busy")

    with (
        patch.object(
            service,
            "_telegram_client_config",
            return_value=(object(), 777000, "hash", store.telegram_session_file(account)),
        ),
        patch(
            "telegram_accounts_api.services.auth_service.create_telegram_client",
            return_value=_BusyClient(),
        ),
    ):
        try:
            asyncio.run(service._connect_direct_telegram_client(account))
        except TelegramOperationError as exc:
            assert exc.status_code == 409
            assert "session is busy" in exc.message
        else:
            raise AssertionError("Expected TelegramOperationError for busy session")
