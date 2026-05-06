from __future__ import annotations

import asyncio
import hashlib
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_SQLITE_TIMEOUT_SECONDS = 30.0
DEFAULT_SESSION_LOCK_TIMEOUT_SECONDS = 15.0
_SESSION_LOCK_RETRY_INTERVAL_SECONDS = 0.1
_SESSION_LOCKS: dict[str, threading.Lock] = {}
_SESSION_LOCKS_GUARD = threading.Lock()


class TelegramSessionInUseError(RuntimeError):
    pass


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
    return LockedTelegramClient(
        telegram_client_cls(session, api_id, api_hash),
        session_path=session_path,
    )


def _is_telethon_client_class(telegram_client_cls: Any) -> bool:
    module_name = str(getattr(telegram_client_cls, "__module__", ""))
    return module_name.startswith("telethon.")


def telegram_session_in_use_message(session_path: str | Path) -> str:
    return (
        "Telegram session is already in use by another running process or account. "
        "Wait until the other Telegram operation finishes or use a different Telegram session. "
        f"session_path={Path(session_path)}"
    )


def _session_lock_timeout_seconds() -> float:
    raw = os.getenv("SHAFA_TELEGRAM_SESSION_LOCK_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SESSION_LOCK_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_SESSION_LOCK_TIMEOUT_SECONDS
    return max(value, 0.0)


def _session_lock_dir() -> Path:
    raw = os.getenv("SHAFA_TELEGRAM_LOCK_DIR", "").strip()
    if raw:
        path = Path(raw)
    else:
        path = Path(tempfile.gettempdir()) / "shafa_telegram_locks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_lock_key(session_path: str | Path) -> str:
    fingerprint = _telegram_session_fingerprint(session_path)
    identity = fingerprint or str(Path(session_path).expanduser().resolve())
    return hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()


def _session_lock_path(session_path: str | Path) -> Path:
    return _session_lock_dir() / f"{_session_lock_key(session_path)}.lock"


def _telegram_session_fingerprint(session_path: str | Path) -> str:
    path = Path(session_path).expanduser()
    if not path.exists() or not path.is_file():
        return ""
    try:
        header = path.read_bytes()[:16]
    except OSError:
        return ""
    if not header.startswith(b"SQLite format 3"):
        return ""
    try:
        with sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
            timeout=1.0,
            check_same_thread=False,
        ) as conn:
            rows = conn.execute(
                "SELECT dc_id, server_address, port, auth_key "
                "FROM sessions ORDER BY dc_id"
            ).fetchall()
    except sqlite3.Error:
        return ""
    if not rows:
        return ""
    digest = hashlib.sha256()
    auth_key_found = False
    for dc_id, server_address, port, auth_key in rows:
        auth_key_bytes = bytes(auth_key or b"")
        if auth_key_bytes:
            auth_key_found = True
        digest.update(str(dc_id).encode("utf-8", errors="replace"))
        digest.update(b"|")
        digest.update(str(server_address or "").encode("utf-8", errors="replace"))
        digest.update(b"|")
        digest.update(str(port or "").encode("utf-8", errors="replace"))
        digest.update(b"|")
        digest.update(auth_key_bytes)
        digest.update(b"\n")
    if not auth_key_found:
        return ""
    return digest.hexdigest()


def _local_session_lock(lock_key: str) -> threading.Lock:
    with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.get(lock_key)
        if lock is None:
            lock = threading.Lock()
            _SESSION_LOCKS[lock_key] = lock
        return lock


def _try_acquire_file_lock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError from exc
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise
    except OSError as exc:
        if exc.errno in {11, 13}:
            raise BlockingIOError from exc
        raise


def _release_file_lock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            return
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        return


class SessionUsageLock:
    def __init__(self, session_path: str | Path) -> None:
        self.session_path = Path(session_path).expanduser()
        self.lock_key = _session_lock_key(self.session_path)
        self.lock_path = _session_lock_path(self.session_path)
        self._local_lock = _local_session_lock(self.lock_key)
        self._local_lock_acquired = False
        self._handle = None

    def try_acquire(self) -> bool:
        acquired = self._local_lock.acquire(blocking=False)
        if not acquired:
            return False
        self._local_lock_acquired = True
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            _try_acquire_file_lock(handle)
        except BlockingIOError:
            handle.close()
            self._release_local_lock()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        try:
            if handle is not None:
                _release_file_lock(handle)
                handle.close()
        finally:
            self._release_local_lock()

    def _release_local_lock(self) -> None:
        if self._local_lock_acquired:
            self._local_lock.release()
            self._local_lock_acquired = False


class LockedTelegramClient:
    def __init__(self, client: Any, *, session_path: str | Path) -> None:
        self._client = client
        self._lock = SessionUsageLock(session_path)
        self._lock_acquired = False
        self._lock_timeout_seconds = _session_lock_timeout_seconds()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    async def __call__(self, *args, **kwargs):
        return await self._client(*args, **kwargs)

    async def connect(self):
        await self._ensure_lock()
        try:
            return await self._client.connect()
        except Exception:
            await self._release_lock()
            raise

    async def disconnect(self):
        try:
            return await self._client.disconnect()
        finally:
            await self._release_lock()

    async def __aenter__(self):
        await self._ensure_lock()
        try:
            if hasattr(self._client, "__aenter__"):
                await self._client.__aenter__()
            else:
                await self._client.connect()
        except Exception:
            await self._release_lock()
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if hasattr(self._client, "__aexit__"):
                return await self._client.__aexit__(exc_type, exc, tb)
            return await self._client.disconnect()
        finally:
            await self._release_lock()

    async def _ensure_lock(self) -> None:
        if self._lock_acquired:
            return
        deadline = time.monotonic() + self._lock_timeout_seconds
        while True:
            if self._lock.try_acquire():
                self._lock_acquired = True
                return
            if time.monotonic() >= deadline:
                raise TelegramSessionInUseError(
                    telegram_session_in_use_message(self._lock.session_path)
                )
            await asyncio.sleep(_SESSION_LOCK_RETRY_INTERVAL_SECONDS)

    async def _release_lock(self) -> None:
        if not self._lock_acquired:
            return
        try:
            self._lock.release()
        finally:
            self._lock_acquired = False


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
