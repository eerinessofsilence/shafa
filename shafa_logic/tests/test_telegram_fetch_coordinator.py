import _test_path  # noqa: F401

import sqlite3
from datetime import datetime, timedelta, timezone

import data.db as db


def test_claim_telegram_fetch_respects_lease_and_cooldown(tmp_path, monkeypatch) -> None:
    telegram_db_path = tmp_path / "telegram.sqlite3"
    monkeypatch.setattr(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path))

    status, lease_token = db.claim_telegram_fetch(
        "clothes",
        min_interval_seconds=60,
        lease_seconds=30,
        now_ts=1000,
    )

    assert status == "acquired"
    assert lease_token

    status, next_token = db.claim_telegram_fetch(
        "clothes",
        min_interval_seconds=60,
        lease_seconds=30,
        now_ts=1001,
    )

    assert status == "in_progress"
    assert next_token is None

    db.finish_telegram_fetch(
        "clothes",
        lease_token,
        success=True,
        finished_at_ts=1005,
    )

    status, next_token = db.claim_telegram_fetch(
        "clothes",
        min_interval_seconds=60,
        lease_seconds=30,
        now_ts=1006,
    )

    assert status == "not_due"
    assert next_token is None

    status, next_token = db.claim_telegram_fetch(
        "clothes",
        min_interval_seconds=60,
        lease_seconds=30,
        now_ts=1066,
    )

    assert status == "acquired"
    assert next_token


def test_failed_telegram_fetch_releases_slot_without_cooldown(tmp_path, monkeypatch) -> None:
    telegram_db_path = tmp_path / "telegram.sqlite3"
    monkeypatch.setattr(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path))

    status, lease_token = db.claim_telegram_fetch(
        "clothes",
        min_interval_seconds=60,
        lease_seconds=30,
        now_ts=2000,
    )

    assert status == "acquired"
    assert lease_token

    db.finish_telegram_fetch(
        "clothes",
        lease_token,
        success=False,
        finished_at_ts=2005,
    )

    status, next_token = db.claim_telegram_fetch(
        "clothes",
        min_interval_seconds=60,
        lease_seconds=30,
        now_ts=2006,
    )

    assert status == "acquired"
    assert next_token


def test_fetch_state_isolated_by_account_scoped_scope(tmp_path, monkeypatch) -> None:
    telegram_db_path = tmp_path / "telegram.sqlite3"
    monkeypatch.setattr(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path))

    status_1, lease_token_1 = db.claim_telegram_fetch(
        "telegram_feed:acc-1:clothes",
        min_interval_seconds=60,
        lease_seconds=30,
        now_ts=3000,
    )
    status_2, lease_token_2 = db.claim_telegram_fetch(
        "telegram_feed:acc-2:clothes",
        min_interval_seconds=60,
        lease_seconds=30,
        now_ts=3001,
    )

    assert status_1 == "acquired"
    assert lease_token_1
    assert status_2 == "acquired"
    assert lease_token_2
    assert lease_token_1 != lease_token_2


def test_claim_telegram_product_deactivation_respects_lease(tmp_path, monkeypatch) -> None:
    telegram_db_path = tmp_path / "telegram.sqlite3"
    monkeypatch.setattr(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path))
    message_date = datetime.now(timezone.utc) - timedelta(days=200)

    db.save_telegram_product(
        11,
        501,
        "old",
        {"name": "Item", "price": "1600", "size": "41"},
        account_id="acc-1",
        telegram_message_date=message_date,
    )
    db.mark_telegram_product_created(
        11,
        501,
        created_product_id="product-501",
        account_id="acc-1",
    )

    queued = db.enqueue_expired_telegram_products_for_deactivation(
        older_than_days=183,
        limit=10,
        account_id="acc-1",
    )
    first = db.claim_telegram_product_deactivation(
        account_id="acc-1",
        lease_seconds=30,
        now_ts=1000,
    )
    second = db.claim_telegram_product_deactivation(
        account_id="acc-1",
        lease_seconds=30,
        now_ts=1001,
    )
    third = db.claim_telegram_product_deactivation(
        account_id="acc-1",
        lease_seconds=30,
        now_ts=1031,
    )

    assert queued == 1
    assert first is not None
    assert first["message_id"] == 501
    assert first["deactivation_status"] == db.TELEGRAM_DEACTIVATION_STATUS_PROCESSING
    assert first["deactivation_processing_token"]
    assert second is None
    assert third is not None
    assert third["deactivation_processing_token"] != first["deactivation_processing_token"]


def test_finish_telegram_product_deactivation_requires_matching_token(
    tmp_path,
    monkeypatch,
) -> None:
    telegram_db_path = tmp_path / "telegram.sqlite3"
    monkeypatch.setattr(db, "TELEGRAM_PRODUCTS_DB_PATH", str(telegram_db_path))
    message_date = datetime.now(timezone.utc) - timedelta(days=200)

    db.save_telegram_product(
        11,
        502,
        "old",
        {"name": "Item", "price": "1600", "size": "41"},
        account_id="acc-1",
        telegram_message_date=message_date,
    )
    db.mark_telegram_product_created(
        11,
        502,
        created_product_id="product-502",
        account_id="acc-1",
    )
    db.enqueue_expired_telegram_products_for_deactivation(
        older_than_days=183,
        limit=10,
        account_id="acc-1",
    )
    claimed = db.claim_telegram_product_deactivation(
        account_id="acc-1",
        lease_seconds=30,
        now_ts=2000,
    )

    assert claimed is not None
    assert not db.finish_telegram_product_deactivation(
        11,
        502,
        "wrong-token",
        success=True,
        account_id="acc-1",
    )
    assert db.finish_telegram_product_deactivation(
        11,
        502,
        claimed["deactivation_processing_token"],
        success=True,
        account_id="acc-1",
    )

    with sqlite3.connect(telegram_db_path) as conn:
        row = conn.execute(
            """
            SELECT shafa_deactivated_at, deactivation_status, deactivation_completed_at
            FROM telegram_products
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            ("acc-1", 11, 502),
        ).fetchone()

    assert row[0] is not None
    assert row[1] == db.TELEGRAM_DEACTIVATION_STATUS_COMPLETED
    assert row[2] is not None
