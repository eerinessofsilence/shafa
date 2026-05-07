import _test_path  # noqa: F401

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import controller.data_controller as dc
import data.db as db


class ProductQueueStatusTests(unittest.TestCase):
    def test_new_account_does_not_see_other_account_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}
            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-2"}, clear=False),
            ):
                db.save_telegram_product(11, 501, "valid-1", parsed, account_id="acc-1")

                result = dc._pick_next_product_for_upload()

        self.assertIsNone(result)

    def test_next_product_is_selected_only_from_current_account_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch(
                    "controller.data_controller._build_product_raw_data",
                    side_effect=lambda parsed: {
                        "name": parsed["name"],
                        "price": int(parsed["price"]),
                        "size": 176,
                    },
                ),
                patch("controller.data_controller.is_valid_product", return_value=True),
            ):
                db.save_telegram_product(
                    11,
                    501,
                    "",
                    {"name": "Nike Air Force 1", "price": "1600", "size": "41"},
                    account_id="acc-1",
                )
                db.save_telegram_product(
                    11,
                    999,
                    "",
                    {"name": "Nike Vomero", "price": "2600", "size": "42"},
                    account_id="acc-2",
                )

                result = dc._pick_next_product_for_upload()

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, message_id, status
                        FROM telegram_products
                        ORDER BY account_id, message_id
                        """
                    ).fetchall()

        self.assertIsNotNone(result)
        self.assertEqual(result["message_id"], 501)
        self.assertEqual(
            [(row[0], row[1], row[2]) for row in rows],
            [
                ("acc-1", 501, "processing"),
                ("acc-2", 999, "queued"),
            ],
        )

    def test_claim_next_product_is_scoped_by_account_and_marks_processing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}
            with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)):
                db.save_telegram_product(11, 501, "valid-1", parsed, account_id="acc-1")
                db.save_telegram_product(11, 501, "valid-1", parsed, account_id="acc-2")

                claimed_acc_1 = db.claim_next_telegram_product_for_creation(
                    account_id="acc-1"
                )
                claimed_acc_2 = db.claim_next_telegram_product_for_creation(
                    account_id="acc-2"
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, message_id, status
                        FROM telegram_products
                        ORDER BY account_id
                        """
                    ).fetchall()

        self.assertEqual(claimed_acc_1["account_id"], "acc-1")
        self.assertEqual(claimed_acc_1["status"], "processing")
        self.assertEqual(claimed_acc_2["account_id"], "acc-2")
        self.assertEqual(claimed_acc_2["status"], "processing")
        self.assertEqual(
            [(row[0], row[1], row[2]) for row in rows],
            [
                ("acc-1", 501, "processing"),
                ("acc-2", 501, "processing"),
            ],
        )

    def test_mark_created_and_skipped_write_terminal_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}
            with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)):
                db.save_telegram_product(11, 501, "valid-1", parsed, account_id="acc-1")
                db.save_telegram_product(11, 502, "valid-2", parsed, account_id="acc-1")

                db.claim_next_telegram_product_for_creation(account_id="acc-1")
                db.mark_telegram_product_created(
                    11,
                    502,
                    created_product_id="product-1",
                    account_id="acc-1",
                )
                db.claim_next_telegram_product_for_creation(account_id="acc-1")
                db.mark_telegram_product_created(
                    11,
                    501,
                    created_product_id="SKIPPED_INVALID_NAME",
                    account_id="acc-1",
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT message_id, status, created, created_product_id, last_create_error
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-1",),
                    ).fetchall()

        self.assertEqual(
            [(row[0], row[1], row[2], row[3], row[4]) for row in rows],
            [
                (501, "skipped", 1, "SKIPPED_INVALID_NAME", "SKIPPED_INVALID_NAME"),
                (502, "created", 1, "product-1", None),
            ],
        )

    def test_retryable_failure_becomes_failed_then_skipped_on_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}
            with (
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
            ):
                db.save_telegram_product(11, 501, "valid-1", parsed, account_id="acc-1")
                db.claim_next_telegram_product_for_creation(account_id="acc-1")

                attempts_1, skipped_1 = dc.register_product_failure(
                    501,
                    failure_reason="NO_UPLOADABLE_PHOTOS",
                    channel_id=11,
                )

                claim_after_failure = db.claim_next_telegram_product_for_creation(
                    account_id="acc-1"
                )
                attempts_2, skipped_2 = dc.register_product_failure(
                    501,
                    failure_reason="NO_UPLOADABLE_PHOTOS",
                    channel_id=11,
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    row = conn.execute(
                        """
                        SELECT status, create_attempts, created_product_id, last_create_error
                        FROM telegram_products
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        ("acc-1", 11, 501),
                    ).fetchone()

        self.assertEqual(attempts_1, 1)
        self.assertFalse(skipped_1)
        self.assertIsNotNone(claim_after_failure)
        self.assertEqual(claim_after_failure["status"], "processing")
        self.assertEqual(attempts_2, dc.MAX_PRODUCT_CREATE_ATTEMPTS)
        self.assertTrue(skipped_2)
        self.assertEqual(
            tuple(row),
            (
                "skipped",
                dc.MAX_PRODUCT_CREATE_ATTEMPTS,
                dc.SKIPPED_CREATE_RETRY_LIMIT,
                dc.SKIPPED_CREATE_RETRY_LIMIT,
            ),
        )

    def test_reset_and_exist_are_isolated_per_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}
            with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)):
                db.save_telegram_product(11, 501, "valid-1", parsed, account_id="acc-1")
                db.save_telegram_product(11, 502, "valid-2", parsed, account_id="acc-2")

                db.mark_telegram_product_created(
                    11,
                    501,
                    created_product_id="product-1",
                    account_id="acc-1",
                )

                self.assertTrue(db.telegram_products_exist(account_id="acc-1"))
                self.assertTrue(db.telegram_products_exist(account_id="acc-2"))

                reset_count = db.reset_telegram_products_created(account_id="acc-1")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, message_id, status, created, created_product_id
                        FROM telegram_products
                        ORDER BY account_id
                        """
                    ).fetchall()

        self.assertEqual(reset_count, 1)
        self.assertEqual(
            [(row[0], row[1], row[2], row[3], row[4]) for row in rows],
            [
                ("acc-1", 501, "queued", 0, None),
                ("acc-2", 502, "queued", 0, None),
            ],
        )

    def test_created_failed_and_skipped_are_isolated_per_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}
            with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)):
                db.save_telegram_product(11, 501, "valid", parsed, account_id="acc-created")
                db.save_telegram_product(11, 501, "valid", parsed, account_id="acc-failed")
                db.save_telegram_product(11, 501, "valid", parsed, account_id="acc-skipped")

                db.mark_telegram_product_created(
                    11,
                    501,
                    created_product_id="product-1",
                    account_id="acc-created",
                )
                db.increment_telegram_product_attempt(
                    11,
                    501,
                    failure_reason="NO_UPLOADABLE_PHOTOS",
                    account_id="acc-failed",
                )
                db.mark_telegram_product_created(
                    11,
                    501,
                    created_product_id="SKIPPED_INVALID_NAME",
                    account_id="acc-skipped",
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT account_id, status, created_product_id, create_attempts, last_create_error
                        FROM telegram_products
                        ORDER BY account_id
                        """
                    ).fetchall()

        self.assertEqual(
            [(row[0], row[1], row[2], row[3], row[4]) for row in rows],
            [
                ("acc-created", "created", "product-1", 0, None),
                ("acc-failed", "failed", None, 1, "NO_UPLOADABLE_PHOTOS"),
                ("acc-skipped", "skipped", "SKIPPED_INVALID_NAME", 0, "SKIPPED_INVALID_NAME"),
            ],
        )

    def test_seed_new_account_from_existing_db_copies_all_non_skipped_products(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            parsed = {"name": "Sneakers", "price": "1600", "size": "41"}
            with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)):
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
                db.save_telegram_product(11, 503, "failed", parsed, account_id="acc-2")
                db.increment_telegram_product_attempt(
                    11,
                    503,
                    failure_reason="NO_UPLOADABLE_PHOTOS",
                    account_id="acc-2",
                )
                db.save_telegram_product(11, 504, "skipped", parsed, account_id="acc-3")
                db.mark_telegram_product_created(
                    11,
                    504,
                    created_product_id="SKIPPED_INVALID_NAME",
                    account_id="acc-3",
                )

                seeded = db.seed_account_telegram_products_from_existing_db("acc-new")
                cursor = db.get_telegram_scan_cursor(11, account_id="acc-new")

                with sqlite3.connect(telegram_db_path) as conn:
                    rows = conn.execute(
                        """
                        SELECT message_id, status, created, created_product_id, create_attempts, last_create_error
                        FROM telegram_products
                        WHERE account_id = ?
                        ORDER BY message_id
                        """,
                        ("acc-new",),
                    ).fetchall()

        self.assertEqual(seeded, 3)
        self.assertEqual(cursor["last_checked_message_id"], 503)
        self.assertEqual(cursor["backfill_before_message_id"], 503)
        self.assertEqual(
            [tuple(row) for row in rows],
            [
                (501, "queued", 0, None, 0, None),
                (502, "queued", 0, None, 0, None),
                (503, "queued", 0, None, 0, None),
            ],
        )


if __name__ == "__main__":
    unittest.main()
