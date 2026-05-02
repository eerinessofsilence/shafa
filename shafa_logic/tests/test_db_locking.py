import _test_path  # noqa: F401
import sqlite3

import data.db as db


def test_run_with_lock_retry_retries_locked_operational_error(monkeypatch) -> None:
    sleep_calls: list[float] = []
    calls = {"count": 0}

    monkeypatch.setattr(db.time, "sleep", lambda delay: sleep_calls.append(delay))

    def flaky_action() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    result = db._run_with_lock_retry(flaky_action, rollback=lambda: None)

    assert result == "ok"
    assert calls["count"] == 3
    assert len(sleep_calls) == 2


def test_connect_configures_busy_timeout_and_wal(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "shafa.sqlite3"
    monkeypatch.setattr(db, "_DB_INITIALIZED", False)

    db.init_db(db_path=db_path)

    with db._connect(db_path) as conn:
        journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        busy_timeout = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])
        synchronous = int(conn.execute("PRAGMA synchronous").fetchone()[0])

    assert journal_mode == "wal"
    assert busy_timeout == db._sqlite_busy_timeout_ms()
    assert synchronous in {1, 2}
