from __future__ import annotations

from telegram_accounts_api.services.account_service import AccountService


class OutdatedProductCleanupService:
    def __init__(self, account_service: AccountService) -> None:
        self.account_service = account_service

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def run_once(self) -> dict[str, int | float]:
        return {
            "accounts": 0,
            "checked": 0,
            "deactivated": 0,
            "failed": 0,
            "execution_time_seconds": 0.0,
        }
