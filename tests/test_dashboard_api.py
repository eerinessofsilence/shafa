from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from telegram_accounts_api.dependencies import (
    get_account_log_store,
    get_account_service,
    get_dashboard_service,
)
from telegram_accounts_api.main import app
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.dashboard_service import DashboardService
from telegram_accounts_api.utils.account_logging import AccountLogStore, set_account_log_store
from telegram_accounts_api.utils.storage import JsonListStorage


class DashboardApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.accounts_file = self.base_dir / "accounts_state.json"
        self.accounts_dir = self.base_dir / "accounts"
        self.local_tz = datetime.now().astimezone().tzinfo or UTC
        self.now = datetime.now(self.local_tz).replace(microsecond=0)
        self.accounts_file.write_text(
            json.dumps(
                [
                    {
                        "id": "acc-1",
                        "name": "Alpha",
                        "phone_number": "",
                        "path": "/tmp/project-a",
                        "branch": "main",
                        "timer_minutes": 5,
                        "channel_links": [],
                        "status": "started",
                        "last_run": (self.now - timedelta(hours=2)).isoformat(),
                        "errors": 2,
                    },
                    {
                        "id": "acc-2",
                        "name": "Beta",
                        "phone_number": "",
                        "path": "/tmp/project-b",
                        "branch": "main",
                        "timer_minutes": 10,
                        "channel_links": [],
                        "status": "stopped",
                        "last_run": (self.now - timedelta(days=1)).isoformat(),
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
        self.log_store = AccountLogStore(max_entries_per_account=100)
        set_account_log_store(self.log_store)
        self.dashboard_service = DashboardService(
            account_service=self.account_service,
            log_store=self.log_store,
            now_provider=lambda: self.now,
        )
        app.dependency_overrides[get_account_service] = lambda: self.account_service
        app.dependency_overrides[get_account_log_store] = lambda: self.log_store
        app.dependency_overrides[get_dashboard_service] = lambda: self.dashboard_service
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(lambda: set_account_log_store(AccountLogStore()))
        self.client = TestClient(app)

        self._write_ready_account("acc-1")
        self._write_history_log(
            "acc-1",
            [
                (
                    self.now - timedelta(days=1, hours=1),
                    "SUCCESS",
                    "Товар создан успешно. ID: 101.",
                ),
                (
                    self.now - timedelta(days=1, minutes=10),
                    "ERROR",
                    "Не удалось обработать товар.",
                ),
                (
                    self.now - timedelta(days=8),
                    "SUCCESS",
                    "Товар создан успешно. ID: 1.",
                ),
            ],
        )
        self._write_history_log(
            "acc-2",
            [
                (
                    self.now - timedelta(days=2, hours=3),
                    "SUCCESS",
                    "Товар создан успешно. ID: 202.",
                ),
            ],
        )
        self.log_store.append(
            "acc-1",
            "ERROR",
            "Runtime pipeline failed.",
            timestamp=self.now - timedelta(hours=1),
        )

    def _write_ready_account(self, account_id: str) -> None:
        account_dir = self.accounts_dir / account_id
        account_dir.mkdir(parents=True, exist_ok=True)
        (account_dir / "auth.json").write_text(
            json.dumps(
                {
                    "cookies": [
                        {
                            "name": "csrftoken",
                            "value": "token-123",
                            "domain": ".shafa.ua",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (account_dir / "telegram.session").write_bytes(b"SQLite format 3\x00payload")
        (account_dir / ".env").write_text(
            "SHAFA_TELEGRAM_API_ID=1\nSHAFA_TELEGRAM_API_HASH=hash\n",
            encoding="utf-8",
        )

    def _write_history_log(
        self,
        account_id: str,
        entries: list[tuple[datetime, str, str]],
    ) -> None:
        account_log = self.accounts_dir / account_id / "logs" / "app.log"
        account_log.parent.mkdir(parents=True, exist_ok=True)
        account_log.write_text(
            "".join(
                f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] [{account_id}] {message}\n"
                for timestamp, level, message in entries
            ),
            encoding="utf-8",
        )

    def test_dashboard_summary_returns_aggregated_real_data(self) -> None:
        response = self.client.get("/dashboard/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["range_start"], (self.now.date() - timedelta(days=8)).isoformat())
        self.assertEqual(payload["range_end"], self.now.date().isoformat())
        self.assertEqual(payload["total_accounts"], 2)
        self.assertEqual(payload["active_accounts"], 0)
        self.assertEqual(payload["ready_accounts"], 1)
        self.assertEqual(payload["attention_accounts"], 2)
        self.assertEqual(payload["item_successes_in_range"], 3)
        self.assertEqual(payload["error_events_in_range"], 2)
        self.assertEqual(payload["latest_run_account_name"], "Alpha")
        self.assertEqual(payload["top_error_account_name"], "Alpha")
        self.assertEqual(payload["top_error_account_errors"], 2)
        self.assertEqual(len(payload["series"]), 9)

        points = {point["date"]: point for point in payload["series"]}
        eight_days_ago = (self.now.date() - timedelta(days=8)).isoformat()
        yesterday = (self.now.date() - timedelta(days=1)).isoformat()
        two_days_ago = (self.now.date() - timedelta(days=2)).isoformat()
        today = self.now.date().isoformat()
        self.assertEqual(points[eight_days_ago]["items"], 1)
        self.assertEqual(points[yesterday]["items"], 1)
        self.assertEqual(points[yesterday]["errors"], 1)
        self.assertEqual(points[two_days_ago]["items"], 1)
        self.assertEqual(points[today]["errors"], 1)

    def test_dashboard_summary_supports_week_period(self) -> None:
        response = self.client.get("/dashboard/summary?period=week")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["range_start"], (self.now.date() - timedelta(days=6)).isoformat())
        self.assertEqual(payload["range_end"], self.now.date().isoformat())
        self.assertEqual(payload["item_successes_in_range"], 2)
        self.assertEqual(payload["error_events_in_range"], 2)
        self.assertEqual(len(payload["series"]), 7)

    def test_dashboard_summary_supports_custom_range(self) -> None:
        range_start = (self.now.date() - timedelta(days=2)).isoformat()
        range_end = self.now.date().isoformat()

        response = self.client.get(
            f"/dashboard/summary?period=custom&date_from={range_start}&date_to={range_end}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["range_start"], range_start)
        self.assertEqual(payload["range_end"], range_end)
        self.assertEqual(payload["item_successes_in_range"], 2)
        self.assertEqual(payload["error_events_in_range"], 2)
        self.assertEqual(len(payload["series"]), 3)

    def test_dashboard_summary_rejects_invalid_custom_range(self) -> None:
        response = self.client.get(
            "/dashboard/summary?period=custom&date_from=2026-05-01&date_to=2026-04-01"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Дата начала", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
