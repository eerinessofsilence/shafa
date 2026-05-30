from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from tests.asgi_client import SyncASGITestClient, async_dependency


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
        app.dependency_overrides[get_account_service] = async_dependency(self.account_service)
        app.dependency_overrides[get_account_log_store] = async_dependency(self.log_store)
        app.dependency_overrides[get_dashboard_service] = async_dependency(self.dashboard_service)
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(lambda: set_account_log_store(AccountLogStore()))
        self.client = SyncASGITestClient(app)

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

    def _write_shared_deactivation_rows(
        self,
        rows: list[dict[str, object]],
    ) -> None:
        db_path = self.account_service.session_store.shared_telegram_db_file()
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE shared_telegram_products (
                    telegram_product_key TEXT PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    telegram_message_date TEXT,
                    product_title TEXT
                );
                CREATE TABLE shared_telegram_product_accounts (
                    telegram_product_key TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    shafa_product_id TEXT NOT NULL,
                    product_title TEXT,
                    account_product_status TEXT NOT NULL DEFAULT 'active',
                    PRIMARY KEY (telegram_product_key, account_id)
                );
                CREATE TABLE shared_deactivation_tasks (
                    task_id TEXT PRIMARY KEY,
                    telegram_product_key TEXT NOT NULL,
                    telegram_message_date TEXT,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    updated_at TEXT
                );
                CREATE TABLE shared_deactivation_task_accounts (
                    task_id TEXT NOT NULL,
                    telegram_product_key TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    shafa_product_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    next_retry_at REAL,
                    completed_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (task_id, account_id)
                );
                """
            )
            products: set[tuple[str, int, int, str]] = set()
            tasks: set[tuple[str, str, str]] = set()
            for row in rows:
                product_key = str(row["telegram_product_key"])
                channel_id = int(row.get("channel_id") or 11)
                message_id = int(row.get("message_id") or 501)
                title = str(row.get("product_title") or "Item")
                products.add((product_key, channel_id, message_id, title))
                tasks.add(
                    (
                        str(row["task_id"]),
                        product_key,
                        str(row.get("reason") or "telegram_message_older_than_183_days"),
                    )
                )
            conn.executemany(
                """
                INSERT INTO shared_telegram_products (
                    telegram_product_key, channel_id, message_id, product_title
                )
                VALUES (?, ?, ?, ?)
                """,
                sorted(products),
            )
            conn.executemany(
                """
                INSERT INTO shared_deactivation_tasks (
                    task_id, telegram_product_key, reason, status, updated_at
                )
                VALUES (?, ?, ?, 'pending', datetime('now'))
                """,
                sorted(tasks),
            )
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO shared_telegram_product_accounts (
                        telegram_product_key,
                        account_id,
                        shafa_product_id,
                        product_title,
                        account_product_status
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row["telegram_product_key"],
                        row["account_id"],
                        row["shafa_product_id"],
                        row.get("product_title") or "Item",
                        row.get("account_product_status") or "active",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO shared_deactivation_task_accounts (
                        task_id,
                        telegram_product_key,
                        account_id,
                        shafa_product_id,
                        status,
                        retry_count,
                        last_error,
                        completed_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        row["task_id"],
                        row["telegram_product_key"],
                        row["account_id"],
                        row["shafa_product_id"],
                        row["status"],
                        row.get("last_error"),
                        row.get("completed_at"),
                        row.get("updated_at") or row.get("completed_at"),
                    ),
                )

    def _write_direct_deactivation_rows(
        self,
        rows: list[dict[str, object]],
    ) -> None:
        db_path = self.account_service.session_store.shared_telegram_db_file()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    parsed_data TEXT,
                    status TEXT NOT NULL DEFAULT 'created',
                    created INTEGER NOT NULL DEFAULT 1,
                    created_product_id TEXT,
                    shafa_deactivated_at TEXT,
                    shafa_deleted_at TEXT,
                    deactivation_status TEXT,
                    deactivation_completed_at TEXT,
                    deactivation_error TEXT,
                    updated_at TEXT,
                    UNIQUE(account_id, channel_id, message_id)
                )
                """
            )
            for row in rows:
                title = str(row.get("product_title") or "Direct item")
                completed_at = row.get("completed_at") or self.now.isoformat()
                conn.execute(
                    """
                    INSERT INTO telegram_products (
                        account_id,
                        channel_id,
                        message_id,
                        parsed_data,
                        status,
                        created,
                        created_product_id,
                        shafa_deactivated_at,
                        shafa_deleted_at,
                        deactivation_status,
                        deactivation_completed_at,
                        deactivation_error,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, 'created', 1, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["account_id"],
                        row["channel_id"],
                        row["message_id"],
                        json.dumps({"name": title}),
                        row["shafa_product_id"],
                        row.get("shafa_deactivated_at"),
                        row.get("shafa_deleted_at"),
                        row.get("deactivation_status"),
                        completed_at,
                        row.get("deactivation_error"),
                        row.get("updated_at") or completed_at,
                    ),
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

    def test_dashboard_summary_counts_shared_deactivations_per_account_row(self) -> None:
        completed_at = (self.now - timedelta(minutes=5)).isoformat()
        self._write_shared_deactivation_rows(
            [
                {
                    "task_id": "task-shared-product",
                    "telegram_product_key": "tg:11:501",
                    "account_id": "acc-1",
                    "shafa_product_id": "product-a",
                    "status": "completed",
                    "completed_at": completed_at,
                    "product_title": "Shared item",
                },
                {
                    "task_id": "task-shared-product",
                    "telegram_product_key": "tg:11:501",
                    "account_id": "acc-2",
                    "shafa_product_id": "product-b",
                    "status": "completed",
                    "completed_at": completed_at,
                    "product_title": "Shared item",
                },
                {
                    "task_id": "task-other-product",
                    "telegram_product_key": "tg:12:601",
                    "channel_id": 12,
                    "message_id": 601,
                    "account_id": "acc-1",
                    "shafa_product_id": "product-c",
                    "status": "skipped_not_found",
                    "completed_at": completed_at,
                    "product_title": "Missing item",
                },
                {
                    "task_id": "task-pending-product",
                    "telegram_product_key": "tg:13:701",
                    "channel_id": 13,
                    "message_id": 701,
                    "account_id": "acc-1",
                    "shafa_product_id": "product-d",
                    "status": "pending",
                },
                {
                    "task_id": "task-failed-product",
                    "telegram_product_key": "tg:14:801",
                    "channel_id": 14,
                    "message_id": 801,
                    "account_id": "acc-2",
                    "shafa_product_id": "product-e",
                    "status": "failed",
                    "last_error": "temporary Shafa error",
                },
                {
                    "task_id": "task-retry-product",
                    "telegram_product_key": "tg:15:901",
                    "channel_id": 15,
                    "message_id": 901,
                    "account_id": "acc-2",
                    "shafa_product_id": "product-f",
                    "status": "retry_scheduled",
                    "last_error": "retry later",
                },
            ]
        )

        response = self.client.get("/dashboard/summary")

        self.assertEqual(response.status_code, 200)
        shared = response.json()["shared_deactivation"]
        self.assertEqual(shared["deactivated_success_count"], 2)
        self.assertEqual(shared["not_found_treated_as_done_count"], 1)
        self.assertEqual(shared["total_done_count"], 3)
        self.assertEqual(shared["total_deactivated_products"], 3)

        by_account = {
            row["account_id"]: row for row in shared["per_account"]
        }
        self.assertEqual(by_account["acc-1"]["account_name"], "Alpha")
        self.assertEqual(by_account["acc-1"]["deactivated_success_count"], 1)
        self.assertEqual(by_account["acc-1"]["not_found_treated_as_done_count"], 1)
        self.assertEqual(by_account["acc-1"]["total_done_count"], 2)
        self.assertEqual(by_account["acc-1"]["pending_count"], 1)
        self.assertEqual(by_account["acc-2"]["account_name"], "Beta")
        self.assertEqual(by_account["acc-2"]["deactivated_success_count"], 1)
        self.assertEqual(by_account["acc-2"]["failed_count"], 1)
        self.assertEqual(by_account["acc-2"]["retry_scheduled_count"], 1)

        recent = shared["recent"]
        self.assertEqual(len(recent), 3)
        self.assertEqual(
            sum(1 for row in recent if row["telegram_product_key"] == "tg:11:501"),
            2,
        )
        self.assertEqual(
            {row["status"] for row in recent},
            {"completed", "skipped_not_found"},
        )

    def test_dashboard_summary_counts_direct_deactivations(self) -> None:
        completed_at = (self.now - timedelta(minutes=5)).isoformat()
        self._write_direct_deactivation_rows(
            [
                {
                    "account_id": "acc-1",
                    "channel_id": 21,
                    "message_id": 1001,
                    "shafa_product_id": "direct-a",
                    "deactivation_status": "completed",
                    "shafa_deactivated_at": completed_at,
                    "completed_at": completed_at,
                    "product_title": "Direct item A",
                },
                {
                    "account_id": "acc-2",
                    "channel_id": 21,
                    "message_id": 1001,
                    "shafa_product_id": "direct-b",
                    "deactivation_status": "completed",
                    "shafa_deactivated_at": completed_at,
                    "completed_at": completed_at,
                    "product_title": "Direct item B",
                },
                {
                    "account_id": "acc-1",
                    "channel_id": 22,
                    "message_id": 1002,
                    "shafa_product_id": "direct-missing",
                    "deactivation_status": "skipped_not_found",
                    "shafa_deleted_at": completed_at,
                    "completed_at": completed_at,
                    "product_title": "Missing direct item",
                },
                {
                    "account_id": "acc-1",
                    "channel_id": 23,
                    "message_id": 1003,
                    "shafa_product_id": "direct-pending",
                    "deactivation_status": "pending",
                    "completed_at": completed_at,
                },
                {
                    "account_id": "acc-2",
                    "channel_id": 24,
                    "message_id": 1004,
                    "shafa_product_id": "direct-failed",
                    "deactivation_status": "failed",
                    "completed_at": completed_at,
                },
            ]
        )

        response = self.client.get("/dashboard/summary")

        self.assertEqual(response.status_code, 200)
        shared = response.json()["shared_deactivation"]
        self.assertEqual(shared["deactivated_success_count"], 2)
        self.assertEqual(shared["not_found_treated_as_done_count"], 1)
        self.assertEqual(shared["total_done_count"], 3)
        by_account = {row["account_id"]: row for row in shared["per_account"]}
        self.assertEqual(by_account["acc-1"]["deactivated_success_count"], 1)
        self.assertEqual(by_account["acc-1"]["not_found_treated_as_done_count"], 1)
        self.assertEqual(by_account["acc-2"]["deactivated_success_count"], 1)
        self.assertEqual({row["status"] for row in shared["recent"]}, {"completed", "skipped_not_found"})

    def test_dashboard_does_not_double_count_shared_source_rows(self) -> None:
        completed_at = (self.now - timedelta(minutes=5)).isoformat()
        self._write_shared_deactivation_rows(
            [
                {
                    "task_id": "task-shared-source",
                    "telegram_product_key": "tg:31:1101",
                    "channel_id": 31,
                    "message_id": 1101,
                    "account_id": "acc-1",
                    "shafa_product_id": "shared-source-a",
                    "status": "completed",
                    "completed_at": completed_at,
                    "product_title": "Shared source item",
                },
            ]
        )
        self._write_direct_deactivation_rows(
            [
                {
                    "account_id": "acc-1",
                    "channel_id": 31,
                    "message_id": 1101,
                    "shafa_product_id": "shared-source-a",
                    "deactivation_status": "completed",
                    "shafa_deactivated_at": completed_at,
                    "completed_at": completed_at,
                    "product_title": "Shared source item",
                },
            ]
        )

        response = self.client.get("/dashboard/summary")

        self.assertEqual(response.status_code, 200)
        shared = response.json()["shared_deactivation"]
        self.assertEqual(shared["deactivated_success_count"], 1)
        self.assertEqual(shared["total_done_count"], 1)

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

    def test_dashboard_summary_reads_full_history_not_only_log_tail(self) -> None:
        account_log = self.accounts_dir / "acc-1" / "logs" / "app.log"
        account_log.parent.mkdir(parents=True, exist_ok=True)
        history_entries = []
        for offset in range(130):
            timestamp = self.now - timedelta(days=129 - offset)
            history_entries.append(
                (
                    timestamp,
                    "SUCCESS",
                    f"Товар создан успешно. ID: {offset + 1000}.",
                )
            )
        self._write_history_log("acc-1", history_entries)

        self.dashboard_service.log_store = AccountLogStore(max_entries_per_account=5)

        response = self.client.get("/dashboard/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["range_start"],
            (self.now.date() - timedelta(days=129)).isoformat(),
        )
        self.assertEqual(payload["item_successes_in_range"], 130)
        self.assertEqual(len(payload["series"]), 130)


if __name__ == "__main__":
    unittest.main()
