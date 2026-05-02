from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_SQLITE_TIMEOUT_SECONDS = 30.0


def create_telegram_client(
    session_path: str | Path,
    api_id: int,
    api_hash: str,
    *,
    save_entities: bool = False,
    sqlite_timeout_seconds: float = DEFAULT_SQLITE_TIMEOUT_SECONDS,
    telegram_client_cls: Any | None = None,
):
    if telegram_client_cls is None:
        from telethon import TelegramClient

        telegram_client_cls = TelegramClient

    if not _is_telethon_client_class(telegram_client_cls):
        return telegram_client_cls(str(session_path), api_id, api_hash)

    session = BusyTimeoutSQLiteSession(
        session_path,
        save_entities=save_entities,
        sqlite_timeout_seconds=sqlite_timeout_seconds,
    )
    return telegram_client_cls(session, api_id, api_hash)


def _is_telethon_client_class(telegram_client_cls: Any) -> bool:
    module_name = str(getattr(telegram_client_cls, "__module__", ""))
    return module_name.startswith("telethon.")


class BusyTimeoutSQLiteSession:
    def __new__(
        cls,
        session_path: str | Path,
        *,
        save_entities: bool,
        sqlite_timeout_seconds: float,
    ):
        from telethon.sessions import SQLiteSession

        class _BusyTimeoutSQLiteSession(SQLiteSession):
            def __init__(self, session_id: str) -> None:
                self._sqlite_timeout_seconds = sqlite_timeout_seconds
                super().__init__(session_id)
                self.save_entities = save_entities

            def _cursor(self):
                if self._conn is None:
                    self._conn = sqlite3.connect(
                        self.filename,
                        timeout=self._sqlite_timeout_seconds,
                        check_same_thread=False,
                    )
                    self._conn.execute(
                        f"PRAGMA busy_timeout={int(self._sqlite_timeout_seconds * 1000)}",
                    )
                return self._conn.cursor()

        return _BusyTimeoutSQLiteSession(str(session_path))
