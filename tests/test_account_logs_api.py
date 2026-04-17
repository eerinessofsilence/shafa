from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from shafa_control import AccountSessionStore
from telegram_accounts_api.dependencies import get_account_log_store, get_account_service, get_auth_service
from telegram_accounts_api.main import app
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.auth_service import AccountAuthService
from telegram_accounts_api.utils.account_logging import AccountLogStore, log, set_account_log_store
from telegram_accounts_api.utils.storage import JsonListStorage


class AccountLogsApiTest(unittest.TestCase):
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
                        "name": "Alpha",
                        "phone_number": "",
                        "path": "/tmp/project",
                        "branch": "main",
                        "open_browser": False,
                        "timer_minutes": 5,
                        "channel_links": [],
                        "status": "stopped",
                        "last_run": None,
                        "errors": 0,
                    },
                    {
                        "id": "acc-2",
                        "name": "Beta",
                        "phone_number": "",
                        "path": "/tmp/project",
                        "branch": "main",
                        "open_browser": False,
                        "timer_minutes": 5,
                        "channel_links": [],
                        "status": "stopped",
                        "last_run": None,
                        "errors": 0,
                    },
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
        self.log_store = AccountLogStore(max_entries_per_account=3)
        self.previous_store = set_account_log_store(self.log_store)
        store = AccountSessionStore(
            base_dir=self.base_dir,
            accounts_dir=self.accounts_dir,
            legacy_state_file=self.accounts_file,
        )
        self.auth_service = AccountAuthService(
            account_service=self.account_service,
            store=store,
            shafa_login_launcher=lambda _account, _args: None,
        )
        app.dependency_overrides[get_account_service] = lambda: self.account_service
        app.dependency_overrides[get_auth_service] = lambda: self.auth_service
        app.dependency_overrides[get_account_log_store] = lambda: self.log_store
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(lambda: set_account_log_store(AccountLogStore()))
        self.client = TestClient(app)

    def test_get_account_logs_returns_only_requested_account(self) -> None:
        log("acc-1", "INFO", "Login started")
        log("acc-1", "ERROR", "password=secret should be hidden")
        log("acc-2", "INFO", "Other account event")

        response = self.client.get("/accounts/acc-1/logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["account_id"] for item in payload], ["acc-1", "acc-1"])
        self.assertEqual(payload[-1]["level"], "ERROR")
        self.assertIn("password=[REDACTED]", payload[-1]["message"])

    def test_get_account_logs_supports_level_limit_and_since_index(self) -> None:
        log("acc-1", "INFO", "one")
        log("acc-1", "ERROR", "two")
        log("acc-1", "ERROR", "three")
        log("acc-1", "ERROR", "four")

        response = self.client.get("/accounts/acc-1/logs", params={"level": "ERROR", "limit": 2, "since": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["message"] for item in payload], ["three", "four"])
        self.assertEqual([item["index"] for item in payload], [2, 3])

    def test_websocket_streams_new_account_logs(self) -> None:
        with self.client.websocket_connect("/ws/logs/acc-1") as websocket:
            log("acc-1", "INFO", "Browser login started")
            message = websocket.receive_json()

        self.assertEqual(message["account_id"], "acc-1")
        self.assertEqual(message["level"], "INFO")
        self.assertEqual(message["message"], "Browser login started")

    def test_invalid_since_returns_bad_request(self) -> None:
        response = self.client.get("/accounts/acc-1/logs", params={"since": "not-a-timestamp"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("since", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
