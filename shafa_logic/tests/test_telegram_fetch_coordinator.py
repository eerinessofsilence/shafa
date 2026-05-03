import _test_path  # noqa: F401

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
