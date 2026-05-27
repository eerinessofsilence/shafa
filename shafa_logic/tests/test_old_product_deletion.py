import _test_path  # noqa: F401

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import controller.data_controller as dc
import data.db as db


class OldTelegramProductDeactivationTests(unittest.TestCase):
    def _patch_account_db(self, account_db_path: Path):
        original_connect = db._connect
        default_db_path = Path(db.DB_PATH)
        db._DB_INITIALIZED_PATHS.discard(default_db_path)
        db._DB_INITIALIZED_PATHS.discard(account_db_path)
        return patch(
            "data.db._connect",
            side_effect=lambda db_path_arg=db.DB_PATH: original_connect(
                account_db_path
                if Path(db_path_arg) == default_db_path
                else Path(db_path_arg)
            ),
        )

    def test_backfill_created_product_message_date_from_existing_db(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)
            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
            ):
                parsed = {"name": "Item", "price": "1600", "size": "41"}
                db.save_telegram_product(11, 401, "target", parsed, account_id="acc-1")
                db.mark_telegram_product_created(
                    11,
                    401,
                    created_product_id="product-401",
                    account_id="acc-1",
                )
                db.save_telegram_product(
                    11,
                    401,
                    "source",
                    parsed,
                    account_id="acc-2",
                    telegram_message_date=now - timedelta(days=200),
                )

                result = dc.backfill_created_product_message_dates(
                    limit=10,
                    account_id="acc-1",
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    row = conn.execute(
                        """
                        SELECT telegram_message_date
                        FROM telegram_products
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        ("acc-1", 11, 401),
                    ).fetchone()

        self.assertEqual(result["updated_from_db"], 1)
        self.assertEqual(result["updated_from_telegram"], 0)
        self.assertEqual(result["remaining"], 0)
        self.assertIsNotNone(row[0])

    def test_backfill_created_product_message_date_from_telegram(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)

            class _FakeClient:
                def __init__(self, *_args, **_kwargs) -> None:
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return False

                async def get_messages(self, peer, ids):
                    return [
                        SimpleNamespace(id=int(message_id), date=now - timedelta(days=190))
                        for message_id in ids
                    ]

            with (
                patch.dict(
                    "os.environ",
                    {
                        "SHAFA_ACCOUNT_ID": "acc-1",
                        "SHAFA_TELEGRAM_API_ID": "1",
                        "SHAFA_TELEGRAM_API_HASH": "hash",
                    },
                    clear=False,
                ),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.object(dc, "api_id", 1),
                patch.object(dc, "api_hash", "hash"),
            ):
                parsed = {"name": "Item", "price": "1600", "size": "41"}
                db.save_telegram_product(11, 402, "target", parsed, account_id="acc-1")
                db.mark_telegram_product_created(
                    11,
                    402,
                    created_product_id="product-402",
                    account_id="acc-1",
                )

                result = dc.backfill_created_product_message_dates(
                    limit=10,
                    account_id="acc-1",
                    telegram_client_cls=_FakeClient,
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    row = conn.execute(
                        """
                        SELECT telegram_message_date
                        FROM telegram_products
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        ("acc-1", 11, 402),
                    ).fetchone()

        self.assertEqual(result["updated_from_db"], 0)
        self.assertEqual(result["updated_from_telegram"], 1)
        self.assertEqual(result["remaining"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertIsNotNone(row[0])

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
            account_db_path = Path(temp_dir) / "account.sqlite3"
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)
            deactivated_ids: list[str] = []

            def _deactivator(product_id: str) -> None:
                deactivated_ids.append(product_id)

            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                self._patch_account_db(account_db_path),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
            ):
                db.init_db(db_path=account_db_path)
                parsed = {"name": "Item", "price": "1600", "size": "41"}
                db.save_uploaded_product(
                    "product-201",
                    {"name": "Item", "price": 1600, "size": 41},
                    [],
                )
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
                with sqlite3.connect(account_db_path) as conn:
                    uploaded_row = conn.execute(
                        """
                        SELECT is_active, status_title
                        FROM uploaded_products
                        WHERE product_id = ?
                        """,
                        ("product-201",),
                    ).fetchone()

        self.assertEqual(result["found"], 1)
        self.assertEqual(result["deactivated"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(deactivated_ids, ["product-201"])
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], 0)
        self.assertIsNone(row[2])
        self.assertEqual(uploaded_row, (0, "Деактивовано"))

    def test_deactivate_old_telegram_products_checks_one_product_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account_db_path = Path(temp_dir) / "account.sqlite3"
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)
            deactivated_ids: list[str] = []

            def _deactivator(product_id: str) -> None:
                deactivated_ids.append(product_id)

            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                self._patch_account_db(account_db_path),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
            ):
                dc._OLD_PRODUCT_AGE_CHECK_CURSOR.clear()
                db.init_db(db_path=account_db_path)
                parsed = {"name": "Item", "price": "1600", "size": "41"}
                for message_id, product_id in ((231, "product-231"), (232, "product-232")):
                    db.save_uploaded_product(
                        product_id,
                        {"name": "Item", "price": 1600, "size": 41},
                        [],
                    )
                    db.save_telegram_product(
                        11,
                        message_id,
                        "old",
                        parsed,
                        account_id="acc-1",
                        telegram_message_date=now - timedelta(days=190),
                    )
                    db.mark_telegram_product_created(
                        11,
                        message_id,
                        created_product_id=product_id,
                        account_id="acc-1",
                    )

                first_result = dc.deactivate_old_telegram_products(
                    older_than_days=183,
                    sleep_seconds=0,
                    account_id="acc-1",
                    deactivate_product_func=_deactivator,
                )
                second_result = dc.deactivate_old_telegram_products(
                    older_than_days=183,
                    sleep_seconds=0,
                    account_id="acc-1",
                    deactivate_product_func=_deactivator,
                )

        self.assertEqual(first_result["checked"], 1)
        self.assertEqual(first_result["deactivated"], 1)
        self.assertEqual(second_result["checked"], 1)
        self.assertEqual(second_result["deactivated"], 1)
        self.assertEqual(deactivated_ids, ["product-231", "product-232"])

    def test_deactivate_old_telegram_products_sleeps_between_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)
            deactivated_ids: list[str] = []

            def _deactivator(product_id: str) -> None:
                deactivated_ids.append(product_id)

            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.object(dc.time, "sleep") as sleep_mock,
            ):
                parsed = {"name": "Item", "price": "1600", "size": "41"}
                db.save_telegram_product(
                    11,
                    211,
                    "old-1",
                    parsed,
                    account_id="acc-1",
                    telegram_message_date=now - timedelta(days=190),
                )
                db.mark_telegram_product_created(
                    11,
                    211,
                    created_product_id="product-211",
                    account_id="acc-1",
                )
                db.save_telegram_product(
                    11,
                    212,
                    "old-2",
                    parsed,
                    account_id="acc-1",
                    telegram_message_date=now - timedelta(days=191),
                )
                db.mark_telegram_product_created(
                    11,
                    212,
                    created_product_id="product-212",
                    account_id="acc-1",
                )

                result = dc.deactivate_old_telegram_products(
                    older_than_days=183,
                    limit=5,
                    sleep_seconds=1.5,
                    account_id="acc-1",
                    deactivate_product_func=_deactivator,
                )

        self.assertEqual(result["found"], 2)
        self.assertEqual(result["deactivated"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(deactivated_ids, ["product-212", "product-211"])
        sleep_mock.assert_called_once_with(1.5)

    def test_deactivate_old_telegram_products_logs_each_created_product_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account_db_path = Path(temp_dir) / "account.sqlite3"
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            now = datetime.now(timezone.utc)

            def _deactivator(_: str) -> None:
                return None

            with (
                patch.dict("os.environ", {"SHAFA_ACCOUNT_ID": "acc-1"}, clear=False),
                self._patch_account_db(account_db_path),
                patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)),
                patch.object(dc, "log") as log_mock,
            ):
                db.init_db(db_path=account_db_path)
                parsed = {"name": "Checked item", "price": "1600", "size": "41"}
                db.save_uploaded_product(
                    "product-221",
                    {"name": "Checked item", "price": 1600, "size": 41},
                    [],
                )
                db.save_telegram_product(
                    11,
                    221,
                    "old",
                    parsed,
                    account_id="acc-1",
                    telegram_message_date=now - timedelta(days=190),
                )
                db.mark_telegram_product_created(
                    11,
                    221,
                    created_product_id="product-221",
                    account_id="acc-1",
                )
                db.save_uploaded_product(
                    "product-222",
                    {"name": "Checked item", "price": 1600, "size": 41},
                    [],
                )
                db.save_telegram_product(
                    11,
                    222,
                    "fresh",
                    parsed,
                    account_id="acc-1",
                    telegram_message_date=now - timedelta(days=10),
                )
                db.mark_telegram_product_created(
                    11,
                    222,
                    created_product_id="product-222",
                    account_id="acc-1",
                )

                result = dc.deactivate_old_telegram_products(
                    older_than_days=183,
                    limit=5,
                    sleep_seconds=0,
                    account_id="acc-1",
                    deactivate_product_func=_deactivator,
                )

        self.assertEqual(result["checked"], 2)
        self.assertEqual(result["deactivated"], 1)
        info_messages = [
            call.args[1]
            for call in log_mock.call_args_list
            if len(call.args) >= 2 and call.args[0] == "INFO"
        ]
        self.assertTrue(
            any(
                "Проверяю созданный товар из базы аккаунта." in message
                and "account_id=acc-1." in message
                and "source=uploaded_products(account_db)." in message
                and "telegram_source=telegram_products(shared_account_db)." in message
                and "name=Checked item." in message
                and "product_id=product-221." in message
                and "checked_at_utc=" in message
                and "product_age=" in message
                and "threshold_days=183." in message
                and "telegram_age_days=" in message
                and "decision=eligible_for_deactivation." in message
                for message in info_messages
            )
        )
        self.assertTrue(
            any(
                "Проверяю созданный товар из базы аккаунта." in message
                and "account_id=acc-1." in message
                and "source=uploaded_products(account_db)." in message
                and "telegram_source=telegram_products(shared_account_db)." in message
                and "product_id=product-222." in message
                and "checked_at_utc=" in message
                and "product_age=" in message
                and "threshold_days=183." in message
                and "telegram_age_days=" in message
                and "decision=not_old_enough." in message
                for message in info_messages
            )
        )

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
