import _test_path  # noqa: F401

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import data.db as db


def _load_shafa_logic_main():
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("shafa_logic_main_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load shafa_logic/main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


main = _load_shafa_logic_main()


class NewAccountQueueBootstrapTests(unittest.TestCase):
    def test_bootstrap_seeds_existing_products_once_and_removes_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            marker_path = (
                Path(temp_dir)
                / "accounts"
                / "acc-new"
                / "seed_existing_telegram_products.pending"
            )
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.touch()
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}

            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict(
                    "os.environ",
                    {
                        "SHAFA_ACCOUNT_ID": "acc-new",
                        "SHAFA_TELEGRAM_QUEUE_SEED_MARKER_PATH": str(marker_path),
                    },
                    clear=False,
                ),
            ):
                db.save_telegram_product(
                    11,
                    501,
                    "legacy-created",
                    parsed,
                    account_id=db.LEGACY_TELEGRAM_ACCOUNT_ID,
                )
                db.mark_telegram_product_created(
                    11,
                    501,
                    created_product_id="legacy-product-1",
                    account_id=db.LEGACY_TELEGRAM_ACCOUNT_ID,
                )
                db.save_telegram_product(11, 502, "queued", parsed, account_id="acc-1")
                db.save_telegram_product(11, 503, "skipped", parsed, account_id="acc-1")
                db.mark_telegram_product_created(
                    11,
                    503,
                    created_product_id="SKIPPED_INVALID_NAME",
                    account_id="acc-1",
                )

                first_seeded = main._bootstrap_new_account_telegram_queue_if_needed()
                second_seeded = main._bootstrap_new_account_telegram_queue_if_needed()
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-new")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, message_id, status
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-new",),
                    ).fetchall()

        self.assertEqual(first_seeded, 2)
        self.assertEqual(second_seeded, 0)
        self.assertFalse(marker_path.exists())
        self.assertEqual(cursor["last_checked_message_id"], 502)
        self.assertEqual(cursor["backfill_before_message_id"], 502)
        self.assertEqual(
            [tuple(row) for row in rows],
            [
                ("acc-new", 501, "queued"),
                ("acc-new", 502, "queued"),
            ],
        )

    def test_bootstrap_skips_old_feed_when_creation_db_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            creation_db_path = Path(temp_dir) / "creation.sqlite3"
            marker_path = (
                Path(temp_dir)
                / "accounts"
                / "acc-new"
                / "seed_existing_telegram_products.pending"
            )
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.touch()
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}

            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict(
                    "os.environ",
                    {
                        "SHAFA_ACCOUNT_ID": "acc-new",
                        "SHAFA_CREATION_PRODUCTS_DB_PATH": str(creation_db_path),
                        "SHAFA_TELEGRAM_QUEUE_SEED_MARKER_PATH": str(marker_path),
                    },
                    clear=False,
                ),
            ):
                db.save_telegram_product(
                    11,
                    501,
                    "legacy-created",
                    parsed,
                    account_id=db.LEGACY_TELEGRAM_ACCOUNT_ID,
                )
                db.mark_telegram_product_created(
                    11,
                    501,
                    created_product_id="legacy-product-1",
                    account_id=db.LEGACY_TELEGRAM_ACCOUNT_ID,
                )
                db.save_telegram_product(11, 502, "queued", parsed, account_id="acc-1")
                db.save_telegram_product(11, 503, "skipped", parsed, account_id="acc-1")
                db.mark_telegram_product_created(
                    11,
                    503,
                    created_product_id="SKIPPED_INVALID_NAME",
                    account_id="acc-1",
                )

                seeded = main._bootstrap_new_account_telegram_queue_if_needed()
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-new")

                with sqlite3.connect(creation_db_path) as conn:
                    creation_table = conn.execute(
                        """
                        SELECT 1
                        FROM sqlite_master
                        WHERE type = 'table' AND name = 'creation_products'
                        """
                    ).fetchone()
                with sqlite3.connect(telegram_db_path) as conn:
                    old_queue_count = conn.execute(
                        """
                        SELECT COUNT(*)
                        FROM telegram_products
                        WHERE account_id = ?
                        """,
                        ("acc-new",),
                    ).fetchone()[0]

        self.assertEqual(seeded, 0)
        self.assertFalse(marker_path.exists())
        self.assertIsNone(cursor["last_checked_message_id"])
        self.assertIsNone(cursor["backfill_before_message_id"])
        self.assertEqual(old_queue_count, 0)
        self.assertIsNone(creation_table)


if __name__ == "__main__":
    unittest.main()
