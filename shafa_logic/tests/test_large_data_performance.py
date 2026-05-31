import _test_path  # noqa: F401

import os
import sqlite3
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import data.db as db
from telegram_accounts_api.services.dashboard_service import DashboardService
from telegram_accounts_api.utils.account_logging import AccountLogStore


pytestmark = pytest.mark.skipif(
    os.getenv("SHAFA_RUN_LARGE_DATA_PERF_TESTS") != "1",
    reason="large generated SQLite performance tests are opt-in",
)

LARGE_ROW_COUNT = int(os.getenv("SHAFA_LARGE_DATA_PERF_ROWS", "650000"))


def _insert_large_telegram_products(conn: sqlite3.Connection, row_count: int) -> None:
    conn.executescript(
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
        );
        """
    )
    batch = []
    for index in range(row_count):
        deactivation_status = None
        deactivated_at = None
        deleted_at = None
        completed_at = None
        if index % 20 == 0:
            deactivation_status = "completed"
            deactivated_at = "2026-01-01 00:00:00"
            completed_at = "2026-01-02 00:00:00"
        elif index % 33 == 0:
            deactivation_status = "skipped_not_found"
            deleted_at = "2026-01-01 00:00:00"
            completed_at = "2026-01-02 00:00:00"
        elif index % 47 == 0:
            deleted_at = "2026-01-01 00:00:00"
            completed_at = "2026-01-02 00:00:00"
        batch.append(
            (
                f"acc-{index % 12}",
                index % 1000,
                index,
                '{"name":"Item"}',
                "created",
                1,
                f"product-{index}",
                deactivated_at,
                deleted_at,
                deactivation_status,
                completed_at,
                None,
                "2026-01-02 00:00:00",
            )
        )
        if len(batch) >= 10_000:
            conn.executemany(
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            batch.clear()
    if batch:
        conn.executemany(
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )


def _create_direct_deactivation_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_completed
            ON telegram_products(
                deactivation_status,
                shafa_deactivated_at,
                deactivation_completed_at,
                updated_at,
                account_id
            );
        CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_skipped
            ON telegram_products(
                deactivation_status,
                deactivation_completed_at,
                updated_at,
                account_id
            );
        CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_deleted
            ON telegram_products(
                shafa_deleted_at,
                shafa_deactivated_at,
                deactivation_completed_at,
                updated_at,
                account_id
            );
        """
    )


def _insert_existing_large_telegram_products(
    conn: sqlite3.Connection,
    row_count: int,
) -> None:
    batch = []
    for index in range(row_count):
        batch.append(
            (
                f"acc-{index % 12}",
                index % 1000,
                index,
                "raw",
                '{"name":"Item"}',
                db.TELEGRAM_PRODUCT_STATUS_CREATED,
                1,
                f"product-{index}",
                "2025-01-01 00:00:00",
            )
        )
        if len(batch) >= 10_000:
            conn.executemany(
                """
                INSERT INTO telegram_products (
                    account_id,
                    channel_id,
                    message_id,
                    raw_message,
                    parsed_data,
                    status,
                    created,
                    created_product_id,
                    telegram_message_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            batch.clear()
    if batch:
        conn.executemany(
            """
            INSERT INTO telegram_products (
                account_id,
                channel_id,
                message_id,
                raw_message,
                parsed_data,
                status,
                created,
                created_product_id,
                telegram_message_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )


def _insert_large_shared_products(conn: sqlite3.Connection, row_count: int) -> None:
    batch = []
    for index in range(row_count):
        if index < 100:
            checked_status = db.SHARED_PRODUCT_CHECK_UNCHECKED
            next_check_at = None
        elif index % 10_000 == 0:
            checked_status = db.SHARED_PRODUCT_CHECK_DATE_MISSING
            next_check_at = "2026-01-01 00:00:00"
        else:
            checked_status = db.SHARED_PRODUCT_CHECK_FRESH
            next_check_at = "2027-01-01 00:00:00"
        batch.append(
            (
                f"tg:{index % 1000}:{index}",
                index % 1000,
                index,
                "2025-01-01 00:00:00",
                "Item",
                checked_status,
                "none",
                "2026-05-01 00:00:00",
                next_check_at,
            )
        )
        if len(batch) >= 10_000:
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
                batch,
            )
            batch.clear()
    if batch:
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
            batch,
        )


def test_dashboard_direct_stats_are_cached_on_large_telegram_products() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "large.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            _insert_large_telegram_products(conn, LARGE_ROW_COUNT)
            _create_direct_deactivation_indexes(conn)
            conn.commit()
        service = DashboardService(
            account_service=SimpleNamespace(
                session_store=SimpleNamespace(shared_telegram_db_file=lambda: db_path)
            ),
            log_store=AccountLogStore(),
            deactivation_cache_ttl_seconds=30,
        )

        started_at = time.perf_counter()
        first = service._load_shared_deactivation_summary(account_names={})
        first_ms = (time.perf_counter() - started_at) * 1000
        started_at = time.perf_counter()
        second = service._load_shared_deactivation_summary(account_names={})
        second_ms = (time.perf_counter() - started_at) * 1000
        print(
            "dashboard_direct_stats "
            f"rows={LARGE_ROW_COUNT} first_ms={first_ms:.2f} cached_ms={second_ms:.2f}"
        )

    assert first.total_done_count > 0
    assert second.total_done_count == first.total_done_count
    assert first_ms < 2_000
    assert second_ms < 50


def test_shared_planner_selects_due_rows_without_scanning_fresh_large_table() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "large.sqlite3"
        db._DB_INITIALIZED_PATHS.discard(db_path)
        with patch.object(db, "TELEGRAM_PRODUCTS_DB_PATH", str(db_path)):
            with patch.dict(os.environ, {"SHAFA_SHARED_TELEGRAM_DB_PATH": str(db_path)}):
                db._ensure_db_initialized(db_path)
                with sqlite3.connect(db_path) as conn:
                    conn.execute("PRAGMA synchronous=OFF")
                    _insert_existing_large_telegram_products(conn, LARGE_ROW_COUNT)
                    _insert_large_shared_products(conn, LARGE_ROW_COUNT)
                    conn.commit()

                started_at = time.perf_counter()
                result = db.plan_shared_deactivation_tasks(limit=100, dry_run=True)
                duration_ms = (time.perf_counter() - started_at) * 1000
                print(
                    "shared_planner_due "
                    f"rows={LARGE_ROW_COUNT} telegram_rows={LARGE_ROW_COUNT} "
                    f"checked={result['checked']} "
                    f"duration_ms={duration_ms:.2f}"
                )

    assert result["checked"] == 100
    assert duration_ms < 2_000
