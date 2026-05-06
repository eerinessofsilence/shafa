import _test_path  # noqa: F401
import asyncio
import shutil
import sqlite3

import pytest

from telegram_subscription.client import (
    TelegramSessionInUseError,
    _telegram_session_fingerprint,
    create_telegram_client,
)


class _FakeTelethonClient:
    __module__ = "telethon.fake"

    def __init__(self, session, api_id: int, api_hash: str) -> None:
        self.session = session
        self.api_id = api_id
        self.api_hash = api_hash
        self.connected = False

    async def connect(self):
        self.connected = True
        return None

    async def disconnect(self):
        self.connected = False
        return None


def _write_telegram_session(path, auth_key: bytes) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE version (
                version INTEGER PRIMARY KEY
            );
            CREATE TABLE sessions (
                dc_id INTEGER PRIMARY KEY,
                server_address TEXT,
                port INTEGER,
                auth_key BLOB,
                takeout_id INTEGER
            );
            CREATE TABLE entities (
                id INTEGER PRIMARY KEY,
                hash INTEGER NOT NULL,
                username TEXT,
                phone INTEGER,
                name TEXT,
                date INTEGER
            );
            CREATE TABLE sent_files (
                md5_digest BLOB,
                file_size INTEGER,
                type INTEGER,
                id INTEGER,
                hash INTEGER,
                PRIMARY KEY (md5_digest, file_size, type)
            );
            CREATE TABLE update_state (
                id INTEGER PRIMARY KEY,
                pts INTEGER,
                qts INTEGER,
                date INTEGER,
                seq INTEGER
            );
            """
        )
        conn.execute("INSERT INTO version(version) VALUES (7)")
        conn.execute(
            "INSERT INTO sessions(dc_id, server_address, port, auth_key, takeout_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (2, "149.154.167.50", 443, auth_key, None),
        )


def test_copied_telegram_sessions_share_same_fingerprint(tmp_path) -> None:
    source = tmp_path / "source.session"
    copied = tmp_path / "copied.session"
    _write_telegram_session(source, b"auth-key-1")
    shutil.copy2(source, copied)

    assert _telegram_session_fingerprint(source)
    assert _telegram_session_fingerprint(source) == _telegram_session_fingerprint(copied)


def test_create_telegram_client_blocks_parallel_usage_of_copied_session(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.session"
    copied = tmp_path / "copied.session"
    _write_telegram_session(source, b"auth-key-2")
    shutil.copy2(source, copied)
    monkeypatch.setenv("SHAFA_TELEGRAM_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("SHAFA_TELEGRAM_SESSION_LOCK_TIMEOUT_SECONDS", "0")
    monkeypatch.setattr(
        "telegram_subscription.client.BusyTimeoutSQLiteSession",
        lambda *_args, **_kwargs: "session",
    )

    first = create_telegram_client(
        source,
        777000,
        "hash",
        telegram_client_cls=_FakeTelethonClient,
    )
    second = create_telegram_client(
        copied,
        777000,
        "hash",
        telegram_client_cls=_FakeTelethonClient,
    )

    asyncio.run(first.connect())
    try:
        with pytest.raises(TelegramSessionInUseError):
            asyncio.run(second.connect())
    finally:
        asyncio.run(first.disconnect())

    asyncio.run(second.connect())
    asyncio.run(second.disconnect())


def test_create_telegram_client_waits_for_busy_session_instead_of_failing(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.session"
    copied = tmp_path / "copied.session"
    _write_telegram_session(source, b"auth-key-3")
    shutil.copy2(source, copied)
    monkeypatch.setenv("SHAFA_TELEGRAM_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.delenv("SHAFA_TELEGRAM_SESSION_LOCK_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(
        "telegram_subscription.client.BusyTimeoutSQLiteSession",
        lambda *_args, **_kwargs: "session",
    )

    first = create_telegram_client(
        source,
        777000,
        "hash",
        telegram_client_cls=_FakeTelethonClient,
    )
    second = create_telegram_client(
        copied,
        777000,
        "hash",
        telegram_client_cls=_FakeTelethonClient,
    )

    async def _exercise_queue() -> None:
        await first.connect()
        waiter = asyncio.create_task(second.connect())
        await asyncio.sleep(0.2)
        assert not waiter.done()
        await first.disconnect()
        await asyncio.wait_for(waiter, timeout=1.0)
        await second.disconnect()

    asyncio.run(_exercise_queue())
