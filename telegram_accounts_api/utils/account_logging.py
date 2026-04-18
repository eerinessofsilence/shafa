from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAX_LOG_ENTRIES_PER_ACCOUNT = 1000
_ACCOUNT_LOGGER_NAME = "telegram_accounts_api.account"
_HANDLER_NAME = "telegram_accounts_api.account_log_handler"
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(password|api_hash|token|sessionid|csrftoken|authorization|cookie)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
)
_RENDERED_LOG_PATTERN = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+\[(?P<level>[^\]]+)\](?:\s+\[(?P<account_name>[^\]]+)\])?\s+(?P<message>.*)$"
)


@dataclass(frozen=True)
class AccountLogEntry:
    index: int
    account_id: str
    timestamp: datetime
    level: str
    message: str


@dataclass(frozen=True)
class _Subscriber:
    id: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[AccountLogEntry]


class AccountLogStore:
    def __init__(self, max_entries_per_account: int = _MAX_LOG_ENTRIES_PER_ACCOUNT) -> None:
        self.max_entries_per_account = max(1, int(max_entries_per_account))
        self._entries: dict[str, deque[AccountLogEntry]] = defaultdict(
            lambda: deque(maxlen=self.max_entries_per_account)
        )
        self._next_index: dict[str, int] = defaultdict(int)
        self._subscribers: dict[str, dict[str, _Subscriber]] = defaultdict(dict)
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._next_index.clear()
            self._subscribers.clear()

    def append(
        self,
        account_id: str | int,
        level: str,
        message: str,
        *,
        timestamp: datetime | None = None,
    ) -> AccountLogEntry:
        normalized_account_id = str(account_id)
        entry = AccountLogEntry(
            index=self._next_index[normalized_account_id],
            account_id=normalized_account_id,
            timestamp=normalize_log_timestamp(timestamp or datetime.now(UTC)),
            level=str(level or "INFO").upper(),
            message=sanitize_log_message(message),
        )
        with self._lock:
            self._entries[normalized_account_id].append(entry)
            self._next_index[normalized_account_id] += 1
            subscribers = list(self._subscribers.get(normalized_account_id, {}).values())
        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(subscriber.queue.put_nowait, entry)
            except RuntimeError:
                self.unsubscribe(normalized_account_id, subscriber.id)
        return entry

    def list_entries(
        self,
        account_id: str | int,
        *,
        limit: int = 100,
        level: str | None = None,
        since_index: int | None = None,
        since_timestamp: datetime | None = None,
    ) -> list[AccountLogEntry]:
        normalized_account_id = str(account_id)
        target_level = str(level or "").upper()
        normalized_timestamp = since_timestamp.astimezone(UTC) if since_timestamp else None
        with self._lock:
            entries = list(self._entries.get(normalized_account_id, ()))
        if target_level:
            entries = [entry for entry in entries if entry.level == target_level]
        if since_index is not None:
            entries = [entry for entry in entries if entry.index > since_index]
        if normalized_timestamp is not None:
            entries = [entry for entry in entries if entry.timestamp >= normalized_timestamp]
        bounded_limit = max(1, min(int(limit), self.max_entries_per_account))
        return entries[-bounded_limit:]

    def subscribe(self, account_id: str | int) -> tuple[str, asyncio.Queue[AccountLogEntry]]:
        normalized_account_id = str(account_id)
        subscription = _Subscriber(
            id=uuid.uuid4().hex,
            loop=asyncio.get_running_loop(),
            queue=asyncio.Queue(),
        )
        with self._lock:
            self._subscribers[normalized_account_id][subscription.id] = subscription
        return subscription.id, subscription.queue

    def unsubscribe(self, account_id: str | int, subscription_id: str) -> None:
        normalized_account_id = str(account_id)
        with self._lock:
            subscribers = self._subscribers.get(normalized_account_id)
            if not subscribers:
                return
            subscribers.pop(subscription_id, None)
            if not subscribers:
                self._subscribers.pop(normalized_account_id, None)


class AccountLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        account_id = getattr(record, "account_id", None)
        if account_id in (None, ""):
            return
        try:
            get_account_log_store().append(
                account_id=account_id,
                level=record.levelname,
                message=record.getMessage(),
                timestamp=datetime.fromtimestamp(record.created, tz=UTC),
            )
        except Exception:
            self.handleError(record)


_store_lock = threading.RLock()
_account_log_store: AccountLogStore | None = None


