from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .models import Account
from .session_store import AccountSessionStore


@dataclass
class ShafaLoginContext:
    account_id: str
    confirmation_file: Path


class ShafaAuthService:
    def __init__(self, store: AccountSessionStore) -> None:
        self.store = store

    def create_login_context(
        self,
        account: Account,
        base_env: Mapping[str, str],
    ) -> tuple[dict[str, str], ShafaLoginContext]:
        confirmation_file = self.store.account_dir(account) / "shafa_login.confirm"
        confirmation_file.unlink(missing_ok=True)
        env = dict(base_env)
        env["SHAFA_LOGIN_CONFIRMATION_FILE"] = str(confirmation_file)
        return env, ShafaLoginContext(account_id=account.id, confirmation_file=confirmation_file)

    def confirm_login(self, context: ShafaLoginContext) -> None:
        context.confirmation_file.write_text("ok\n", encoding="utf-8")

    def cancel_login(self, context: ShafaLoginContext) -> None:
        context.confirmation_file.unlink(missing_ok=True)

    def clear_context(self, context: ShafaLoginContext) -> None:
        context.confirmation_file.unlink(missing_ok=True)
