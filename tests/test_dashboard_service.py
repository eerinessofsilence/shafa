from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telegram_accounts_api.services.dashboard_service import DashboardService
from telegram_accounts_api.utils.account_logging import AccountLogStore


class DashboardServiceDeactivationTest(unittest.TestCase):
    def _service(self, db_path: Path) -> DashboardService:
        account_service = SimpleNamespace(
            session_store=SimpleNamespace(shared_telegram_db_file=lambda: db_path)
        )
        return DashboardService(
            account_service=account_service,
            log_store=AccountLogStore(),
        )

    def test_shared_deactivation_summary_uses_ttl_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "telegram.sqlite3"
            completed_at = datetime.now().replace(microsecond=0).isoformat()
            self._create_telegram_products(
                db_path,
                [
                    {
                        "account_id": "acc-1",
                        "channel_id": 21,
                        "message_id": 1001,
                        "shafa_product_id": "direct-a",
                        "deactivation_status": "completed",
                        "shafa_deactivated_at": completed_at,
                        "completed_at": completed_at,
                    },
                ],
            )
            service = DashboardService(
                account_service=SimpleNamespace(
                    session_store=SimpleNamespace(shared_telegram_db_file=lambda: db_path)
                ),
                log_store=AccountLogStore(),
                deactivation_cache_ttl_seconds=30,
            )
            original_connect = sqlite3.connect
            connect_calls = 0

            def counting_connect(*args, **kwargs):
                nonlocal connect_calls
                connect_calls += 1
                return original_connect(*args, **kwargs)

            with patch("telegram_accounts_api.services.dashboard_service.sqlite3.connect", counting_connect):
                first = service._load_shared_deactivation_summary(account_names={"acc-1": "Alpha"})
                second = service._load_shared_deactivation_summary(account_names={"acc-1": "Alpha"})

        self.assertEqual(first.total_done_count, 1)
        self.assertEqual(second.total_done_count, 1)
        self.assertEqual(connect_calls, 1)

    def _create_telegram_products(self, db_path: Path, rows: list[dict[str, object]]) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE telegram_products (
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
                completed_at = str(row["completed_at"])
                conn.execute(
                    """
                    INSERT INTO telegram_products (
                        account_id,
                        channel_id,
                        message_id,
                        parsed_data,
                        created_product_id,
                        shafa_deactivated_at,
                        shafa_deleted_at,
                        deactivation_status,
                        deactivation_completed_at,
                        deactivation_error,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["account_id"],
                        row["channel_id"],
                        row["message_id"],
                        json.dumps({"name": row.get("product_title") or "Item"}),
                        row["shafa_product_id"],
                        row.get("shafa_deactivated_at"),
                        row.get("shafa_deleted_at"),
                        row.get("deactivation_status"),
                        completed_at,
                        row.get("deactivation_error"),
                        completed_at,
                    ),
                )

    def _create_shared_task(
        self,
        db_path: Path,
        *,
        account_id: str,
        telegram_product_key: str,
        shafa_product_id: str,
        completed_at: str,
    ) -> None:
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
            _prefix, channel_id, message_id = telegram_product_key.split(":")
            conn.execute(
                """
                INSERT INTO shared_telegram_products (
                    telegram_product_key, channel_id, message_id, product_title
                )
                VALUES (?, ?, ?, ?)
                """,
                (telegram_product_key, int(channel_id), int(message_id), "Shared"),
            )
            conn.execute(
                """
                INSERT INTO shared_deactivation_tasks (
                    task_id, telegram_product_key, reason, status, updated_at
                )
                VALUES ('task-1', ?, 'telegram_message_older_than_183_days',
                        'completed', ?)
                """,
                (telegram_product_key, completed_at),
            )
            conn.execute(
                """
                INSERT INTO shared_deactivation_task_accounts (
                    task_id,
                    telegram_product_key,
                    account_id,
                    shafa_product_id,
                    status,
                    completed_at,
                    updated_at
                )
                VALUES ('task-1', ?, ?, ?, 'completed', ?, ?)
                """,
                (
                    telegram_product_key,
                    account_id,
                    shafa_product_id,
                    completed_at,
                    completed_at,
                ),
            )

    def test_counts_direct_deactivation_rows_per_account_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "telegram.sqlite3"
            completed_at = datetime.now().replace(microsecond=0).isoformat()
            self._create_telegram_products(
                db_path,
                [
                    {
                        "account_id": "acc-1",
                        "channel_id": 21,
                        "message_id": 1001,
                        "shafa_product_id": "direct-a",
                        "deactivation_status": "completed",
                        "shafa_deactivated_at": completed_at,
                        "completed_at": completed_at,
                    },
                    {
                        "account_id": "acc-2",
                        "channel_id": 21,
                        "message_id": 1001,
                        "shafa_product_id": "direct-b",
                        "deactivation_status": "completed",
                        "shafa_deactivated_at": completed_at,
                        "completed_at": completed_at,
                    },
                    {
                        "account_id": "acc-1",
                        "channel_id": 22,
                        "message_id": 1002,
                        "shafa_product_id": "missing-a",
                        "deactivation_status": "skipped_not_found",
                        "shafa_deleted_at": completed_at,
                        "completed_at": completed_at,
                    },
                    {
                        "account_id": "acc-1",
                        "channel_id": 23,
                        "message_id": 1003,
                        "shafa_product_id": "pending-a",
                        "deactivation_status": "pending",
                        "completed_at": completed_at,
                    },
                ],
            )

            summary = self._service(db_path)._load_shared_deactivation_summary(
                account_names={"acc-1": "Alpha", "acc-2": "Beta"}
            )

        self.assertEqual(summary.deactivated_success_count, 2)
        self.assertEqual(summary.not_found_treated_as_done_count, 1)
        self.assertEqual(summary.total_done_count, 3)
        by_account = {row.account_id: row for row in summary.per_account}
        self.assertEqual(by_account["acc-1"].total_done_count, 2)
        self.assertEqual(by_account["acc-2"].total_done_count, 1)

    def test_shared_source_rows_are_not_double_counted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "telegram.sqlite3"
            completed_at = (
                datetime.now().replace(microsecond=0) - timedelta(minutes=1)
            ).isoformat()
            self._create_shared_task(
                db_path,
                account_id="acc-1",
                telegram_product_key="tg:31:1101",
                shafa_product_id="shared-source-a",
                completed_at=completed_at,
            )
            self._create_telegram_products(
                db_path,
                [
                    {
                        "account_id": "acc-1",
                        "channel_id": 31,
                        "message_id": 1101,
                        "shafa_product_id": "shared-source-a",
                        "deactivation_status": "completed",
                        "shafa_deactivated_at": completed_at,
                        "completed_at": completed_at,
                    },
                ],
            )

            summary = self._service(db_path)._load_shared_deactivation_summary(
                account_names={"acc-1": "Alpha"}
            )

        self.assertEqual(summary.deactivated_success_count, 1)
        self.assertEqual(summary.total_done_count, 1)


if __name__ == "__main__":
    unittest.main()