def get_account_log_store() -> AccountLogStore:
    global _account_log_store
    with _store_lock:
        if _account_log_store is None:
            _account_log_store = AccountLogStore()
        return _account_log_store


def set_account_log_store(store: AccountLogStore) -> AccountLogStore:
    global _account_log_store
    with _store_lock:
        _account_log_store = store
    return store


def install_account_log_handler() -> None:
    root_logger = logging.getLogger()
    if any(getattr(handler, "name", "") == _HANDLER_NAME for handler in root_logger.handlers):
        return
    handler = AccountLogHandler()
    handler.setLevel(logging.DEBUG)
    handler.name = _HANDLER_NAME
    root_logger.addHandler(handler)


def sanitize_log_message(message: str) -> str:
    sanitized = str(message)
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        if "Bearer" in pattern.pattern:
            sanitized = pattern.sub("Bearer [REDACTED]", sanitized)
        else:
            sanitized = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", sanitized)
    return sanitized


def normalize_log_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or UTC
        timestamp = timestamp.replace(tzinfo=local_tz)
    return timestamp.astimezone(UTC)


def load_account_log_file_entries(
    account_id: str | int,
    log_file: Path,
) -> list[AccountLogEntry]:
    if not log_file.exists() or not log_file.is_file():
        return []

    entries: list[AccountLogEntry] = []
    try:
        raw_lines = log_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    normalized_account_id = str(account_id)
    for raw_line in raw_lines:
        match = _RENDERED_LOG_PATTERN.match(raw_line.strip())
        if not match:
            continue
        try:
            timestamp = datetime.strptime(
                match.group("timestamp"),
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            continue
        entries.append(
            AccountLogEntry(
                index=0,
                account_id=normalized_account_id,
                timestamp=normalize_log_timestamp(timestamp),
                level=str(match.group("level") or "INFO").upper(),
                message=sanitize_log_message(match.group("message") or ""),
            )
        )
    start_index = -len(entries)
    return [
        AccountLogEntry(
            index=start_index + offset,
            account_id=entry.account_id,
            timestamp=entry.timestamp,
            level=entry.level,
            message=entry.message,
        )
        for offset, entry in enumerate(entries)
    ]


def merge_account_log_entries(*groups: list[AccountLogEntry]) -> list[AccountLogEntry]:
    merged_by_key: dict[tuple[str, str, str, str], AccountLogEntry] = {}

    for group in groups:
        for entry in group:
            dedupe_key = (
                entry.account_id,
                normalize_log_timestamp(entry.timestamp)
                .replace(microsecond=0)
                .isoformat(),
                entry.level,
                entry.message,
            )
            existing = merged_by_key.get(dedupe_key)
            if existing is None or entry.index > existing.index:
                merged_by_key[dedupe_key] = entry

    return sorted(
        merged_by_key.values(),
        key=lambda entry: (
            normalize_log_timestamp(entry.timestamp),
            entry.index,
            entry.message,
        ),
    )


def filter_account_log_entries(
    entries: list[AccountLogEntry],
    *,
    limit: int = 100,
    level: str | None = None,
    since_index: int | None = None,
    since_timestamp: datetime | None = None,
    max_entries: int = _MAX_LOG_ENTRIES_PER_ACCOUNT,
) -> list[AccountLogEntry]:
    target_level = str(level or "").upper()
    normalized_since_timestamp = (
        normalize_log_timestamp(since_timestamp)
        if since_timestamp is not None
        else None
    )
    bounded_limit = max(1, min(int(limit), int(max_entries)))

    filtered = entries
    if target_level:
        filtered = [entry for entry in filtered if entry.level == target_level]
    if since_index is not None:
        filtered = [entry for entry in filtered if entry.index > since_index]
    if normalized_since_timestamp is not None:
        filtered = [
            entry
            for entry in filtered
            if normalize_log_timestamp(entry.timestamp) >= normalized_since_timestamp
        ]
    return filtered[-bounded_limit:]


def log(account_id: str | int, level: str, message: str) -> None:
    install_account_log_handler()
    logger = logging.getLogger(_ACCOUNT_LOGGER_NAME)
    if logger.level in {logging.NOTSET, logging.WARNING, logging.ERROR, logging.CRITICAL}:
        logger.setLevel(logging.DEBUG)
    log_level = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    logger.log(
        log_level,
        sanitize_log_message(message),
        extra={"account_id": str(account_id)},
    )
