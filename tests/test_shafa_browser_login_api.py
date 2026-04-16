from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from shafa_control import AccountSessionStore
from telegram_accounts_api.dependencies import get_account_service, get_auth_service
from telegram_accounts_api.main import app
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.auth_service import AccountAuthService
from telegram_accounts_api.utils.storage import JsonListStorage


class ShafaBrowserLoginApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.accounts_file = self.base_dir / "accounts_state.json"
        self.accounts_dir = self.base_dir / "accounts"
        self.accounts_file.write_text(
            json.dumps(
                [
                    {
                        "id": "acc-1",
                        "name": "Waffle",
                        "phone": "",
                        "path": "/tmp/project",
                        "branch": "main",
                        "open_browser": False,
                        "timer_minutes": 5,
                        "channel_links": [],
                        "status": "stopped",
                        "last_run": None,
                        "errors": 0,
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.account_service = AccountService(
            storage=JsonListStorage(self.accounts_file),
            accounts_dir=self.accounts_dir,
        )
        self.launched_commands: list[tuple[str, list[str]]] = []
        store = AccountSessionStore(
            base_dir=self.base_dir,
            accounts_dir=self.accounts_dir,
            legacy_state_file=self.accounts_file,
        )

        def launcher(account, args: list[str]) -> None:
            self.launched_commands.append((account.id, args))

        self.auth_service = AccountAuthService(
            account_service=self.account_service,
            store=store,
            shafa_login_launcher=launcher,
        )
        app.dependency_overrides[get_account_service] = lambda: self.account_service
        app.dependency_overrides[get_auth_service] = lambda: self.auth_service
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_browser_login_endpoint_starts_shafa_flow(self) -> None:
        response = self.client.post("/accounts/acc-1/auth/shafa/browser-login")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.launched_commands, [("acc-1", ["main.py", "--login-shafa"])])
        self.assertIn("started", response.json()["message"].lower())


if __name__ == "__main__":
    unittest.main()
