from __future__ import annotations

from datetime import datetime
from pathlib import Path

from shafa_control import LogRecord, LogStore


def test_log_store_writes_global_and_account_logs(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "runtime" / "logs")
    account_log = tmp_path / "accounts" / "acc-1" / "logs" / "app.log"
    record = LogRecord(
        timestamp=datetime(2026, 4, 13, 12, 0, 0),
        message="Telegram session saved",
        level="SUCCESS",
        account_id="acc-1",
        account_name="Account 1",
    )

    store.append(record, account_log_file=account_log)

    rendered = record.render()
    assert rendered in (tmp_path / "runtime" / "logs" / "all.log").read_text(encoding="utf-8")
    assert rendered in account_log.read_text(encoding="utf-8")


def test_log_store_filters_by_account_and_level(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "runtime" / "logs")
    store.append(
        LogRecord(datetime(2026, 4, 13, 12, 0, 0), "ok", "SUCCESS", "a1", "A1")
    )
    store.append(
        LogRecord(datetime(2026, 4, 13, 12, 1, 0), "bad", "ERROR", "a2", "A2")
    )

    assert [record.message for record in store.filtered(account_id="a1", level="ALL")] == ["ok"]
    assert [record.message for record in store.filtered(level="ERROR")] == ["bad"]
