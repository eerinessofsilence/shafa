import _test_path  # noqa: F401

import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import controller.data_controller as dc
import data.db as db


class SharedDeactivationTests(unittest.TestCase):
    @contextmanager
    def _use_telegram_db(self, telegram_db_path: Path):
        db._DB_INITIALIZED_PATHS.discard(telegram_db_path)
        with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path)):
            with patch.dict(
                os.environ,
                {"SHAFA_SHARED_TELEGRAM_DB_PATH": str(telegram_db_path)},
            ):
                yield

    def _created_product(
        self,
        *,
        account_id: str,
        channel_id: int = 11,
        message_id: int = 501,
        product_id: str,
        message_date=None,
        name: str = "Item",
    ) -> None:
        parsed = {"name": name, "price": "1600", "size": "41"}
        db.save_telegram_product(
            channel_id,
            message_id,
            "raw",
            parsed,
            account_id=account_id,
            telegram_message_date=message_date,
        )
        db.mark_telegram_product_created(
            channel_id,
            message_id,
            created_product_id=product_id,
            account_id=account_id,
        )

    def _seed_shared_products(
        self,
        telegram_db_path: Path,
        *,
        count: int,
        message_date=None,
        account_id: str = "acc-1",
        start_message_id: int = 1000,
    ) -> None:
        db._ensure_db_initialized(telegram_db_path)
        normalized_date = (
            message_date.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(message_date, datetime)
            else message_date
        )
        rows = []
        memberships = []
        for offset in range(count):
            message_id = start_message_id + offset
            product_key = db.shared_telegram_product_key(11, message_id)
            rows.append(
                (
                    product_key,
                    11,
                    message_id,
                    normalized_date,
                    f"Item {offset}",
                    db.SHARED_PRODUCT_CHECK_UNCHECKED,
                    db.SHARED_PRODUCT_DEACTIVATION_NONE,
                    None,
                    None,
                )
            )
            memberships.append(
                (
                    product_key,
                    account_id,
                    f"product-{offset}",
                    f"Item {offset}",
                    db.SHARED_ACCOUNT_PRODUCT_ACTIVE,
                )
            )
        with sqlite3.connect(telegram_db_path) as conn:
            conn.executemany(
                """
                INSERT INTO shared_telegram_products (
                    telegram_product_key,
                    channel_id,
                    message_id,
                    telegram_message_date,
                    product_title,
                    checked_status,
                    deactivation_status,
                    last_checked_at,
                    next_check_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.executemany(
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
                memberships,
            )

    def test_planner_due_query_uses_next_check_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with self._use_telegram_db(telegram_db_path):
                db._ensure_db_initialized(telegram_db_path)
                with sqlite3.connect(telegram_db_path) as conn:
                    plan_rows = conn.execute(
                        """
                        EXPLAIN QUERY PLAN
                        SELECT *
                        FROM shared_telegram_products
                        WHERE (
                                checked_status IN (?, ?, ?)
                                OR last_checked_at IS NULL
                                OR last_checked_at <= datetime('now', '-1 day')
                              )
                          AND (
                                next_check_at IS NULL
                                OR next_check_at <= datetime('now')
                              )
                        ORDER BY
                            CASE checked_status
                                WHEN ? THEN 0
                                WHEN ? THEN 1
                                WHEN ? THEN 2
                                ELSE 3
                            END,
                            COALESCE(next_check_at, '') ASC,
                            updated_at ASC,
                            telegram_message_date ASC,
                            channel_id ASC,
                            message_id ASC
                        LIMIT ?
                        """,
                        (
                            db.SHARED_PRODUCT_CHECK_UNCHECKED,
                            db.SHARED_PRODUCT_CHECK_NEEDS_RETRY,
                            db.SHARED_PRODUCT_CHECK_DATE_MISSING,
                            db.SHARED_PRODUCT_CHECK_UNCHECKED,
                            db.SHARED_PRODUCT_CHECK_NEEDS_RETRY,
                            db.SHARED_PRODUCT_CHECK_DATE_MISSING,
                            100,
                        ),
                    ).fetchall()

        plan_text = "\n".join(str(row) for row in plan_rows)
        self.assertIn("idx_shared_telegram_products_due_next", plan_text)
        self.assertNotIn("SCAN shared_telegram_products", plan_text)

    def test_planner_reconciliation_is_limited_to_batch_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )

                with patch.object(
                    db,
                    "reconcile_shared_telegram_products",
                    wraps=db.reconcile_shared_telegram_products,
                ) as reconcile_mock:
                    db.plan_shared_deactivation_tasks(limit=17, dry_run=True)

        self.assertEqual(reconcile_mock.call_args.kwargs["limit"], 17)

    def test_planner_processes_only_default_batch_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._seed_shared_products(
                    telegram_db_path,
                    count=105,
                    message_date=old_date,
                )

                first = db.plan_shared_deactivation_tasks(dry_run=False)
                second = db.plan_shared_deactivation_tasks(dry_run=False)

                with sqlite3.connect(telegram_db_path) as conn:
                    task_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_tasks"
                    ).fetchone()[0]

        self.assertEqual(first["batch_size"], 100)
        self.assertEqual(first["processed_count"], 100)
        self.assertEqual(first["queued_count"], 100)
        self.assertEqual(first["has_more"], 1)
        self.assertEqual(second["processed_count"], 5)
        self.assertEqual(second["has_more"], 0)
        self.assertEqual(task_count, 105)

    def test_planner_respects_batch_size_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._seed_shared_products(
                    telegram_db_path,
                    count=12,
                    message_date=old_date,
                )
                with patch.dict(
                    os.environ,
                    {db.SHARED_DEACTIVATION_PLAN_BATCH_SIZE_ENV: "7"},
                ):
                    result = db.plan_shared_deactivation_tasks(dry_run=False)

        self.assertEqual(result["batch_size"], 7)
        self.assertEqual(result["processed_count"], 7)

    def test_planner_clamps_batch_size_env(self) -> None:
        with patch.dict(os.environ, {db.SHARED_DEACTIVATION_PLAN_BATCH_SIZE_ENV: "999"}):
            self.assertEqual(db.shared_deactivation_plan_batch_size(), 500)
        with patch.dict(os.environ, {db.SHARED_DEACTIVATION_PLAN_BATCH_SIZE_ENV: "0"}):
            self.assertEqual(db.shared_deactivation_plan_batch_size(), 1)

    def test_planner_clamps_explicit_limit(self) -> None:
        self.assertEqual(db.shared_deactivation_plan_batch_size(999), 500)
        self.assertEqual(db.shared_deactivation_plan_batch_size(0), 1)

    def test_shared_schema_creation_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with self._use_telegram_db(telegram_db_path):
                db.init_db(db_path=telegram_db_path)
                db._DB_INITIALIZED_PATHS.discard(telegram_db_path)
                db.init_db(db_path=telegram_db_path)

                with sqlite3.connect(telegram_db_path) as conn:
                    tables = {
                        row[0]
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }

        self.assertIn("shared_telegram_products", tables)
        self.assertIn("shared_telegram_product_accounts", tables)
        self.assertIn("shared_deactivation_tasks", tables)
        self.assertIn("shared_deactivation_task_accounts", tables)

    def test_reconcile_creates_one_product_and_multiple_memberships(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                self._created_product(
                    account_id="acc-2",
                    product_id="product-b",
                    message_date=old_date,
                )

                result = db.reconcile_shared_telegram_products()

                with sqlite3.connect(telegram_db_path) as conn:
                    product_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_telegram_products"
                    ).fetchone()[0]
                    membership_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_telegram_product_accounts"
                    ).fetchone()[0]

        self.assertEqual(result["products"], 1)
        self.assertEqual(result["memberships"], 2)
        self.assertEqual(product_count, 1)
        self.assertEqual(membership_count, 2)

    def test_planner_creates_one_parent_and_account_tasks_for_old_product(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                self._created_product(
                    account_id="acc-2",
                    product_id="product-b",
                    message_date=old_date,
                )

                result = db.plan_shared_deactivation_tasks(dry_run=False)

                with sqlite3.connect(telegram_db_path) as conn:
                    parent_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_tasks"
                    ).fetchone()[0]
                    child_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_task_accounts"
                    ).fetchone()[0]

        self.assertEqual(result["old"], 1)
        self.assertEqual(parent_count, 1)
        self.assertEqual(child_count, 2)

    def test_planner_is_idempotent_for_parent_and_account_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                self._created_product(
                    account_id="acc-2",
                    product_id="product-b",
                    message_date=old_date,
                )

                db.plan_shared_deactivation_tasks(dry_run=False)
                db.plan_shared_deactivation_tasks(dry_run=False)

                with sqlite3.connect(telegram_db_path) as conn:
                    parent_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_tasks"
                    ).fetchone()[0]
                    child_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_task_accounts"
                    ).fetchone()[0]

        self.assertEqual(parent_count, 1)
        self.assertEqual(child_count, 2)

    def test_new_membership_after_completed_parent_gets_account_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                self._created_product(
                    account_id="acc-2",
                    product_id="product-b",
                    message_date=old_date,
                )
                db.plan_shared_deactivation_tasks(dry_run=False)
                for account_id in ("acc-1", "acc-2"):
                    claimed = db.claim_shared_deactivation_task_for_account(
                        account_id=account_id
                    )
                    self.assertIsNotNone(claimed)
                    self.assertTrue(
                        db.complete_shared_deactivation_task_for_account(
                            task_id=claimed["task_id"],
                            account_id=account_id,
                            processing_token=claimed["processing_token"],
                        )
                    )

                self._created_product(
                    account_id="acc-3",
                    product_id="product-c",
                    message_date=old_date,
                )
                db.reconcile_shared_telegram_products(account_id="acc-3")
                db.plan_shared_deactivation_tasks(dry_run=False)

                with sqlite3.connect(telegram_db_path) as conn:
                    child_rows = conn.execute(
                        """
                        SELECT account_id, status
                        FROM shared_deactivation_task_accounts
                        ORDER BY account_id
                        """
                    ).fetchall()
                    parent_status = conn.execute(
                        "SELECT status FROM shared_deactivation_tasks"
                    ).fetchone()[0]

        self.assertEqual(
            [(row[0], row[1]) for row in child_rows],
            [
                ("acc-1", db.SHARED_ACCOUNT_TASK_COMPLETED),
                ("acc-2", db.SHARED_ACCOUNT_TASK_COMPLETED),
                ("acc-3", db.SHARED_ACCOUNT_TASK_PENDING),
            ],
        )
        self.assertIn(
            parent_status,
            {db.SHARED_TASK_STATUS_PENDING, db.SHARED_TASK_STATUS_PARTIAL},
        )

    def test_missing_date_is_marked_retryable_without_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            with self._use_telegram_db(telegram_db_path):
                self._created_product(account_id="acc-1", product_id="product-a")

                result = db.plan_shared_deactivation_tasks(dry_run=False)
                second = db.plan_shared_deactivation_tasks(dry_run=False)

                with sqlite3.connect(telegram_db_path) as conn:
                    row = conn.execute(
                        """
                        SELECT checked_status, next_check_at
                        FROM shared_telegram_products
                        """
                    ).fetchone()
                    task_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_tasks"
                    ).fetchone()[0]

        self.assertEqual(result["date_missing"], 1)
        self.assertEqual(second["processed_count"], 0)
        self.assertEqual(row[0], db.SHARED_PRODUCT_CHECK_DATE_MISSING)
        self.assertIsNotNone(row[1])
        self.assertEqual(task_count, 0)

    def test_young_product_does_not_create_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            fresh_date = datetime.now(timezone.utc) - timedelta(days=20)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=fresh_date,
                )

                result = db.plan_shared_deactivation_tasks(dry_run=False)
                second = db.plan_shared_deactivation_tasks(dry_run=False)

                with sqlite3.connect(telegram_db_path) as conn:
                    task_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_tasks"
                    ).fetchone()[0]

        self.assertEqual(result["fresh"], 1)
        self.assertEqual(second["processed_count"], 0)
        self.assertEqual(task_count, 0)

    def test_ambiguous_telegram_match_does_not_create_shared_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                db.init_db(db_path=telegram_db_path)
                db.save_telegram_product(
                    11,
                    501,
                    "raw",
                    {"name": "Duplicate title", "size": "41"},
                    account_id="acc-1",
                    telegram_message_date=old_date,
                )
                db.mark_telegram_product_created(
                    11,
                    501,
                    created_product_id="SKIPPED_AMBIGUOUS_TITLE_MATCH",
                    account_id="acc-1",
                )

                result = db.plan_shared_deactivation_tasks(dry_run=False)

                with sqlite3.connect(telegram_db_path) as conn:
                    task_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_tasks"
                    ).fetchone()[0]
                    membership_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_telegram_product_accounts"
                    ).fetchone()[0]

        self.assertEqual(result["old"], 0)
        self.assertEqual(task_count, 0)
        self.assertEqual(membership_count, 0)

    def test_missing_account_product_id_does_not_create_shared_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                db.save_telegram_product(
                    11,
                    501,
                    "raw",
                    {"name": "Missing identity", "size": "41"},
                    account_id="acc-1",
                    telegram_message_date=old_date,
                )
                with sqlite3.connect(telegram_db_path) as conn:
                    conn.execute(
                        """
                        UPDATE telegram_products
                        SET status = ?, created = 1, created_product_id = NULL
                        WHERE account_id = ? AND channel_id = ? AND message_id = ?
                        """,
                        (
                            db.TELEGRAM_PRODUCT_STATUS_CREATED,
                            "acc-1",
                            11,
                            501,
                        ),
                    )

                result = db.plan_shared_deactivation_tasks(dry_run=False)

                with sqlite3.connect(telegram_db_path) as conn:
                    task_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_deactivation_tasks"
                    ).fetchone()[0]
                    membership_count = conn.execute(
                        "SELECT COUNT(*) FROM shared_telegram_product_accounts"
                    ).fetchone()[0]

        self.assertEqual(result["old"], 0)
        self.assertEqual(task_count, 0)
        self.assertEqual(membership_count, 0)

    def test_account_claim_is_scoped_and_completion_requires_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                self._created_product(
                    account_id="acc-2",
                    product_id="product-b",
                    message_date=old_date,
                )
                db.plan_shared_deactivation_tasks(dry_run=False)

                acc1 = db.claim_shared_deactivation_task_for_account(account_id="acc-1")
                acc2 = db.claim_shared_deactivation_task_for_account(account_id="acc-2")

                wrong_account_completed = db.complete_shared_deactivation_task_for_account(
                    task_id=acc2["task_id"],
                    account_id="acc-1",
                    processing_token=acc2["processing_token"],
                )
                wrong_token_completed = db.complete_shared_deactivation_task_for_account(
                    task_id=acc1["task_id"],
                    account_id="acc-1",
                    processing_token="wrong-token",
                )
                completed = db.complete_shared_deactivation_task_for_account(
                    task_id=acc1["task_id"],
                    account_id="acc-1",
                    processing_token=acc1["processing_token"],
                )

        self.assertEqual(acc1["account_id"], "acc-1")
        self.assertEqual(acc1["shafa_product_id"], "product-a")
        self.assertEqual(acc2["account_id"], "acc-2")
        self.assertEqual(acc2["shafa_product_id"], "product-b")
        self.assertFalse(wrong_account_completed)
        self.assertFalse(wrong_token_completed)
        self.assertTrue(completed)

    def test_shared_completion_updates_source_row_for_only_that_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                self._created_product(
                    account_id="acc-2",
                    product_id="product-b",
                    message_date=old_date,
                )
                db.plan_shared_deactivation_tasks(dry_run=False)
                claimed = db.claim_shared_deactivation_task_for_account(account_id="acc-1")
                self.assertTrue(
                    db.complete_shared_deactivation_task_for_account(
                        task_id=claimed["task_id"],
                        account_id="acc-1",
                        processing_token=claimed["processing_token"],
                    )
                )
                db.reconcile_shared_telegram_products()

                with sqlite3.connect(telegram_db_path) as conn:
                    source_rows = conn.execute(
                        """
                        SELECT account_id, shafa_deactivated_at
                        FROM telegram_products
                        ORDER BY account_id
                        """
                    ).fetchall()
                    memberships = conn.execute(
                        """
                        SELECT account_id, account_product_status
                        FROM shared_telegram_product_accounts
                        ORDER BY account_id
                        """
                    ).fetchall()

        self.assertIsNotNone(source_rows[0][1])
        self.assertIsNone(source_rows[1][1])
        self.assertEqual(
            [(row[0], row[1]) for row in memberships],
            [
                ("acc-1", db.SHARED_ACCOUNT_PRODUCT_DEACTIVATED),
                ("acc-2", db.SHARED_ACCOUNT_PRODUCT_ACTIVE),
            ],
        )

    def test_shared_worker_treats_product_not_found_as_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                self._created_product(
                    account_id="acc-2",
                    product_id="product-b",
                    message_date=old_date,
                )
                db.plan_shared_deactivation_tasks(dry_run=False)

                def _not_found(_: str) -> None:
                    raise RuntimeError("product_not_found")

                with patch.object(dc, "mark_uploaded_product_inactive", lambda *args, **kwargs: None):
                    result = dc.process_shared_deactivation_queue_once(
                        account_id="acc-1",
                        dry_run=False,
                        deactivate_product_func=_not_found,
                        sleep_func=lambda _: None,
                    )
                retry = db.claim_shared_deactivation_task_for_account(account_id="acc-1")
                db.reconcile_shared_telegram_products()

                with sqlite3.connect(telegram_db_path) as conn:
                    task_rows = conn.execute(
                        """
                        SELECT account_id, status, retry_count
                        FROM shared_deactivation_task_accounts
                        ORDER BY account_id
                        """
                    ).fetchall()
                    source_rows = conn.execute(
                        """
                        SELECT account_id, shafa_deleted_at, shafa_deactivated_at
                        FROM telegram_products
                        ORDER BY account_id
                        """
                    ).fetchall()
                    memberships = conn.execute(
                        """
                        SELECT account_id, account_product_status
                        FROM shared_telegram_product_accounts
                        ORDER BY account_id
                        """
                    ).fetchall()

        self.assertEqual(result["claimed"], 1)
        self.assertEqual(result["not_found"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["deactivated"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertIsNone(retry)
        self.assertEqual(
            [(row[0], row[1], row[2]) for row in task_rows],
            [
                ("acc-1", db.SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND, 0),
                ("acc-2", db.SHARED_ACCOUNT_TASK_PENDING, 0),
            ],
        )
        self.assertIsNotNone(source_rows[0][1])
        self.assertIsNone(source_rows[0][2])
        self.assertIsNone(source_rows[1][1])
        self.assertIsNone(source_rows[1][2])
        self.assertEqual(
            [(row[0], row[1]) for row in memberships],
            [
                ("acc-1", db.SHARED_ACCOUNT_PRODUCT_MISSING),
                ("acc-2", db.SHARED_ACCOUNT_PRODUCT_ACTIVE),
            ],
        )

    def test_product_not_found_completion_is_account_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                self._created_product(
                    account_id="acc-2",
                    product_id="product-b",
                    message_date=old_date,
                )
                db.plan_shared_deactivation_tasks(dry_run=False)
                claimed = db.claim_shared_deactivation_task_for_account(account_id="acc-2")

                wrong_account_skipped = (
                    db.skip_shared_deactivation_task_not_found_for_account(
                        task_id=claimed["task_id"],
                        account_id="acc-1",
                        processing_token=claimed["processing_token"],
                    )
                )
                skipped = db.skip_shared_deactivation_task_not_found_for_account(
                    task_id=claimed["task_id"],
                    account_id="acc-2",
                    processing_token=claimed["processing_token"],
                )

                with sqlite3.connect(telegram_db_path) as conn:
                    source_rows = conn.execute(
                        """
                        SELECT account_id, shafa_deleted_at
                        FROM telegram_products
                        ORDER BY account_id
                        """
                    ).fetchall()

        self.assertFalse(wrong_account_skipped)
        self.assertTrue(skipped)
        self.assertIsNone(source_rows[0][1])
        self.assertIsNotNone(source_rows[1][1])

    def test_product_not_found_detection_does_not_match_auth_errors(self) -> None:
        self.assertTrue(
            dc._is_shafa_product_not_found_error(RuntimeError("product_not_found"))
        )
        self.assertTrue(
            dc._is_shafa_product_not_found_error(
                RuntimeError("includeIds: not_found")
            )
        )
        self.assertFalse(
            dc._is_shafa_product_not_found_error(
                RuntimeError("csrftoken not found in cookies")
            )
        )

    def test_shared_tables_are_not_created_in_account_db(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            account_db_path = Path(temp_dir) / "account.sqlite3"
            with self._use_telegram_db(telegram_db_path):
                db.init_db(db_path=account_db_path)
                db.init_db(db_path=telegram_db_path)
                with sqlite3.connect(account_db_path) as conn:
                    account_tables = {
                        row[0]
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
                with sqlite3.connect(telegram_db_path) as conn:
                    telegram_tables = {
                        row[0]
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }

        self.assertNotIn("shared_telegram_products", account_tables)
        self.assertIn("shared_telegram_products", telegram_tables)

    def test_expired_lease_can_be_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                db.plan_shared_deactivation_tasks(dry_run=False)

                first = db.claim_shared_deactivation_task_for_account(
                    account_id="acc-1",
                    lease_seconds=1,
                    now_ts=100,
                )
                second = db.claim_shared_deactivation_task_for_account(
                    account_id="acc-1",
                    lease_seconds=1,
                    now_ts=100.5,
                )
                third = db.claim_shared_deactivation_task_for_account(
                    account_id="acc-1",
                    lease_seconds=1,
                    now_ts=102,
                )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertIsNotNone(third)
        self.assertNotEqual(first["processing_token"], third["processing_token"])

    def test_failed_task_is_retry_scheduled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telegram_db_path = Path(temp_dir) / "telegram.sqlite3"
            old_date = datetime.now(timezone.utc) - timedelta(days=200)
            with self._use_telegram_db(telegram_db_path):
                self._created_product(
                    account_id="acc-1",
                    product_id="product-a",
                    message_date=old_date,
                )
                db.plan_shared_deactivation_tasks(dry_run=False)
                claimed = db.claim_shared_deactivation_task_for_account(
                    account_id="acc-1",
                    now_ts=100,
                )

                failed = db.fail_shared_deactivation_task_for_account(
                    task_id=claimed["task_id"],
                    account_id="acc-1",
                    processing_token=claimed["processing_token"],
                    error_message="temporary",
                    retry_delay_seconds=60,
                    max_retries=3,
                    now_ts=100,
                )
                too_early = db.claim_shared_deactivation_task_for_account(
                    account_id="acc-1",
                    now_ts=120,
                )
                retry = db.claim_shared_deactivation_task_for_account(
                    account_id="acc-1",
                    now_ts=200,
                )

        self.assertTrue(failed)
        self.assertIsNone(too_early)
        self.assertIsNotNone(retry)
        self.assertEqual(retry["retry_count"], 1)


if __name__ == "__main__":
    unittest.main()
