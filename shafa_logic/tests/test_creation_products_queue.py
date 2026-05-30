import _test_path  # noqa: F401

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import controller.data_controller as dc
import data.db as db


class CreationProductsQueueTests(unittest.TestCase):
    def _env(self, temp_dir: str) -> dict[str, str]:
        base = Path(temp_dir)
        return {
            "SHAFA_ACCOUNT_ID": "acc-1",
            "SHAFA_CREATION_PRODUCTS_DB_PATH": str(base / "creation.sqlite3"),
            "SHAFA_SHARED_TELEGRAM_DB_PATH": str(base / "telegram.sqlite3"),
        }

    def test_creation_db_schema_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", self._env(temp_dir), clear=False):
                db.upsert_creation_product(
                    11,
                    501,
                    "raw",
                    {"name": "Sneakers", "price": "1600", "size": "41"},
                )

                with sqlite3.connect(Path(temp_dir) / "creation.sqlite3") as conn:
                    tables = {
                        row[0]
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'"
                        )
                    }
                    columns = {
                        row[1]
                        for row in conn.execute("PRAGMA table_info(creation_products)")
                    }

        self.assertIn("creation_products", tables)
        self.assertIn("created_product_id", columns)
        self.assertIn("processing_expires_at", columns)

    def test_duplicate_creation_product_is_updated_not_inserted_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", self._env(temp_dir), clear=False):
                first = db.upsert_creation_product(
                    11,
                    501,
                    "old",
                    {"name": "Old", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                second = db.upsert_creation_product(
                    11,
                    501,
                    "new",
                    {"name": "New", "price": "1700", "size": "42"},
                    account_id="acc-1",
                )

                with sqlite3.connect(Path(temp_dir) / "creation.sqlite3") as conn:
                    row = conn.execute(
                        """
                        SELECT COUNT(*), raw_message, parsed_data
                        FROM creation_products
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        ("acc-1", 11, 501),
                    ).fetchone()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "new")
        self.assertIn("New", row[2])

    def test_scanner_writes_to_creation_db_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            msg = SimpleNamespace(
                id=501,
                message="raw",
                date=datetime(2026, 5, 30, tzinfo=timezone.utc),
            )
            with (
                patch.dict("os.environ", self._env(temp_dir), clear=False),
                patch(
                    "controller.data_controller._classify_product_message",
                    return_value=(
                        {"name": "Sneakers", "price": "1600", "size": "41"},
                        None,
                    ),
                ),
            ):
                result = dc._process_scanned_messages(
                    [msg],
                    channel_id=11,
                    account_id="acc-1",
                    stats=dc._new_scan_stats(),
                )

                with sqlite3.connect(Path(temp_dir) / "creation.sqlite3") as conn:
                    creation_count = conn.execute(
                        "SELECT COUNT(*) FROM creation_products"
                    ).fetchone()[0]
                with sqlite3.connect(Path(temp_dir) / "telegram.sqlite3") as conn:
                    has_old_table = conn.execute(
                        """
                        SELECT 1
                        FROM sqlite_master
                        WHERE type = 'table' AND name = 'telegram_products'
                        """
                    ).fetchone()
                    old_count = (
                        conn.execute("SELECT COUNT(*) FROM telegram_products").fetchone()[0]
                        if has_old_table
                        else 0
                    )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(creation_count, 1)
        self.assertEqual(old_count, 0)

    def test_creation_picker_uses_creation_db_and_bypasses_old_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = self._env(temp_dir)
            with (
                patch.dict("os.environ", env, clear=False),
                patch(
                    "controller.data_controller._build_product_raw_data",
                    side_effect=lambda parsed: {
                        "name": parsed["name"],
                        "price": int(parsed["price"]),
                        "size": 176,
                    },
                ),
                patch(
                    "controller.data_controller.get_next_uncreated_telegram_product",
                    side_effect=AssertionError("old queue should not be scanned"),
                ),
            ):
                db.save_telegram_product(
                    11,
                    999,
                    "",
                    {"name": "Old", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                db.upsert_creation_product(
                    11,
                    501,
                    "",
                    {"name": "New", "price": "1700", "size": "42"},
                    account_id="acc-1",
                )

                product = dc._pick_next_product_for_upload()

        self.assertIsNotNone(product)
        self.assertEqual(product["message_id"], 501)

    def test_only_ready_statuses_and_expired_processing_are_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", self._env(temp_dir), clear=False):
                db.upsert_creation_product(
                    11,
                    501,
                    "",
                    {"name": "Ready", "price": "1600", "size": "41"},
                    account_id="acc-1",
                    status=db.CREATION_PRODUCT_STATUS_READY,
                )
                db.upsert_creation_product(
                    11,
                    502,
                    "",
                    {"name": "New", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                db.upsert_creation_product(
                    11,
                    503,
                    "",
                    {"name": "Failed", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                db.mark_creation_product_failed(11, 503, "old failure", account_id="acc-1")
                db.claim_creation_product_for_creation(account_id="acc-1")
                db.mark_creation_product_failed(11, 501, "boom", account_id="acc-1")
                first_ready = db.list_ready_creation_products(account_id="acc-1")

                claimed = db.claim_creation_product_for_creation(account_id="acc-1")
                second_ready = db.list_ready_creation_products(account_id="acc-1")

                with sqlite3.connect(Path(temp_dir) / "creation.sqlite3") as conn:
                    conn.execute(
                        """
                        UPDATE creation_products
                        SET processing_expires_at = 1
                        WHERE message_id = ?
                        """,
                        (claimed["message_id"],),
                    )
                expired_ready = db.list_ready_creation_products(account_id="acc-1")

        self.assertEqual([row["message_id"] for row in first_ready], [502])
        self.assertEqual(claimed["message_id"], 502)
        self.assertEqual(second_ready, [])
        self.assertEqual([row["message_id"] for row in expired_ready], [502])

    def test_terminal_statuses_are_not_selected_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", self._env(temp_dir), clear=False):
                db.upsert_creation_product(
                    11,
                    501,
                    "",
                    {"name": "Created", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                db.upsert_creation_product(
                    11,
                    502,
                    "",
                    {"name": "Skipped", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                db.mark_creation_product_created(11, 501, "product-501", account_id="acc-1")
                db.mark_creation_product_skipped(11, 502, "manual", account_id="acc-1")

                db._CREATION_DB_INITIALIZED_PATHS.clear()
                ready = db.list_ready_creation_products(account_id="acc-1")

        self.assertEqual(ready, [])

    def test_success_failure_and_skip_mark_creation_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", self._env(temp_dir), clear=False):
                for message_id in (501, 502, 503):
                    db.upsert_creation_product(
                        11,
                        message_id,
                        "",
                        {"name": "Sneakers", "price": "1600", "size": "41"},
                        account_id="acc-1",
                    )

                db.claim_creation_product_for_creation(account_id="acc-1")
                dc.mark_product_created(501, "product-501", channel_id=11)
                db.claim_creation_product_for_creation(account_id="acc-1")
                dc.register_product_failure(502, "CREATE_FAILED", channel_id=11)
                db.claim_creation_product_for_creation(account_id="acc-1")
                dc.mark_product_created(503, "SKIPPED_INVALID", channel_id=11)

                with sqlite3.connect(Path(temp_dir) / "creation.sqlite3") as conn:
                    rows = conn.execute(
                        """
                        SELECT message_id, status, created_product_id, last_error, skip_reason
                        FROM creation_products
                        ORDER BY message_id
                        """
                    ).fetchall()
                with sqlite3.connect(Path(temp_dir) / "telegram.sqlite3") as conn:
                    mapping = conn.execute(
                        """
                        SELECT status, created_product_id
                        FROM telegram_products
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        ("acc-1", 11, 501),
                    ).fetchone()
                    shared_mapping = conn.execute(
                        """
                        SELECT shafa_product_id
                        FROM shared_telegram_product_accounts
                        WHERE account_id = ?
                        """,
                        ("acc-1",),
                    ).fetchone()

        self.assertEqual(
            [tuple(row) for row in rows],
            [
                (501, "created", "product-501", None, None),
                (502, "failed", None, "CREATE_FAILED", None),
                (503, "skipped", "SKIPPED_INVALID", None, "SKIPPED_INVALID"),
            ],
        )
        self.assertEqual(tuple(mapping), ("created", "product-501"))
        self.assertEqual(shared_mapping[0], "product-501")

    def test_deactivation_tables_work_independently_from_creation_db(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", self._env(temp_dir), clear=False):
                db.upsert_creation_product(
                    11,
                    501,
                    "",
                    {"name": "Queue", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                db.upsert_created_telegram_product_mapping(
                    11,
                    601,
                    "",
                    {"name": "Created", "price": "1600", "size": "41"},
                    "product-601",
                    account_id="acc-1",
                )

                queued = db.enqueue_telegram_product_deactivation(
                    11,
                    601,
                    account_id="acc-1",
                )

                with sqlite3.connect(Path(temp_dir) / "creation.sqlite3") as conn:
                    creation_status = conn.execute(
                        "SELECT status FROM creation_products WHERE message_id = 501"
                    ).fetchone()[0]
                with sqlite3.connect(Path(temp_dir) / "telegram.sqlite3") as conn:
                    deactivation_status = conn.execute(
                        """
                        SELECT deactivation_status
                        FROM telegram_products
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        ("acc-1", 11, 601),
                    ).fetchone()[0]

        self.assertTrue(queued)
        self.assertEqual(creation_status, "new")
        self.assertEqual(deactivation_status, db.TELEGRAM_DEACTIVATION_STATUS_PENDING)


if __name__ == "__main__":
    unittest.main()
