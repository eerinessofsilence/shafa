from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from shafa_control.session_store import AccountSessionStore


class AccountStore:
    def __init__(
        self,
        state_file: Path,
        account_from_json: Callable[[dict[str, Any]], Any],
    ) -> None:
        self.state_file = state_file
        self.account_from_json = account_from_json
        self.session_store = AccountSessionStore(
            base_dir=state_file.parent,
            accounts_dir=state_file.parent / "accounts",
            legacy_state_file=state_file,
        )

    def load(self) -> list[Any]:
        accounts = self.session_store.load_accounts()
        return [self.account_from_json(account.to_json()) for account in accounts]

    def save(self, accounts: list[Any]) -> None:
        self.session_store.save_accounts(accounts)
