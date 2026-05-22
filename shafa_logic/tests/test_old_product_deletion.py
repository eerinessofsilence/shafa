import _test_path  # noqa: F401

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import controller.data_controller as dc
import data.db as db


class OldTelegramProductDeactivationTests(unittest.TestCase):
    def test_expired_created_products_are_selected_by_telegram_message_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
            ):
                parsed = {"name": "Item", "price": "1600", "size": "41"}
                db.save_telegram_product(
                    11,
                    101,
                    "old",
                    parsed,
                    account_id="acc-1",
                    telegram_message_date=now - timedelta(days=200),
                )
                db.mark_telegram_product_created(
                    11,
                    101,
                    created_product_id="product-old",
                    account_id="acc-1",
                )
                db.save_telegram_product(
                    11,
                    102,
                    "fresh",
                    parsed,
                    account_id="acc-1",
                    telegram_message_date=now - timedelta(days=20),
                )
                db.mark_telegram_product_created(
                    11,
                    102,
                    created_product_id="product-fresh",
                    account_id="acc-1",
                )

                rows = db.list_expired_created_telegram_products(
                    older_than_days=183,
                    limit=10,
                    account_id="acc-1",
                )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message_id"], 101)
        self.assertEqual(rows[0]["created_product_id"], "product-old")

    def test_deactivate_old_telegram_products_marks_records_deactivated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)
            deactivated_ids: list[str] = []

            def _deactivator(product_id: str) -> None:
                deactivated_ids.append(product_id)

            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
            ):
                parsed = {"name": "Item", "price": "1600", "size": "41"}
                db.save_telegram_product(
                    11,
                    201,
                    "old",
                    parsed,
                    account_id="acc-1",
                    telegram_message_date=now - timedelta(days=190),
                )
                db.mark_telegram_product_created(
                    11,
                    201,
                    created_product_id="product-201",
                    account_id="acc-1",
                )

                result = dc.deactivate_old_telegram_products(
                    older_than_days=183,
                    limit=5,
                    sleep_seconds=0,
                    account_id="acc-1",
                    deactivate_product_func=_deactivator,
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    row = conn.execute(
                        """
                        SELECT shafa_deactivated_at, shafa_deactivate_attempts, last_shafa_deactivate_error
                        FROM telegram_products
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        ("acc-1", 11, 201),
                    ).fetchone()

        self.assertEqual(result["found"], 1)
        self.assertEqual(result["deactivated"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(deactivated_ids, ["product-201"])
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], 0)
        self.assertIsNone(row[2])

    def test_deactivate_failure_is_tracked_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)

            def _deactivator(_: str) -> None:
                raise RuntimeError("deactivate failed")

            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
            ):
                parsed = {"name": "Item", "price": "1600", "size": "41"}
                db.save_telegram_product(
                    11,
                    301,
                    "old",
                    parsed,
                    account_id="acc-1",
                    telegram_message_date=now - timedelta(days=190),
                )
                db.mark_telegram_product_created(
                    11,
                    301,
                    created_product_id="product-301",
                    account_id="acc-1",
                )

                result = dc.deactivate_old_telegram_products(
                    older_than_days=183,
                    limit=5,
                    sleep_seconds=0,
                    account_id="acc-1",
                    deactivate_product_func=_deactivator,
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    row = conn.execute(
                        """
                        SELECT shafa_deactivated_at, shafa_deactivate_attempts, last_shafa_deactivate_error
                        FROM telegram_products
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        ("acc-1", 11, 301),
                    ).fetchone()

        self.assertEqual(result["deactivated"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertIsNone(row[0])
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], "deactivate failed")


if __name__ == "__main__":
    unittest.main()
