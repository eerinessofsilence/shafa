from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import Account
from .session_store import AccountSessionStore

CommandRunner = Callable[[Account, list[str]], subprocess.CompletedProcess]


@dataclass
class TelegramAuthStatus:
    ok: bool
    message: str
    pending_code: bool = False


class TelegramAuthService:
    def __init__(
        self,
        store: AccountSessionStore,
        runner: CommandRunner,
    ) -> None:
        self.store = store
        self.runner = runner

    def request_code(self, account: Account) -> TelegramAuthStatus:
        phone = account.phone_number.strip()
        if not phone:
            return TelegramAuthStatus(False, "Telegram auth requires phone number.")

        result = self.runner(account, ["main.py", "--telegram-send-code", phone])
        if result.returncode != 0:
            return TelegramAuthStatus(False, self._command_error(result))
        return TelegramAuthStatus(True, "Telegram code requested.", pending_code=True)

    def submit_code(self, account: Account, code: str) -> TelegramAuthStatus:
        phone = account.phone_number.strip()
        clean_code = code.strip()
        if not phone:
            return TelegramAuthStatus(False, "Telegram auth requires phone number.")
        if not clean_code:
            return TelegramAuthStatus(False, "Verification code is required.")

        result = self.runner(
            account,
            [
                "main.py",
                "--telegram-login-phone",
                phone,
                "--telegram-login-code",
                clean_code,
            ],
        )
        if result.returncode != 0:
            return TelegramAuthStatus(False, self._command_error(result))
        return TelegramAuthStatus(True, "Telegram session saved.", pending_code=False)

    def has_pending_code(self, account: Account) -> bool:
        return self.store.has_pending_telegram_code(account)

    def interactive_command(self) -> list[str]:
        return ["main.py", "--telegram-auth-interactive"]

    def import_session(self, account: Account, source_path: Path) -> None:
        self.store.import_telegram_session(account, source_path)

    def export_session(self, account: Account, target_path: Path) -> None:
        self.store.export_telegram_session(account, target_path)

    def copy_session(self, source: Account, target: Account) -> None:
        self.store.copy_telegram_session(source, target)

    @staticmethod
    def _command_error(result: subprocess.CompletedProcess) -> str:
        return (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
