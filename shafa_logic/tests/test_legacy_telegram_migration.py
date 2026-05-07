import _test_path  # noqa: F401

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import data.db as db


class LegacyTelegramMigrationTests(unittest.TestCase):
    def test_legacy_telegram_products_migrate_into_hidden_legacy_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with sqlite3.connect(telegram_db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE telegram_products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        raw_message TEXT,
                        parsed_data TEXT,
                        created INTEGER NOT NULL DEFAULT 0,
                        created_product_id TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO telegram_products (
                        channel_id, message_id, raw_message, parsed_data, created, created_product_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        11,
                        501,
                        "valid-1",
                        json.dumps({"name": "Sneakers", "price": "1600", "size": "41"}),
                        0,
                        None,
                        "2026-05-01 10:00:00",
                        "2026-05-01 10:00:00",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO telegram_products (
                        channel_id, message_id, raw_message, parsed_data, created, created_product_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        11,
                        502,
                        "valid-2",
                        json.dumps({"name": "Sneakers", "price": "1700", "size": "42"}),
                        1,
                        "product-1",
                        "2026-05-01 10:01:00",
                        "2026-05-01 10:01:00",
                    ),
                )

            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
            ):
                db.init_db(telegram_db_path)

                self.assertEqual(db.count_legacy_telegram_products(), 2)
                self.assertIsNone(
                    db.claim_next_telegram_product_for_creation(account_id="acc-1")
                )
                seeded = db.seed_account_telegram_products_from_legacy("acc-1", [11])

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, message_id, status, created_product_id
                        FROM telegram_products
                        ORDER BY account_id, message_id
                        """
                    ).fetchall()

            self.assertEqual(seeded, 1)
            self.assertEqual(
                [(row[0], row[1], row[2], row[3]) for row in rows],
                [
                    ("__legacy_unassigned__", 501, "queued", None),
                    ("__legacy_unassigned__", 502, "created", "product-1"),
                    ("acc-1", 501, "queued", None),
                ],
            )

    def test_default_placeholder_rows_are_hidden_for_managed_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with sqlite3.connect(telegram_db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE telegram_products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id TEXT NOT NULL,
                        channel_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        raw_message TEXT,
                        parsed_data TEXT,
                        status TEXT NOT NULL DEFAULT 'queued',
                        created INTEGER NOT NULL DEFAULT 0,
                        created_product_id TEXT,
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                        status_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                        create_attempts INTEGER NOT NULL DEFAULT 0,
                        last_create_error TEXT,
                        UNIQUE(account_id, channel_id, message_id)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO telegram_products (
                        account_id, channel_id, message_id, raw_message, parsed_data, status, created
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "default",
                        11,
                        501,
                        "valid-1",
                        json.dumps({"name": "Sneakers", "price": "1600", "size": "41"}),
                        "queued",
                        0,
                    ),
                )

            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-2"}, clear=False),
            ):
                db.init_db(telegram_db_path)
                self.assertIsNone(
                    db.claim_next_telegram_product_for_creation(account_id="acc-2")
                )
                self.assertEqual(db.count_legacy_telegram_products(), 1)

    def test_new_account_does_not_enqueue_product_that_exists_in_legacy_db(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with sqlite3.connect(telegram_db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE telegram_products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        raw_message TEXT,
                        parsed_data TEXT,
                        created INTEGER NOT NULL DEFAULT 0,
                        created_product_id TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO telegram_products (
                        channel_id, message_id, raw_message, parsed_data, created, created_product_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        11,
                        501,
                        "legacy-created",
                        json.dumps({"name": "Sneakers", "price": "1600", "size": "41"}),
                        1,
                        "legacy-product-1",
                        "2026-05-01 10:00:00",
                        "2026-05-01 10:00:00",
                    ),
                )

            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
            ):
                db.init_db(telegram_db_path)

                inserted_existing = db.save_telegram_product(
                    11,
                    501,
                    "legacy-created",
                    {"name": "Sneakers", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                inserted_new = db.save_telegram_product(
                    11,
                    502,
                    "fresh",
                    {"name": "Sneakers", "price": "1700", "size": "42"},
                    account_id="acc-1",
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, message_id, status, created_product_id
                        FROM telegram_products
                        ORDER BY account_id, message_id
                        """
                    ).fetchall()

            self.assertFalse(inserted_existing)
            self.assertTrue(inserted_new)
            self.assertEqual(
                [(row[0], row[1], row[2], row[3]) for row in rows],
                [
                    ("__legacy_unassigned__", 501, "created", "legacy-product-1"),
                    ("acc-1", 502, "queued", None),
                ],
            )

    def test_legacy_fetch_state_is_archived_and_removed_from_active_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with sqlite3.connect(telegram_db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE telegram_fetch_state (
                        scope TEXT PRIMARY KEY,
                        last_fetch_at REAL,
                        lease_expires_at REAL,
                        lease_token TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO telegram_fetch_state (
                        scope, last_fetch_at, lease_expires_at, lease_token, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("telegram_feed:clothes", 1.0, 2.0, "legacy-token", "2026-05-01 10:00:00"),
                )
                conn.execute(
                    """
                    INSERT INTO telegram_fetch_state (
                        scope, last_fetch_at, lease_expires_at, lease_token, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        "telegram_feed:acc-1:clothes",
                        3.0,
                        4.0,
                        "modern-token",
                        "2026-05-01 10:01:00",
                    ),
                )

            with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)):
                db.init_db(telegram_db_path)

            with sqlite3.connect(telegram_db_path) as conn:
                active_rows = conn.execute(
                    "SELECT scope FROM telegram_fetch_state ORDER BY scope"
                ).fetchall()
                archived_rows = conn.execute(
                    "SELECT scope FROM telegram_fetch_state_legacy ORDER BY scope"
                ).fetchall()

            self.assertEqual([row[0] for row in active_rows], ["telegram_feed:acc-1:clothes"])
            self.assertEqual([row[0] for row in archived_rows], ["telegram_feed:clothes"])

    def test_legacy_scan_cursors_migrate_into_hidden_legacy_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with sqlite3.connect(telegram_db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE telegram_scan_cursors (
                        channel_id INTEGER PRIMARY KEY,
                        last_checked_message_id INTEGER,
                        last_scan_started_at TEXT,
                        last_scan_finished_at TEXT,
                        last_scan_error TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO telegram_scan_cursors (
                        channel_id, last_checked_message_id, last_scan_started_at, last_scan_finished_at, last_scan_error, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        11,
                        321,
                        "2026-05-01 10:00:00",
                        "2026-05-01 10:01:00",
                        None,
                        "2026-05-01 10:01:00",
                    ),
                )

            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict(os.environ, {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
            ):
                db.init_db(telegram_db_path)
                current_cursor = db.get_telegram_scan_cursor(11, account_id="acc-1")
                legacy_cursor = db.get_telegram_scan_cursor(
                    11,
                    account_id=db.LEGACY_TELEGRAM_ACCOUNT_ID,
                )

            self.assertIsNone(current_cursor["last_checked_message_id"])
            self.assertEqual(legacy_cursor["last_checked_message_id"], 321)


if __name__ == "__main__":
    unittest.main()
