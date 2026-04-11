from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


class AccountStore:
    def __init__(
        self,
        state_file: Path,
        account_from_json: Callable[[dict[str, Any]], Any],
    ) -> None:
        self.state_file = state_file
        self.account_from_json = account_from_json

    def load(self) -> list[Any]:
        if not self.state_file.exists():
            return []
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        accounts = [self.account_from_json(item) for item in raw if item.get("path")]
        for account in accounts:
            account.status = "stopped"
            account.process = None
        return accounts

    def save(self, accounts: list[Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = [account.to_json() for account in accounts]
        self.state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
