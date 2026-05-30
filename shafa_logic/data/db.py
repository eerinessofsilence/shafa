import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import re

from data.const import (
    ACCOUNT_ID,
    DB_PATH,
    MAX_PRODUCT_CREATE_ATTEMPTS,
    TELEGRAM_PRODUCTS_DB_PATH,
)
from data.size_mapping import normalize_size_text

_COOKIE_BASE_DOMAIN = "shafa.ua"
_DB_INITIALIZED_PATHS: set[Path] = set()
_CREATION_DB_INITIALIZED_PATHS: set[Path] = set()
_SIZE_ID_BY_NAME_CACHE: Optional[dict[str, int]] = None
_SIZE_ID_BY_NAME_CATALOG_CACHE: Optional[dict[tuple[str, str], int]] = None
_SIZE_IDS_CACHE: Optional[set[int]] = None
_SIZE_IDS_CATALOG_CACHE: Optional[dict[str, set[int]]] = None
_SIZE_MAPPING_ROWS_CACHE: Optional[dict[str, list[dict]]] = None
_BRAND_ID_BY_NAME_CACHE: Optional[dict[str, int]] = None
_BRAND_NAMES_CACHE: Optional[list[str]] = None
_DEFAULT_SQLITE_TIMEOUT_SECONDS = 60.0
_DEFAULT_SQLITE_LOCK_RETRIES = 3
_DEFAULT_SQLITE_LOCK_RETRY_DELAY_SECONDS = 0.25
_SQLITE_LOCK_ERROR_MARKERS = (
    "database is locked",
    "database schema is locked",
    "database table is locked",
    "database is busy",
)

TELEGRAM_PRODUCT_STATUS_QUEUED = "queued"
TELEGRAM_PRODUCT_STATUS_PROCESSING = "processing"
TELEGRAM_PRODUCT_STATUS_CREATED = "created"
TELEGRAM_PRODUCT_STATUS_FAILED = "failed"
TELEGRAM_PRODUCT_STATUS_SKIPPED = "skipped"
CREATION_PRODUCT_STATUS_NEW = "new"
CREATION_PRODUCT_STATUS_READY = "ready_to_upload"
CREATION_PRODUCT_STATUS_PROCESSING = "processing"
CREATION_PRODUCT_STATUS_CREATED = "created"
CREATION_PRODUCT_STATUS_FAILED = "failed"
CREATION_PRODUCT_STATUS_SKIPPED = "skipped"
CREATION_PRODUCT_STATUS_DUPLICATE = "duplicate"
TELEGRAM_DEACTIVATION_STATUS_PENDING = "pending"
TELEGRAM_DEACTIVATION_STATUS_PROCESSING = "processing"
TELEGRAM_DEACTIVATION_STATUS_COMPLETED = "completed"
TELEGRAM_DEACTIVATION_STATUS_FAILED = "failed"
TELEGRAM_DEACTIVATION_STATUS_SKIPPED_NOT_FOUND = "skipped_not_found"
TELEGRAM_DEACTIVATION_CHECK_FRESH = "fresh"
TELEGRAM_DEACTIVATION_CHECK_OLD = "old"
TELEGRAM_DEACTIVATION_CHECK_DATE_MISSING = "date_missing"
TELEGRAM_DEACTIVATION_CHECK_NEEDS_RETRY = "needs_retry"
SHARED_PRODUCT_CHECK_UNCHECKED = "unchecked"
SHARED_PRODUCT_CHECK_FRESH = "fresh"
SHARED_PRODUCT_CHECK_OLD = "old"
SHARED_PRODUCT_CHECK_DATE_MISSING = "date_missing"
SHARED_PRODUCT_CHECK_NEEDS_RETRY = "needs_retry"
SHARED_PRODUCT_DEACTIVATION_NONE = "none"
SHARED_PRODUCT_DEACTIVATION_QUEUED = "queued"
SHARED_PRODUCT_DEACTIVATION_PARTIAL = "partial"
SHARED_PRODUCT_DEACTIVATION_COMPLETED = "completed"
SHARED_PRODUCT_DEACTIVATION_FAILED = "failed"
SHARED_TASK_STATUS_PENDING = "pending"
SHARED_TASK_STATUS_PROCESSING = "processing"
SHARED_TASK_STATUS_PARTIAL = "partial"
SHARED_TASK_STATUS_COMPLETED = "completed"
SHARED_TASK_STATUS_FAILED = "failed"
SHARED_ACCOUNT_TASK_PENDING = "pending"
SHARED_ACCOUNT_TASK_PROCESSING = "processing"
SHARED_ACCOUNT_TASK_COMPLETED = "completed"
SHARED_ACCOUNT_TASK_FAILED = "failed"
SHARED_ACCOUNT_TASK_RETRY_SCHEDULED = "retry_scheduled"
SHARED_ACCOUNT_TASK_SKIPPED = "skipped"
SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND = "skipped_not_found"
SHARED_ACCOUNT_PRODUCT_ACTIVE = "active"
SHARED_ACCOUNT_PRODUCT_DEACTIVATED = "deactivated"
SHARED_ACCOUNT_PRODUCT_MISSING = "missing"
LEGACY_TELEGRAM_ACCOUNT_ID = "__legacy_unassigned__"
DEFAULT_ACCOUNT_PLACEHOLDER = "default"


def _sqlite_timeout_seconds() -> float:
    raw = os.getenv("SHAFA_DB_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_SQLITE_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_SQLITE_TIMEOUT_SECONDS
    return min(max(value, 1.0), 300.0)


def _sqlite_busy_timeout_ms() -> int:
    return int(_sqlite_timeout_seconds() * 1000)


def _sqlite_lock_retries() -> int:
    raw = os.getenv("SHAFA_DB_LOCK_RETRIES", "").strip()
    if not raw:
        return _DEFAULT_SQLITE_LOCK_RETRIES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_SQLITE_LOCK_RETRIES
    return min(max(value, 1), 10)


def _sqlite_lock_retry_delay_seconds() -> float:
    raw = os.getenv("SHAFA_DB_LOCK_RETRY_DELAY_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_SQLITE_LOCK_RETRY_DELAY_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_SQLITE_LOCK_RETRY_DELAY_SECONDS
    return min(max(value, 0.05), 5.0)


def _is_sqlite_lock_error(exc: sqlite3.Error) -> bool:
    message = " ".join(str(exc).split()).lower()
    return any(marker in message for marker in _SQLITE_LOCK_ERROR_MARKERS)


def _run_with_lock_retry(action, *, rollback=None):
    retries = _sqlite_lock_retries()
    for attempt in range(retries):
        try:
            return action()
        except sqlite3.OperationalError as exc:
            if not _is_sqlite_lock_error(exc):
                raise
            if rollback is not None:
                try:
                    rollback()
                except sqlite3.Error:
                    pass
            if attempt + 1 >= retries:
                raise
            time.sleep(_sqlite_lock_retry_delay_seconds() * (attempt + 1))


class _RetryingConnection(sqlite3.Connection):
    def execute(self, *args, **kwargs):
        return _run_with_lock_retry(
            lambda: sqlite3.Connection.execute(self, *args, **kwargs),
            rollback=lambda: sqlite3.Connection.rollback(self),
        )

    def executemany(self, *args, **kwargs):
        return _run_with_lock_retry(
            lambda: sqlite3.Connection.executemany(self, *args, **kwargs),
            rollback=lambda: sqlite3.Connection.rollback(self),
        )

    def executescript(self, *args, **kwargs):
        return _run_with_lock_retry(
            lambda: sqlite3.Connection.executescript(self, *args, **kwargs),
            rollback=lambda: sqlite3.Connection.rollback(self),
        )


def _normalize_telegram_channel_alias(alias: Optional[str]) -> str:
    raw = str(alias or "").strip()
    tokens = [token for token in re.split(r"\s+", raw) if token]
    if not tokens:
        tokens = ["main"]
    if "main" not in tokens:
        tokens.insert(0, "main")
    if "extra_photos" not in tokens:
        tokens.append("extra_photos")
    return " ".join(tokens)


def _current_account_id(account_id: Optional[str] = None) -> str:
    raw = str(account_id or os.getenv("SHAFA_ACCOUNT_ID") or ACCOUNT_ID).strip()
    return raw or "default"


def _create_telegram_products_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            raw_message TEXT,
            parsed_data TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            created INTEGER NOT NULL DEFAULT 0,
            created_product_id TEXT,
            telegram_message_date TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            status_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            create_attempts INTEGER NOT NULL DEFAULT 0,
            last_create_error TEXT,
            shafa_deactivated_at TEXT,
            shafa_deactivate_attempts INTEGER NOT NULL DEFAULT 0,
            last_shafa_deactivate_error TEXT,
            deactivation_status TEXT,
            deactivation_queued_at TEXT,
            deactivation_processing_started_at REAL,
            deactivation_processing_token TEXT,
            deactivation_processing_expires_at REAL,
            deactivation_retry_count INTEGER NOT NULL DEFAULT 0,
            deactivation_failed_at TEXT,
            deactivation_error TEXT,
            deactivation_completed_at TEXT,
            deactivation_check_status TEXT,
            deactivation_last_checked_at TEXT,
            deactivation_next_check_at TEXT,
            shafa_deleted_at TEXT,
            shafa_delete_attempts INTEGER NOT NULL DEFAULT 0,
            last_shafa_delete_error TEXT,
            UNIQUE(account_id, channel_id, message_id)
        )
        """
    )


def _create_creation_products_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS creation_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            telegram_product_key TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            telegram_message_date TEXT,
            product_title TEXT,
            raw_message TEXT,
            parsed_data TEXT,
            media_paths TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_product_id TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT,
            last_error TEXT,
            skip_reason TEXT,
            processing_started_at REAL,
            processing_token TEXT,
            processing_expires_at REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(account_id, telegram_product_key),
            UNIQUE(account_id, channel_id, message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_creation_products_account
            ON creation_products(account_id);
        CREATE INDEX IF NOT EXISTS idx_creation_products_key
            ON creation_products(telegram_product_key);
        CREATE INDEX IF NOT EXISTS idx_creation_products_channel_message
            ON creation_products(channel_id, message_id);
        CREATE INDEX IF NOT EXISTS idx_creation_products_status
            ON creation_products(status);
        CREATE INDEX IF NOT EXISTS idx_creation_products_created_product
            ON creation_products(created_product_id);
        CREATE INDEX IF NOT EXISTS idx_creation_products_updated
            ON creation_products(updated_at);
        CREATE INDEX IF NOT EXISTS idx_creation_products_ready
            ON creation_products(account_id, status, processing_expires_at, updated_at);
        """
    )


def _create_shared_deactivation_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS shared_telegram_products (
            telegram_product_key TEXT PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            telegram_message_date TEXT,
            product_title TEXT,
            checked_status TEXT NOT NULL DEFAULT 'unchecked',
            deactivation_status TEXT NOT NULL DEFAULT 'none',
            age_source TEXT,
            last_checked_at TEXT,
            next_check_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(channel_id, message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_shared_telegram_products_check
            ON shared_telegram_products(checked_status, next_check_at, last_checked_at);
        CREATE INDEX IF NOT EXISTS idx_shared_telegram_products_deactivation
            ON shared_telegram_products(deactivation_status);

        CREATE TABLE IF NOT EXISTS shared_telegram_product_accounts (
            telegram_product_key TEXT NOT NULL,
            account_id TEXT NOT NULL,
            shafa_product_id TEXT NOT NULL,
            product_title TEXT,
            account_product_status TEXT NOT NULL DEFAULT 'active',
            last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (telegram_product_key, account_id),
            FOREIGN KEY (telegram_product_key)
                REFERENCES shared_telegram_products(telegram_product_key)
        );
        CREATE INDEX IF NOT EXISTS idx_shared_product_accounts_account
            ON shared_telegram_product_accounts(account_id, account_product_status);

        CREATE TABLE IF NOT EXISTS shared_deactivation_tasks (
            task_id TEXT PRIMARY KEY,
            telegram_product_key TEXT NOT NULL,
            telegram_message_date TEXT,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(telegram_product_key),
            FOREIGN KEY (telegram_product_key)
                REFERENCES shared_telegram_products(telegram_product_key)
        );
        CREATE INDEX IF NOT EXISTS idx_shared_deactivation_tasks_status
            ON shared_deactivation_tasks(status, updated_at);

        CREATE TABLE IF NOT EXISTS shared_deactivation_task_accounts (
            task_id TEXT NOT NULL,
            telegram_product_key TEXT NOT NULL,
            account_id TEXT NOT NULL,
            shafa_product_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            processing_token TEXT,
            processing_started_at REAL,
            processing_expires_at REAL,
            next_retry_at REAL,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (task_id, account_id),
            FOREIGN KEY (task_id) REFERENCES shared_deactivation_tasks(task_id),
            FOREIGN KEY (telegram_product_key)
                REFERENCES shared_telegram_products(telegram_product_key)
        );
        CREATE INDEX IF NOT EXISTS idx_shared_task_accounts_claim
            ON shared_deactivation_task_accounts(
                account_id,
                status,
                next_retry_at,
                processing_expires_at
            );
        CREATE INDEX IF NOT EXISTS idx_shared_task_accounts_parent
            ON shared_deactivation_task_accounts(task_id, status);
        """
    )


def _create_telegram_scan_cursors_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_scan_cursors (
            account_id TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            last_checked_message_id INTEGER,
            backfill_before_message_id INTEGER,
            backfill_history_limit_reached INTEGER NOT NULL DEFAULT 0,
            backfill_history_window_days INTEGER,
            backfill_history_limit_reached_at TEXT,
            last_scan_started_at TEXT,
            last_scan_finished_at TEXT,
            last_scan_error TEXT,
            backfill_scan_started_at TEXT,
            backfill_scan_finished_at TEXT,
            backfill_scan_error TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY(account_id, channel_id)
        )
        """
    )


def _create_invalid_uploaded_products_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS invalid_uploaded_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            name TEXT,
            invalid_reason TEXT NOT NULL,
            raw_payload TEXT,
            created_at TEXT,
            detected_at TEXT NOT NULL DEFAULT (datetime('now')),
            processed INTEGER NOT NULL DEFAULT 0,
            processed_at TEXT,
            last_error TEXT,
            UNIQUE(product_id)
        )
        """
    )


def _account_db_path() -> Path:
    configured = os.getenv("SHAFA_DB_PATH", "").strip()
    return Path(configured) if configured else Path(DB_PATH)


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    resolved_db_path = Path(db_path) if db_path is not None else _account_db_path()
    conn = sqlite3.connect(
        resolved_db_path,
        timeout=_sqlite_timeout_seconds(),
        factory=_RetryingConnection,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {_sqlite_busy_timeout_ms()}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    global _DB_INITIALIZED_PATHS
    db_path = Path(db_path) if db_path is not None else _account_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS uploaded_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                name TEXT,
                brand INTEGER,
                size INTEGER,
                price INTEGER,
                photo_ids TEXT,
                raw_payload TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_uploaded_products_product_id
                ON uploaded_products(product_id);
            CREATE TABLE IF NOT EXISTS invalid_uploaded_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                name TEXT,
                invalid_reason TEXT NOT NULL,
                raw_payload TEXT,
                created_at TEXT,
                detected_at TEXT NOT NULL DEFAULT (datetime('now')),
                processed INTEGER NOT NULL DEFAULT 0,
                processed_at TEXT,
                last_error TEXT,
                UNIQUE(product_id)
            );
            CREATE INDEX IF NOT EXISTS idx_invalid_uploaded_products_pending
                ON invalid_uploaded_products(processed, detected_at DESC);

            CREATE TABLE IF NOT EXISTS telegram_fetch_state (
                scope TEXT PRIMARY KEY,
                last_fetch_at REAL,
                lease_expires_at REAL,
                lease_token TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_telegram_fetch_state_updated
                ON telegram_fetch_state(updated_at);

            CREATE TABLE IF NOT EXISTS size_catalogs (
                catalog_slug TEXT NOT NULL,
                size_id INTEGER NOT NULL,
                primary_size_name TEXT NOT NULL,
                size_system TEXT,
                PRIMARY KEY (catalog_slug, size_id)
            );
            CREATE INDEX IF NOT EXISTS idx_size_catalogs_name
                ON size_catalogs(catalog_slug, primary_size_name);

            CREATE TABLE IF NOT EXISTS size_catalog_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_slug TEXT NOT NULL,
                id_v3 INTEGER,
                international TEXT,
                eu TEXT,
                ua TEXT,
                id_v5_international INTEGER,
                id_v5_eu INTEGER,
                id_v5_ua INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_size_catalog_mappings_catalog
                ON size_catalog_mappings(catalog_slug);
            CREATE INDEX IF NOT EXISTS idx_size_catalog_mappings_international
                ON size_catalog_mappings(catalog_slug, international);
            CREATE INDEX IF NOT EXISTS idx_size_catalog_mappings_eu
                ON size_catalog_mappings(catalog_slug, eu);
            CREATE INDEX IF NOT EXISTS idx_size_catalog_mappings_ua
                ON size_catalog_mappings(catalog_slug, ua);

            CREATE TABLE IF NOT EXISTS brands (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cookies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                name TEXT NOT NULL,
                value TEXT NOT NULL,
                path TEXT NOT NULL DEFAULT '/',
                expires REAL,
                http_only INTEGER NOT NULL DEFAULT 0,
                secure INTEGER NOT NULL DEFAULT 0,
                same_site TEXT,
                last_updated TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(domain, name, path)
            );
            CREATE INDEX IF NOT EXISTS idx_cookies_domain
                ON cookies(domain);
            """
        )
        _ensure_schema_migrations_table(conn)
        _create_telegram_products_table(conn)
        if db_path == _telegram_products_db_path():
            _create_shared_deactivation_tables(conn)
        _create_telegram_scan_cursors_table(conn)
        _create_invalid_uploaded_products_table(conn)
        _ensure_uploaded_products_schema(conn)
        _ensure_invalid_uploaded_products_schema(conn)
        _ensure_telegram_products_schema(conn)
        _ensure_telegram_fetch_state_schema(conn)
        _ensure_telegram_scan_cursors_schema(conn)
        _drop_legacy_telegram_channels_table(conn)
        _ensure_size_catalogs_schema(conn)
    _DB_INITIALIZED_PATHS.add(db_path)


def _ensure_db_initialized(db_path: Optional[Path] = None) -> None:
    db_path = Path(db_path) if db_path is not None else _account_db_path()
    if db_path in _DB_INITIALIZED_PATHS:
        return
    init_db(db_path)


def _telegram_products_db_path() -> Path:
    configured = os.getenv("SHAFA_SHARED_TELEGRAM_DB_PATH", "").strip()
    return Path(configured) if configured else Path(TELEGRAM_PRODUCTS_DB_PATH)


def creation_products_enabled() -> bool:
    return bool(os.getenv("SHAFA_CREATION_PRODUCTS_DB_PATH", "").strip())


def creation_products_db_path() -> Optional[Path]:
    configured = os.getenv("SHAFA_CREATION_PRODUCTS_DB_PATH", "").strip()
    return Path(configured) if configured else None


def _creation_products_db_path() -> Path:
    configured = creation_products_db_path()
    if configured is None:
        raise RuntimeError("SHAFA_CREATION_PRODUCTS_DB_PATH is not configured")
    return configured


def _ensure_creation_db_initialized(db_path: Optional[Path] = None) -> None:
    resolved_db_path = Path(db_path) if db_path is not None else _creation_products_db_path()
    if resolved_db_path in _CREATION_DB_INITIALIZED_PATHS:
        return
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(resolved_db_path) as conn:
        _create_creation_products_table(conn)
    _CREATION_DB_INITIALIZED_PATHS.add(resolved_db_path)


def _normalize_catalog_slug(catalog_slug: Optional[str]) -> Optional[str]:
    if catalog_slug is None:
        return None
    text = str(catalog_slug).strip()
    if not text:
        return None
    return text.casefold()


def _normalize_datetime_text(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(
            tzinfo=timezone.utc
        )
        return normalized.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    else:
        normalized = normalized.astimezone(timezone.utc)
    return normalized.strftime("%Y-%m-%d %H:%M:%S")


def _load_sizes_cache() -> tuple[
    dict[str, int],
    dict[tuple[str, str], int],
    set[int],
    dict[str, set[int]],
]:
    global _SIZE_ID_BY_NAME_CACHE, _SIZE_ID_BY_NAME_CATALOG_CACHE
    global _SIZE_IDS_CACHE, _SIZE_IDS_CATALOG_CACHE
    if (
        _SIZE_ID_BY_NAME_CACHE is not None
        and _SIZE_ID_BY_NAME_CATALOG_CACHE is not None
        and _SIZE_IDS_CACHE is not None
        and _SIZE_IDS_CATALOG_CACHE is not None
    ):
        return (
            _SIZE_ID_BY_NAME_CACHE,
            _SIZE_ID_BY_NAME_CATALOG_CACHE,
            _SIZE_IDS_CACHE,
            _SIZE_IDS_CATALOG_CACHE,
        )
    _ensure_db_initialized()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT catalog_slug, size_id, primary_size_name
            FROM size_catalogs
            """
        ).fetchall()
    mapping: dict[str, int] = {}
    mapping_by_catalog: dict[tuple[str, str], int] = {}
    ids: set[int] = set()
    ids_by_catalog: dict[str, set[int]] = {}
    for row in rows:
        size_id = row["size_id"]
        if size_id is None:
            continue
        size_id_int = int(size_id)
        ids.add(size_id_int)
        name = row["primary_size_name"]
        if not name:
            continue
        normalized_name = normalize_size_text(name)
        if not normalized_name:
            continue
        key = normalized_name.casefold()
        if not key:
            continue
        current = mapping.get(key)
        if current is None or size_id_int > current:
            mapping[key] = size_id_int
        catalog_slug = _normalize_catalog_slug(row["catalog_slug"])
        if not catalog_slug:
            continue
        catalog_key = (catalog_slug, key)
        current_catalog = mapping_by_catalog.get(catalog_key)
        if current_catalog is None or size_id_int > current_catalog:
            mapping_by_catalog[catalog_key] = size_id_int
        ids_by_catalog.setdefault(catalog_slug, set()).add(size_id_int)
    _SIZE_ID_BY_NAME_CACHE = mapping
    _SIZE_ID_BY_NAME_CATALOG_CACHE = mapping_by_catalog
    _SIZE_IDS_CACHE = ids
    _SIZE_IDS_CATALOG_CACHE = ids_by_catalog
    return mapping, mapping_by_catalog, ids, ids_by_catalog


def _load_size_mapping_rows_cache() -> dict[str, list[dict]]:
    global _SIZE_MAPPING_ROWS_CACHE
    if _SIZE_MAPPING_ROWS_CACHE is not None:
        return _SIZE_MAPPING_ROWS_CACHE
    _ensure_db_initialized()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                catalog_slug,
                id_v3,
                international,
                eu,
                ua,
                id_v5_international,
                id_v5_eu,
                id_v5_ua
            FROM size_catalog_mappings
            """
        ).fetchall()
    cache: dict[str, list[dict]] = {}
    for row in rows:
        catalog_slug = _normalize_catalog_slug(row["catalog_slug"])
        if not catalog_slug:
            continue
        cache.setdefault(catalog_slug, []).append(
            {
                "catalog_slug": catalog_slug,
                "id_v3": row["id_v3"],
                "international": normalize_size_text(row["international"]),
                "eu": normalize_size_text(row["eu"]),
                "ua": normalize_size_text(row["ua"]),
                "id_v5_international": row["id_v5_international"],
                "id_v5_eu": row["id_v5_eu"],
                "id_v5_ua": row["id_v5_ua"],
            }
        )
    _SIZE_MAPPING_ROWS_CACHE = cache
    return cache


def _load_brands_cache() -> tuple[dict[str, int], list[str]]:
    global _BRAND_ID_BY_NAME_CACHE, _BRAND_NAMES_CACHE
    if _BRAND_ID_BY_NAME_CACHE is not None and _BRAND_NAMES_CACHE is not None:
        return _BRAND_ID_BY_NAME_CACHE, _BRAND_NAMES_CACHE
    _ensure_db_initialized()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name
            FROM brands
            WHERE name IS NOT NULL AND TRIM(name) != ''
            """
        ).fetchall()
    mapping: dict[str, int] = {}
    names: list[str] = []
    for row in rows:
        brand_id = row["id"]
        name = row["name"]
        if brand_id is None or not name:
            continue
        names.append(name)
        key = str(name).strip().casefold()
        if key and key not in mapping:
            mapping[key] = int(brand_id)
    names = sorted(names)
    _BRAND_ID_BY_NAME_CACHE = mapping
    _BRAND_NAMES_CACHE = names
    return mapping, names


def _ensure_uploaded_products_schema(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        "uploaded_products",
        "is_active",
        "INTEGER NOT NULL DEFAULT 1",
    )
    _add_column_if_missing(conn, "uploaded_products", "shafa_created_at", "TEXT")
    _add_column_if_missing(conn, "uploaded_products", "status_title", "TEXT")


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in columns:
        return
    try:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )
    except sqlite3.OperationalError as exc:
        message = str(exc).casefold()
        if "duplicate column name" not in message:
            raise
        columns = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            raise


def _ensure_invalid_uploaded_products_schema(conn: sqlite3.Connection) -> None:
    _create_invalid_uploaded_products_table(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_invalid_uploaded_products_pending "
        "ON invalid_uploaded_products(processed, detected_at DESC)"
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _backup_table_once(
    conn: sqlite3.Connection,
    source_table: str,
    backup_table: str,
) -> bool:
    if not _table_exists(conn, source_table) or _table_exists(conn, backup_table):
        return False
    conn.execute(
        f'CREATE TABLE "{backup_table}" AS SELECT * FROM "{source_table}"'
    )
    return True


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')),
            details_json TEXT
        )
        """
    )


def _record_schema_migration(
    conn: sqlite3.Connection,
    name: str,
    *,
    details: Optional[dict] = None,
) -> None:
    _ensure_schema_migrations_table(conn)
    payload = json.dumps(details, ensure_ascii=True) if details is not None else None
    conn.execute(
        """
        INSERT INTO schema_migrations (name, applied_at, details_json)
        VALUES (?, datetime('now'), ?)
        ON CONFLICT(name) DO UPDATE SET
            applied_at = datetime('now'),
            details_json = excluded.details_json
        """,
        (name, payload),
    )


def _telegram_products_requires_rebuild(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='telegram_products'"
    ).fetchone()
    if row is None:
        return False
    columns = {
        item["name"]
        for item in conn.execute("PRAGMA table_info(telegram_products)").fetchall()
    }
    if "account_id" not in columns:
        return True
    create_sql = " ".join(str(row["sql"] or "").split())
    return "UNIQUE(account_id, channel_id, message_id)" not in create_sql


def _rebuild_telegram_products_table(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(telegram_products)").fetchall()
    }
    if not columns:
        _create_telegram_products_table(conn)
        return

    _backup_table_once(conn, "telegram_products", "telegram_products_legacy_backup")
    account_id_expr = "account_id" if "account_id" in columns else "?"
    id_expr = "id" if "id" in columns else "NULL"
    created_expr = "COALESCE(created, 0)" if "created" in columns else "0"
    created_product_id_expr = (
        "created_product_id" if "created_product_id" in columns else "NULL"
    )
    create_attempts_expr = (
        "COALESCE(create_attempts, 0)" if "create_attempts" in columns else "0"
    )
    telegram_message_date_expr = (
        "telegram_message_date" if "telegram_message_date" in columns else "NULL"
    )
    created_at_source = "created_at" if "created_at" in columns else "NULL"
    updated_at_source = "updated_at" if "updated_at" in columns else "NULL"
    status_updated_at_source = (
        "status_updated_at" if "status_updated_at" in columns else "NULL"
    )
    last_create_error_expr = (
        "last_create_error" if "last_create_error" in columns else "NULL"
    )
    shafa_deleted_at_expr = (
        "shafa_deleted_at" if "shafa_deleted_at" in columns else "NULL"
    )
    shafa_deactivated_at_expr = (
        "shafa_deactivated_at" if "shafa_deactivated_at" in columns else "NULL"
    )
    shafa_delete_attempts_expr = (
        "COALESCE(shafa_delete_attempts, 0)"
        if "shafa_delete_attempts" in columns
        else "0"
    )
    shafa_deactivate_attempts_expr = (
        "COALESCE(shafa_deactivate_attempts, 0)"
        if "shafa_deactivate_attempts" in columns
        else "0"
    )
    last_shafa_delete_error_expr = (
        "last_shafa_delete_error" if "last_shafa_delete_error" in columns else "NULL"
    )
    last_shafa_deactivate_error_expr = (
        "last_shafa_deactivate_error"
        if "last_shafa_deactivate_error" in columns
        else "NULL"
    )
    deactivation_status_expr = (
        "deactivation_status" if "deactivation_status" in columns else "NULL"
    )
    deactivation_queued_at_expr = (
        "deactivation_queued_at" if "deactivation_queued_at" in columns else "NULL"
    )
    deactivation_processing_started_at_expr = (
        "deactivation_processing_started_at"
        if "deactivation_processing_started_at" in columns
        else "NULL"
    )
    deactivation_processing_token_expr = (
        "deactivation_processing_token"
        if "deactivation_processing_token" in columns
        else "NULL"
    )
    deactivation_processing_expires_at_expr = (
        "deactivation_processing_expires_at"
        if "deactivation_processing_expires_at" in columns
        else "NULL"
    )
    deactivation_retry_count_expr = (
        "COALESCE(deactivation_retry_count, 0)"
        if "deactivation_retry_count" in columns
        else "0"
    )
    deactivation_failed_at_expr = (
        "deactivation_failed_at" if "deactivation_failed_at" in columns else "NULL"
    )
    deactivation_error_expr = (
        "deactivation_error" if "deactivation_error" in columns else "NULL"
    )
    deactivation_completed_at_expr = (
        "deactivation_completed_at" if "deactivation_completed_at" in columns else "NULL"
    )
    conn.execute("ALTER TABLE telegram_products RENAME TO telegram_products_legacy")
    _create_telegram_products_table(conn)
    conn.execute(
        f"""
        INSERT INTO telegram_products (
            id,
            account_id,
            channel_id,
            message_id,
            raw_message,
            parsed_data,
            status,
            created,
            created_product_id,
            telegram_message_date,
            created_at,
            updated_at,
            status_updated_at,
            create_attempts,
            last_create_error,
            shafa_deactivated_at,
            shafa_deactivate_attempts,
            last_shafa_deactivate_error,
            deactivation_status,
            deactivation_queued_at,
            deactivation_processing_started_at,
            deactivation_processing_token,
            deactivation_processing_expires_at,
            deactivation_retry_count,
            deactivation_failed_at,
            deactivation_error,
            deactivation_completed_at,
            shafa_deleted_at,
            shafa_delete_attempts,
            last_shafa_delete_error
        )
        SELECT
            {id_expr},
            {account_id_expr},
            channel_id,
            message_id,
            raw_message,
            parsed_data,
            CASE
                WHEN {created_expr} != 0
                    THEN CASE
                        WHEN COALESCE({created_product_id_expr}, '') LIKE 'SKIPPED_%'
                            THEN ?
                        ELSE ?
                    END
                WHEN {create_attempts_expr} > 0
                    THEN ?
                ELSE ?
            END,
            {created_expr},
            {created_product_id_expr},
            {telegram_message_date_expr},
            COALESCE({created_at_source}, datetime('now')),
            COALESCE({updated_at_source}, {created_at_source}, datetime('now')),
            COALESCE(
                {status_updated_at_source},
                {updated_at_source},
                {created_at_source},
                datetime('now')
            ),
            {create_attempts_expr},
            {last_create_error_expr},
            {shafa_deactivated_at_expr},
            {shafa_deactivate_attempts_expr},
            {last_shafa_deactivate_error_expr},
            {deactivation_status_expr},
            {deactivation_queued_at_expr},
            {deactivation_processing_started_at_expr},
            {deactivation_processing_token_expr},
            {deactivation_processing_expires_at_expr},
            {deactivation_retry_count_expr},
            {deactivation_failed_at_expr},
            {deactivation_error_expr},
            {deactivation_completed_at_expr},
            {shafa_deleted_at_expr},
            {shafa_delete_attempts_expr},
            {last_shafa_delete_error_expr}
        FROM telegram_products_legacy
        """,
        (
            *((LEGACY_TELEGRAM_ACCOUNT_ID,) if "account_id" not in columns else ()),
            TELEGRAM_PRODUCT_STATUS_SKIPPED,
            TELEGRAM_PRODUCT_STATUS_CREATED,
            TELEGRAM_PRODUCT_STATUS_FAILED,
            TELEGRAM_PRODUCT_STATUS_QUEUED,
        ),
    )
    conn.execute("DROP TABLE telegram_products_legacy")
    _record_schema_migration(
        conn,
        "telegram_products_account_scope_v2",
        details={"legacy_account_id": LEGACY_TELEGRAM_ACCOUNT_ID},
    )


def _hide_placeholder_telegram_product_accounts(conn: sqlite3.Connection) -> None:
    current_account_id = _current_account_id()
    if current_account_id == DEFAULT_ACCOUNT_PLACEHOLDER:
        return
    cursor = conn.execute(
        """
        UPDATE telegram_products
        SET account_id = ?
        WHERE account_id = ?
        """,
        (LEGACY_TELEGRAM_ACCOUNT_ID, DEFAULT_ACCOUNT_PLACEHOLDER),
    )
    if cursor.rowcount:
        _record_schema_migration(
            conn,
            "telegram_products_default_placeholder_hidden",
            details={"migrated_rows": cursor.rowcount},
        )


def _ensure_telegram_products_schema(conn: sqlite3.Connection) -> None:
    if _telegram_products_requires_rebuild(conn):
        _rebuild_telegram_products_table(conn)
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(telegram_products)").fetchall()
    }
    if "account_id" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN account_id TEXT NOT NULL DEFAULT 'default'"
        )
    if "create_attempts" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN create_attempts "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "last_create_error" not in columns:
        conn.execute("ALTER TABLE telegram_products ADD COLUMN last_create_error TEXT")
    if "telegram_message_date" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN telegram_message_date TEXT"
        )
    if "status" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'"
        )
        conn.execute(
            f"""
            UPDATE telegram_products
            SET status = CASE
                WHEN COALESCE(created, 0) != 0
                    THEN CASE
                        WHEN COALESCE(created_product_id, '') LIKE 'SKIPPED_%'
                            THEN '{TELEGRAM_PRODUCT_STATUS_SKIPPED}'
                        ELSE '{TELEGRAM_PRODUCT_STATUS_CREATED}'
                    END
                WHEN COALESCE(create_attempts, 0) > 0
                    THEN '{TELEGRAM_PRODUCT_STATUS_FAILED}'
                ELSE '{TELEGRAM_PRODUCT_STATUS_QUEUED}'
            END
            """
        )
    if "status_updated_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN status_updated_at TEXT"
        )
        conn.execute(
            """
            UPDATE telegram_products
            SET status_updated_at = COALESCE(updated_at, created_at, datetime('now'))
            WHERE status_updated_at IS NULL
            """
        )
    if "shafa_deactivated_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN shafa_deactivated_at TEXT"
        )
    if "shafa_deactivate_attempts" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN shafa_deactivate_attempts "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "last_shafa_deactivate_error" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN last_shafa_deactivate_error TEXT"
        )
    if "deactivation_status" not in columns:
        conn.execute("ALTER TABLE telegram_products ADD COLUMN deactivation_status TEXT")
    if "deactivation_queued_at" not in columns:
        conn.execute("ALTER TABLE telegram_products ADD COLUMN deactivation_queued_at TEXT")
    if "deactivation_processing_started_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN "
            "deactivation_processing_started_at REAL"
        )
    if "deactivation_processing_token" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN deactivation_processing_token TEXT"
        )
    if "deactivation_processing_expires_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN "
            "deactivation_processing_expires_at REAL"
        )
    if "deactivation_retry_count" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN deactivation_retry_count "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "deactivation_failed_at" not in columns:
        conn.execute("ALTER TABLE telegram_products ADD COLUMN deactivation_failed_at TEXT")
    if "deactivation_error" not in columns:
        conn.execute("ALTER TABLE telegram_products ADD COLUMN deactivation_error TEXT")
    if "deactivation_completed_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN deactivation_completed_at TEXT"
        )
    if "deactivation_check_status" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN deactivation_check_status TEXT"
        )
    if "deactivation_last_checked_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN deactivation_last_checked_at TEXT"
        )
    if "deactivation_next_check_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN deactivation_next_check_at TEXT"
        )
    conn.execute(
        f"""
        UPDATE telegram_products
        SET deactivation_status = ?,
            deactivation_completed_at = COALESCE(
                deactivation_completed_at,
                shafa_deactivated_at
            )
        WHERE shafa_deactivated_at IS NOT NULL
          AND (
                deactivation_status IS NULL
                OR deactivation_status != ?
          )
        """,
        (
            TELEGRAM_DEACTIVATION_STATUS_COMPLETED,
            TELEGRAM_DEACTIVATION_STATUS_COMPLETED,
        ),
    )
    if "shafa_deleted_at" not in columns:
        conn.execute("ALTER TABLE telegram_products ADD COLUMN shafa_deleted_at TEXT")
    if "shafa_delete_attempts" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN shafa_delete_attempts "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "last_shafa_delete_error" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN last_shafa_delete_error TEXT"
        )
    conn.execute(
        f"UPDATE telegram_products SET account_id = '{LEGACY_TELEGRAM_ACCOUNT_ID}' "
        "WHERE account_id IS NULL OR TRIM(account_id) = ''"
    )
    _hide_placeholder_telegram_product_accounts(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_account_created "
        "ON telegram_products(account_id, created)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_account_channel "
        "ON telegram_products(account_id, channel_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_account_status "
        "ON telegram_products(account_id, status, created_at DESC, message_id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_account_created_at "
        "ON telegram_products(account_id, created_at DESC, message_id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_account_message_date "
        "ON telegram_products(account_id, telegram_message_date, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_account_deactivated_at "
        "ON telegram_products(account_id, shafa_deactivated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_status "
        "ON telegram_products(account_id, deactivation_status, deactivation_queued_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_lease "
        "ON telegram_products(account_id, deactivation_status, "
        "deactivation_processing_expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_poll "
        "ON telegram_products(account_id, deactivation_status, telegram_message_date, "
        "message_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_products_deactivation_next_check "
        "ON telegram_products(account_id, deactivation_next_check_at, "
        "deactivation_check_status)"
    )


def _ensure_telegram_fetch_state_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_fetch_state (
            scope TEXT PRIMARY KEY,
            last_fetch_at REAL,
            lease_expires_at REAL,
            lease_token TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_fetch_state_updated "
        "ON telegram_fetch_state(updated_at)"
    )
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(telegram_fetch_state)").fetchall()
    }
    if "last_fetch_at" not in columns:
        conn.execute("ALTER TABLE telegram_fetch_state ADD COLUMN last_fetch_at REAL")
    if "lease_expires_at" not in columns:
        conn.execute("ALTER TABLE telegram_fetch_state ADD COLUMN lease_expires_at REAL")
    if "lease_token" not in columns:
        conn.execute("ALTER TABLE telegram_fetch_state ADD COLUMN lease_token TEXT")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE telegram_fetch_state ADD COLUMN updated_at TEXT")
        conn.execute(
            "UPDATE telegram_fetch_state SET updated_at = datetime('now') "
            "WHERE updated_at IS NULL"
        )
    _archive_legacy_fetch_state_rows(conn)


def _is_account_scoped_fetch_scope(scope: object) -> bool:
    text = str(scope or "").strip()
    return text.startswith("telegram_feed:") and text.count(":") >= 2


def _archive_legacy_fetch_state_rows(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_fetch_state_legacy (
            scope TEXT PRIMARY KEY,
            last_fetch_at REAL,
            lease_expires_at REAL,
            lease_token TEXT,
            updated_at TEXT,
            archived_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    rows = conn.execute(
        """
        SELECT scope, last_fetch_at, lease_expires_at, lease_token, updated_at
        FROM telegram_fetch_state
        """
    ).fetchall()
    legacy_rows = [row for row in rows if not _is_account_scoped_fetch_scope(row["scope"])]
    if not legacy_rows:
        return
    conn.executemany(
        """
        INSERT INTO telegram_fetch_state_legacy (
            scope,
            last_fetch_at,
            lease_expires_at,
            lease_token,
            updated_at,
            archived_at
        )
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(scope) DO UPDATE SET
            last_fetch_at = excluded.last_fetch_at,
            lease_expires_at = excluded.lease_expires_at,
            lease_token = excluded.lease_token,
            updated_at = excluded.updated_at,
            archived_at = datetime('now')
        """,
        [
            (
                row["scope"],
                row["last_fetch_at"],
                row["lease_expires_at"],
                row["lease_token"],
                row["updated_at"],
            )
            for row in legacy_rows
        ],
    )
    conn.executemany(
        "DELETE FROM telegram_fetch_state WHERE scope = ?",
        [(row["scope"],) for row in legacy_rows],
    )
    _record_schema_migration(
        conn,
        "telegram_fetch_state_legacy_archive_v1",
        details={"archived_rows": len(legacy_rows)},
    )


def _telegram_scan_cursors_requires_rebuild(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='telegram_scan_cursors'"
    ).fetchone()
    if row is None:
        return False
    columns = {
        item["name"]
        for item in conn.execute("PRAGMA table_info(telegram_scan_cursors)").fetchall()
    }
    if "account_id" not in columns:
        return True
    create_sql = " ".join(str(row["sql"] or "").split())
    return "PRIMARY KEY(account_id, channel_id)" not in create_sql


def _rebuild_telegram_scan_cursors_table(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(telegram_scan_cursors)").fetchall()
    }
    if not columns:
        _create_telegram_scan_cursors_table(conn)
        return

    _backup_table_once(
        conn,
        "telegram_scan_cursors",
        "telegram_scan_cursors_legacy_backup",
    )
    account_id_expr = "account_id" if "account_id" in columns else "?"
    channel_id_expr = "channel_id" if "channel_id" in columns else "NULL"
    last_checked_expr = (
        "last_checked_message_id" if "last_checked_message_id" in columns else "NULL"
    )
    backfill_before_expr = (
        "backfill_before_message_id"
        if "backfill_before_message_id" in columns
        else "NULL"
    )
    backfill_history_limit_reached_expr = (
        "backfill_history_limit_reached"
        if "backfill_history_limit_reached" in columns
        else "0"
    )
    backfill_history_window_days_expr = (
        "backfill_history_window_days"
        if "backfill_history_window_days" in columns
        else "NULL"
    )
    backfill_history_limit_reached_at_expr = (
        "backfill_history_limit_reached_at"
        if "backfill_history_limit_reached_at" in columns
        else "NULL"
    )
    last_started_expr = (
        "last_scan_started_at" if "last_scan_started_at" in columns else "NULL"
    )
    last_finished_expr = (
        "last_scan_finished_at" if "last_scan_finished_at" in columns else "NULL"
    )
    last_error_expr = "last_scan_error" if "last_scan_error" in columns else "NULL"
    backfill_started_expr = (
        "backfill_scan_started_at" if "backfill_scan_started_at" in columns else "NULL"
    )
    backfill_finished_expr = (
        "backfill_scan_finished_at" if "backfill_scan_finished_at" in columns else "NULL"
    )
    backfill_error_expr = (
        "backfill_scan_error" if "backfill_scan_error" in columns else "NULL"
    )
    updated_at_expr = "updated_at" if "updated_at" in columns else "NULL"
    conn.execute("ALTER TABLE telegram_scan_cursors RENAME TO telegram_scan_cursors_legacy")
    _create_telegram_scan_cursors_table(conn)
    conn.execute(
        f"""
        INSERT INTO telegram_scan_cursors (
            account_id,
            channel_id,
            last_checked_message_id,
            backfill_before_message_id,
            backfill_history_limit_reached,
            backfill_history_window_days,
            backfill_history_limit_reached_at,
            last_scan_started_at,
            last_scan_finished_at,
            last_scan_error,
            backfill_scan_started_at,
            backfill_scan_finished_at,
            backfill_scan_error,
            updated_at
        )
        SELECT
            {account_id_expr},
            {channel_id_expr},
            {last_checked_expr},
            {backfill_before_expr},
            {backfill_history_limit_reached_expr},
            {backfill_history_window_days_expr},
            {backfill_history_limit_reached_at_expr},
            {last_started_expr},
            {last_finished_expr},
            {last_error_expr},
            {backfill_started_expr},
            {backfill_finished_expr},
            {backfill_error_expr},
            COALESCE({updated_at_expr}, datetime('now'))
        FROM telegram_scan_cursors_legacy
        """,
        (*((LEGACY_TELEGRAM_ACCOUNT_ID,) if "account_id" not in columns else ()),),
    )
    conn.execute("DROP TABLE telegram_scan_cursors_legacy")
    _record_schema_migration(
        conn,
        "telegram_scan_cursors_account_scope_v1",
        details={"legacy_account_id": LEGACY_TELEGRAM_ACCOUNT_ID},
    )


def _hide_placeholder_scan_cursor_accounts(conn: sqlite3.Connection) -> None:
    current_account_id = _current_account_id()
    if current_account_id == DEFAULT_ACCOUNT_PLACEHOLDER:
        return
    cursor = conn.execute(
        """
        UPDATE telegram_scan_cursors
        SET account_id = ?
        WHERE account_id = ?
        """,
        (LEGACY_TELEGRAM_ACCOUNT_ID, DEFAULT_ACCOUNT_PLACEHOLDER),
    )
    if cursor.rowcount:
        _record_schema_migration(
            conn,
            "telegram_scan_cursors_default_placeholder_hidden",
            details={"migrated_rows": cursor.rowcount},
        )


def _ensure_telegram_scan_cursors_schema(conn: sqlite3.Connection) -> None:
    if _telegram_scan_cursors_requires_rebuild(conn):
        _rebuild_telegram_scan_cursors_table(conn)
    _create_telegram_scan_cursors_table(conn)
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(telegram_scan_cursors)").fetchall()
    }
    if "last_checked_message_id" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors ADD COLUMN last_checked_message_id INTEGER"
        )
    if "backfill_before_message_id" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors ADD COLUMN backfill_before_message_id INTEGER"
        )
    if "backfill_history_limit_reached" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors "
            "ADD COLUMN backfill_history_limit_reached INTEGER NOT NULL DEFAULT 0"
        )
    if "backfill_history_window_days" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors "
            "ADD COLUMN backfill_history_window_days INTEGER"
        )
    if "backfill_history_limit_reached_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors "
            "ADD COLUMN backfill_history_limit_reached_at TEXT"
        )
    if "last_scan_started_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors ADD COLUMN last_scan_started_at TEXT"
        )
    if "last_scan_finished_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors ADD COLUMN last_scan_finished_at TEXT"
        )
    if "last_scan_error" not in columns:
        conn.execute("ALTER TABLE telegram_scan_cursors ADD COLUMN last_scan_error TEXT")
    if "backfill_scan_started_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors ADD COLUMN backfill_scan_started_at TEXT"
        )
    if "backfill_scan_finished_at" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors ADD COLUMN backfill_scan_finished_at TEXT"
        )
    if "backfill_scan_error" not in columns:
        conn.execute(
            "ALTER TABLE telegram_scan_cursors ADD COLUMN backfill_scan_error TEXT"
        )
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE telegram_scan_cursors ADD COLUMN updated_at TEXT")
        conn.execute(
            "UPDATE telegram_scan_cursors SET updated_at = datetime('now') "
            "WHERE updated_at IS NULL"
        )
    conn.execute(
        f"UPDATE telegram_scan_cursors SET account_id = '{LEGACY_TELEGRAM_ACCOUNT_ID}' "
        "WHERE account_id IS NULL OR TRIM(account_id) = ''"
    )
    _hide_placeholder_scan_cursor_accounts(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_scan_cursors_account_updated "
        "ON telegram_scan_cursors(account_id, updated_at)"
    )


def _drop_legacy_telegram_channels_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS telegram_channels")


def _ensure_size_catalogs_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS size_catalogs (
            catalog_slug TEXT NOT NULL,
            size_id INTEGER NOT NULL,
            primary_size_name TEXT NOT NULL,
            size_system TEXT,
            PRIMARY KEY (catalog_slug, size_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_size_catalogs_name "
        "ON size_catalogs(catalog_slug, primary_size_name)"
    )
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(size_catalogs)").fetchall()
    }
    if "size_system" not in columns:
        conn.execute("ALTER TABLE size_catalogs ADD COLUMN size_system TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS size_catalog_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog_slug TEXT NOT NULL,
            id_v3 INTEGER,
            international TEXT,
            eu TEXT,
            ua TEXT,
            id_v5_international INTEGER,
            id_v5_eu INTEGER,
            id_v5_ua INTEGER
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_size_catalog_mappings_catalog "
        "ON size_catalog_mappings(catalog_slug)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_size_catalog_mappings_international "
        "ON size_catalog_mappings(catalog_slug, international)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_size_catalog_mappings_eu "
        "ON size_catalog_mappings(catalog_slug, eu)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_size_catalog_mappings_ua "
        "ON size_catalog_mappings(catalog_slug, ua)"
    )
    has_sizes_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sizes'"
    ).fetchone()
    if has_sizes_table:
        conn.execute("DROP TABLE sizes")


def save_uploaded_product(
    product_id: Optional[str],
    product_raw_data: dict,
    photo_ids: list[str],
) -> None:
    size = product_raw_data.get("size")
    if size is None or str(size).strip() == "":
        return
    _ensure_db_initialized()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO uploaded_products
                (product_id, name, brand, size, price, photo_ids, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                product_raw_data.get("name"),
                product_raw_data.get("brand"),
                product_raw_data.get("size"),
                product_raw_data.get("price"),
                json.dumps(photo_ids, ensure_ascii=True),
                json.dumps(product_raw_data, ensure_ascii=True),
            ),
        )


def sync_uploaded_products_from_shafa(products: list[dict]) -> dict[str, int]:
    normalized_products: list[dict] = []
    seen_ids: set[str] = set()
    for product in products:
        product_id = str(product.get("product_id") or product.get("id") or "").strip()
        name = str(product.get("name") or "").strip()
        if not product_id or not name or product_id in seen_ids:
            continue
        seen_ids.add(product_id)
        raw_payload = product.get("raw_payload")
        if not isinstance(raw_payload, dict):
            raw_payload = dict(product)
        brand_payload = raw_payload.get("brand") or {}
        brand_id = None
        if isinstance(brand_payload, dict):
            brand_value = brand_payload.get("id")
            if brand_value is not None and str(brand_value).strip() != "":
                try:
                    brand_id = int(brand_value)
                except (TypeError, ValueError):
                    brand_id = None
        normalized_products.append(
            {
                "product_id": product_id,
                "name": name,
                "brand": brand_id,
                "size": product.get("size"),
                "price": product.get("price"),
                "photo_ids": json.dumps([], ensure_ascii=True),
                "raw_payload": json.dumps(raw_payload, ensure_ascii=True),
                "shafa_created_at": _normalize_datetime_text(
                    product.get("created_at") or raw_payload.get("createdAt")
                ),
                "status_title": str(product.get("status_title") or "").strip() or None,
            }
        )

    _ensure_db_initialized()
    inserted = 0
    updated = 0
    deactivated = 0
    with _connect() as conn:
        active_ids = [item["product_id"] for item in normalized_products]
        if active_ids:
            placeholders = ",".join(["?"] * len(active_ids))
            cursor = conn.execute(
                f"""
                UPDATE uploaded_products
                SET is_active = 0
                WHERE product_id IS NOT NULL
                  AND TRIM(product_id) != ''
                  AND product_id NOT IN ({placeholders})
                  AND COALESCE(is_active, 1) != 0
                """,
                active_ids,
            )
        else:
            cursor = conn.execute(
                """
                UPDATE uploaded_products
                SET is_active = 0
                WHERE product_id IS NOT NULL
                  AND TRIM(product_id) != ''
                  AND COALESCE(is_active, 1) != 0
                """
            )
        deactivated = int(cursor.rowcount or 0)

        for item in normalized_products:
            existing = conn.execute(
                """
                SELECT id
                FROM uploaded_products
                WHERE product_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (item["product_id"],),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO uploaded_products (
                        product_id,
                        name,
                        brand,
                        size,
                        price,
                        photo_ids,
                        raw_payload,
                        created_at,
                        shafa_created_at,
                        status_title,
                        is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, 1)
                    """,
                    (
                        item["product_id"],
                        item["name"],
                        item["brand"],
                        item["size"],
                        item["price"],
                        item["photo_ids"],
                        item["raw_payload"],
                        item["shafa_created_at"],
                        item["shafa_created_at"],
                        item["status_title"],
                    ),
                )
                inserted += 1
                continue

            conn.execute(
                """
                UPDATE uploaded_products
                SET name = ?,
                    brand = ?,
                    size = ?,
                    price = ?,
                    photo_ids = ?,
                    raw_payload = ?,
                    created_at = COALESCE(?, created_at),
                    shafa_created_at = COALESCE(?, shafa_created_at),
                    status_title = ?,
                    is_active = 1
                WHERE id = ?
                """,
                (
                    item["name"],
                    item["brand"],
                    item["size"],
                    item["price"],
                    item["photo_ids"],
                    item["raw_payload"],
                    item["shafa_created_at"],
                    item["shafa_created_at"],
                    item["status_title"],
                    int(existing["id"]),
                ),
            )
            conn.execute(
                """
                UPDATE uploaded_products
                SET is_active = 0
                WHERE product_id = ? AND id != ?
                """,
                (item["product_id"], int(existing["id"])),
            )
            updated += 1

    return {
        "total": len(normalized_products),
        "inserted": inserted,
        "updated": updated,
        "deactivated": deactivated,
    }


def list_uploaded_products(limit: int = 20) -> list[dict]:
    _ensure_db_initialized()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                product_id,
                name,
                COALESCE(shafa_created_at, created_at) AS created_at
            FROM uploaded_products
            WHERE product_id IS NOT NULL AND TRIM(product_id) != ''
              AND COALESCE(is_active, 1) = 1
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "product_id": row["product_id"],
            "name": row["name"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def list_uploaded_products_for_age_check() -> list[dict]:
    _ensure_db_initialized()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                product_id,
                name,
                COALESCE(shafa_created_at, created_at) AS created_at,
                status_title,
                raw_payload
            FROM uploaded_products
            WHERE product_id IS NOT NULL AND TRIM(product_id) != ''
              AND COALESCE(is_active, 1) = 1
            ORDER BY created_at ASC, product_id ASC
            """
        ).fetchall()
    return [
        {
            "product_id": str(row["product_id"]),
            "name": str(row["name"] or "").strip() or None,
            "created_at": row["created_at"],
            "status_title": row["status_title"],
            "message_id": _extract_message_id_from_payload(row["raw_payload"]),
        }
        for row in rows
    ]


def mark_uploaded_product_inactive(
    product_id: str,
    *,
    status_title: Optional[str] = None,
) -> bool:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        return False
    _ensure_db_initialized()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE uploaded_products
            SET is_active = 0,
                status_title = COALESCE(?, status_title)
            WHERE product_id = ?
              AND COALESCE(is_active, 1) != 0
            """,
            (str(status_title or "").strip() or None, normalized_product_id),
        )
    return bool(cursor.rowcount)


def list_uploaded_product_payloads(limit: Optional[int] = None) -> list[dict]:
    _ensure_db_initialized()
    with _connect() as conn:
        if limit is None:
            rows = conn.execute(
                """
                SELECT
                    id,
                    product_id,
                    name,
                    photo_ids,
                    raw_payload,
                    COALESCE(shafa_created_at, created_at) AS created_at
                FROM uploaded_products
                WHERE raw_payload IS NOT NULL AND TRIM(raw_payload) != ''
                ORDER BY id
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    id,
                    product_id,
                    name,
                    photo_ids,
                    raw_payload,
                    COALESCE(shafa_created_at, created_at) AS created_at
                FROM uploaded_products
                WHERE raw_payload IS NOT NULL AND TRIM(raw_payload) != ''
                ORDER BY id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [
        {
            "id": row["id"],
            "product_id": row["product_id"],
            "name": row["name"],
            "photo_ids": row["photo_ids"],
            "raw_payload": row["raw_payload"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_sizes(
    sizes: list[dict],
    catalog_slug: Optional[str] = None,
    replace_catalog: bool = False,
) -> None:
    global _SIZE_ID_BY_NAME_CACHE, _SIZE_ID_BY_NAME_CATALOG_CACHE
    global _SIZE_IDS_CACHE, _SIZE_IDS_CATALOG_CACHE
    global _SIZE_MAPPING_ROWS_CACHE
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    if normalized_catalog_slug is None:
        return
    rows: list[tuple[str, object, str, Optional[str]]] = []
    for size in sizes:
        size_id = size.get("id")
        primary_name = normalize_size_text(size.get("primarySizeName"))
        if size_id is None or not primary_name:
            continue
        size_system = size.get("sizeSystem")
        rows.append((normalized_catalog_slug, size_id, primary_name, size_system))
    _ensure_db_initialized()
    with _connect() as conn:
        if replace_catalog:
            conn.execute(
                "DELETE FROM size_catalogs WHERE catalog_slug = ?",
                (normalized_catalog_slug,),
            )
        if not rows:
            _SIZE_ID_BY_NAME_CACHE = None
            _SIZE_ID_BY_NAME_CATALOG_CACHE = None
            _SIZE_IDS_CACHE = None
            _SIZE_IDS_CATALOG_CACHE = None
            return
        conn.executemany(
            """
            INSERT INTO size_catalogs (
                catalog_slug,
                size_id,
                primary_size_name,
                size_system
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(catalog_slug, size_id) DO UPDATE SET
                primary_size_name = excluded.primary_size_name,
                size_system = excluded.size_system
            """,
            rows,
        )
    _SIZE_ID_BY_NAME_CACHE = None
    _SIZE_ID_BY_NAME_CATALOG_CACHE = None
    _SIZE_IDS_CACHE = None
    _SIZE_IDS_CATALOG_CACHE = None
    _SIZE_MAPPING_ROWS_CACHE = None


def save_size_mappings(
    mappings: list[dict],
    catalog_slug: Optional[str] = None,
) -> None:
    global _SIZE_MAPPING_ROWS_CACHE
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    if normalized_catalog_slug is None:
        return
    rows: list[tuple[object, ...]] = []
    for mapping in mappings:
        rows.append(
            (
                normalized_catalog_slug,
                mapping.get("id_v3"),
                normalize_size_text(mapping.get("international")),
                normalize_size_text(mapping.get("eu")),
                normalize_size_text(mapping.get("ua")),
                mapping.get("id_v5_international"),
                mapping.get("id_v5_eu"),
                mapping.get("id_v5_ua"),
            )
        )
    _ensure_db_initialized()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM size_catalog_mappings WHERE catalog_slug = ?",
            (normalized_catalog_slug,),
        )
        if rows:
            conn.executemany(
                """
                INSERT INTO size_catalog_mappings (
                    catalog_slug,
                    id_v3,
                    international,
                    eu,
                    ua,
                    id_v5_international,
                    id_v5_eu,
                    id_v5_ua
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
    _SIZE_MAPPING_ROWS_CACHE = None


def save_brands(brands: list[dict]) -> None:
    global _BRAND_ID_BY_NAME_CACHE, _BRAND_NAMES_CACHE
    if not brands:
        return
    rows: list[tuple[object, str]] = []
    for brand in brands:
        brand_id = brand.get("id")
        name = brand.get("name")
        if brand_id is None or not name:
            continue
        rows.append((brand_id, str(name)))
    if not rows:
        return
    _ensure_db_initialized()
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO brands (id, name)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name
            """,
            rows,
        )
    if _BRAND_ID_BY_NAME_CACHE is not None or _BRAND_NAMES_CACHE is not None:
        mapping = _BRAND_ID_BY_NAME_CACHE or {}
        names_set = set(_BRAND_NAMES_CACHE or [])
        for brand_id, name in rows:
            if brand_id is None or not name:
                continue
            names_set.add(name)
            key = str(name).strip().casefold()
            if key:
                mapping[key] = int(brand_id)
        _BRAND_ID_BY_NAME_CACHE = mapping
        _BRAND_NAMES_CACHE = sorted(names_set)


def get_size_id_by_name(
    primary_size_name: str,
    catalog_slug: Optional[str] = None,
) -> Optional[int]:
    normalized_name = normalize_size_text(primary_size_name)
    if not normalized_name:
        return None
    key = normalized_name.casefold()
    mapping, mapping_by_catalog, _, _ = _load_sizes_cache()
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    if normalized_catalog_slug:
        return mapping_by_catalog.get((normalized_catalog_slug, key))
    return mapping.get(key)


def size_id_exists(size_id: int, catalog_slug: Optional[str] = None) -> bool:
    _, _, ids, ids_by_catalog = _load_sizes_cache()
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    if normalized_catalog_slug:
        scoped_ids = ids_by_catalog.get(normalized_catalog_slug)
        if scoped_ids is None:
            return False
        return size_id in scoped_ids
    return size_id in ids


def find_size_mapping_candidates(
    value: object,
    catalog_slug: Optional[str] = None,
) -> list[dict]:
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    normalized_value = normalize_size_text(value)
    if not normalized_catalog_slug or not normalized_value:
        return []
    rows = _load_size_mapping_rows_cache().get(normalized_catalog_slug) or []
    candidates: list[dict] = []
    for row in rows:
        for system in ("international", "eu", "ua"):
            if row.get(system) != normalized_value:
                continue
            matched_id = row.get(f"id_v5_{system}")
            if matched_id is None:
                continue
            candidates.append(
                {
                    "matched_system": system,
                    "matched_id": int(matched_id),
                    "row": row,
                }
            )
    return candidates


def list_size_mappings(catalog_slug: Optional[str] = None) -> list[dict]:
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    if normalized_catalog_slug:
        return list(_load_size_mapping_rows_cache().get(normalized_catalog_slug) or [])
    rows: list[dict] = []
    for catalog_rows in _load_size_mapping_rows_cache().values():
        rows.extend(catalog_rows)
    return rows


def get_brand_id_by_name(brand_name: str) -> Optional[int]:
    name = str(brand_name).strip()
    if not name:
        return None
    mapping, _ = _load_brands_cache()
    return mapping.get(name.casefold())


def list_brand_names() -> list[str]:
    _, names = _load_brands_cache()
    return list(names)


def brand_id_exists(brand_id: object) -> bool:
    try:
        normalized_id = int(brand_id)
    except (TypeError, ValueError):
        return False
    mapping, _ = _load_brands_cache()
    return normalized_id in set(mapping.values())


def save_telegram_product(
    channel_id: int,
    message_id: int,
    raw_message: str,
    parsed_data: dict,
    *,
    account_id: Optional[str] = None,
    telegram_message_date: object = None,
) -> bool:
    size = parsed_data.get("size")
    if size is None or str(size).strip() == "":
        return False
    normalized_account_id = _current_account_id(account_id)
    normalized_telegram_message_date = _normalize_datetime_text(telegram_message_date)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        if normalized_account_id != LEGACY_TELEGRAM_ACCOUNT_ID:
            legacy_row = conn.execute(
                """
                SELECT 1
                FROM telegram_products
                WHERE account_id = ?
                  AND channel_id = ?
                  AND message_id = ?
                LIMIT 1
                """,
                (
                    LEGACY_TELEGRAM_ACCOUNT_ID,
                    channel_id,
                    message_id,
                ),
            ).fetchone()
            if legacy_row is not None:
                return False
        cursor = conn.execute(
            """
            INSERT INTO telegram_products
                (
                    account_id,
                    channel_id,
                    message_id,
                    raw_message,
                    parsed_data,
                    telegram_message_date
                )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, channel_id, message_id) DO NOTHING
            """,
            (
                normalized_account_id,
                channel_id,
                message_id,
                raw_message,
                json.dumps(parsed_data, ensure_ascii=True),
                normalized_telegram_message_date,
            ),
        )
    return cursor.rowcount == 1


def creation_product_key(channel_id: int, message_id: int) -> str:
    return f"{int(channel_id)}:{int(message_id)}"


def _extract_product_name_from_parsed_payload(parsed_data: dict) -> Optional[str]:
    text = str(parsed_data.get("name") or parsed_data.get("title") or "").strip()
    return text or None


def _serialize_creation_product_row(row: sqlite3.Row) -> dict:
    parsed_data = {}
    if row["parsed_data"]:
        try:
            parsed_data = json.loads(row["parsed_data"])
        except (TypeError, ValueError):
            parsed_data = {}
    return {
        "id": int(row["id"]),
        "account_id": str(row["account_id"]),
        "telegram_product_key": str(row["telegram_product_key"]),
        "channel_id": int(row["channel_id"]),
        "message_id": int(row["message_id"]),
        "telegram_message_date": row["telegram_message_date"],
        "product_title": row["product_title"],
        "raw_message": row["raw_message"],
        "parsed_data": parsed_data,
        "media_paths": row["media_paths"],
        "status": row["status"],
        "created_product_id": row["created_product_id"],
        "attempt_count": int(row["attempt_count"] or 0),
        "last_attempt_at": row["last_attempt_at"],
        "last_error": row["last_error"],
        "skip_reason": row["skip_reason"],
        "processing_token": row["processing_token"],
        "processing_started_at": (
            float(row["processing_started_at"])
            if row["processing_started_at"] is not None
            else None
        ),
        "processing_expires_at": (
            float(row["processing_expires_at"])
            if row["processing_expires_at"] is not None
            else None
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_creation_product(
    channel_id: int,
    message_id: int,
    raw_message: str,
    parsed_data: dict,
    *,
    account_id: Optional[str] = None,
    telegram_message_date: object = None,
    media_paths: Optional[list[str]] = None,
    status: str = CREATION_PRODUCT_STATUS_NEW,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    normalized_channel_id = int(channel_id)
    normalized_message_id = int(message_id)
    normalized_key = creation_product_key(normalized_channel_id, normalized_message_id)
    normalized_date = _normalize_datetime_text(telegram_message_date)
    normalized_status = str(status or CREATION_PRODUCT_STATUS_NEW).strip()
    if normalized_status not in {
        CREATION_PRODUCT_STATUS_NEW,
        CREATION_PRODUCT_STATUS_READY,
    }:
        normalized_status = CREATION_PRODUCT_STATUS_NEW
    title = _extract_product_name_from_parsed_payload(parsed_data)
    media_paths_json = (
        json.dumps(media_paths, ensure_ascii=True) if media_paths is not None else None
    )
    _ensure_creation_db_initialized()
    with _connect(_creation_products_db_path()) as conn:
        existing = conn.execute(
            """
            SELECT 1
            FROM creation_products
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            LIMIT 1
            """,
            (normalized_account_id, normalized_channel_id, normalized_message_id),
        ).fetchone()
        cursor = conn.execute(
            """
            INSERT INTO creation_products (
                account_id,
                telegram_product_key,
                channel_id,
                message_id,
                telegram_message_date,
                product_title,
                raw_message,
                parsed_data,
                media_paths,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, channel_id, message_id) DO UPDATE SET
                telegram_message_date = COALESCE(
                    excluded.telegram_message_date,
                    creation_products.telegram_message_date
                ),
                product_title = COALESCE(
                    excluded.product_title,
                    creation_products.product_title
                ),
                raw_message = COALESCE(NULLIF(excluded.raw_message, ''), creation_products.raw_message),
                parsed_data = COALESCE(excluded.parsed_data, creation_products.parsed_data),
                media_paths = COALESCE(excluded.media_paths, creation_products.media_paths),
                updated_at = datetime('now')
            """,
            (
                normalized_account_id,
                normalized_key,
                normalized_channel_id,
                normalized_message_id,
                normalized_date,
                title,
                str(raw_message or ""),
                json.dumps(parsed_data, ensure_ascii=True),
                media_paths_json,
                normalized_status,
            ),
        )
    return existing is None and cursor.rowcount == 1


def creation_product_exists(
    *,
    account_id: Optional[str] = None,
    channel_id: Optional[int] = None,
    message_id: Optional[int] = None,
    telegram_product_key: Optional[str] = None,
) -> bool:
    if channel_id is None and message_id is None and not telegram_product_key:
        raise ValueError("channel_id/message_id or telegram_product_key is required")
    normalized_account_id = _current_account_id(account_id)
    _ensure_creation_db_initialized()
    with _connect(_creation_products_db_path()) as conn:
        if telegram_product_key:
            row = conn.execute(
                """
                SELECT 1
                FROM creation_products
                WHERE account_id = ? AND telegram_product_key = ?
                LIMIT 1
                """,
                (normalized_account_id, str(telegram_product_key)),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT 1
                FROM creation_products
                WHERE account_id = ? AND channel_id = ? AND message_id = ?
                LIMIT 1
                """,
                (normalized_account_id, int(channel_id), int(message_id)),
            ).fetchone()
    return row is not None


def get_creation_product(
    channel_id: int,
    message_id: int,
    *,
    account_id: Optional[str] = None,
) -> Optional[dict]:
    normalized_account_id = _current_account_id(account_id)
    _ensure_creation_db_initialized()
    with _connect(_creation_products_db_path()) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM creation_products
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            LIMIT 1
            """,
            (normalized_account_id, int(channel_id), int(message_id)),
        ).fetchone()
    return _serialize_creation_product_row(row) if row is not None else None


def list_ready_creation_products(
    *,
    account_id: Optional[str] = None,
    limit: int = 100,
    lease_expired_before: Optional[float] = None,
) -> list[dict]:
    normalized_account_id = _current_account_id(account_id)
    cutoff = float(time.time() if lease_expired_before is None else lease_expired_before)
    row_limit = max(int(limit), 1)
    _ensure_creation_db_initialized()
    with _connect(_creation_products_db_path()) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM creation_products
            WHERE account_id = ?
              AND (
                    status IN (?, ?)
                    OR (
                        status = ?
                        AND processing_expires_at IS NOT NULL
                        AND processing_expires_at <= ?
                    )
              )
            ORDER BY
                CASE status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    ELSE 3
                END,
                datetime(updated_at) ASC,
                message_id ASC
            LIMIT ?
            """,
            (
                normalized_account_id,
                CREATION_PRODUCT_STATUS_READY,
                CREATION_PRODUCT_STATUS_NEW,
                CREATION_PRODUCT_STATUS_PROCESSING,
                cutoff,
                CREATION_PRODUCT_STATUS_READY,
                CREATION_PRODUCT_STATUS_NEW,
                CREATION_PRODUCT_STATUS_PROCESSING,
                row_limit,
            ),
        ).fetchall()
    return [_serialize_creation_product_row(row) for row in rows]


def claim_creation_product_for_creation(
    *,
    account_id: Optional[str] = None,
    lease_seconds: int = 900,
) -> Optional[dict]:
    normalized_account_id = _current_account_id(account_id)
    now = time.time()
    expires_at = now + max(int(lease_seconds), 1)
    token = uuid.uuid4().hex
    _ensure_creation_db_initialized()
    with _connect(_creation_products_db_path()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT *
            FROM creation_products
            WHERE account_id = ?
              AND (
                    status IN (?, ?)
                    OR (
                        status = ?
                        AND processing_expires_at IS NOT NULL
                        AND processing_expires_at <= ?
                    )
              )
            ORDER BY
                CASE status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    ELSE 3
                END,
                datetime(updated_at) ASC,
                message_id ASC
            LIMIT 1
            """,
            (
                normalized_account_id,
                CREATION_PRODUCT_STATUS_READY,
                CREATION_PRODUCT_STATUS_NEW,
                CREATION_PRODUCT_STATUS_PROCESSING,
                now,
                CREATION_PRODUCT_STATUS_READY,
                CREATION_PRODUCT_STATUS_NEW,
                CREATION_PRODUCT_STATUS_PROCESSING,
            ),
        ).fetchone()
        if row is None:
            return None
        cursor = conn.execute(
            """
            UPDATE creation_products
            SET status = ?,
                attempt_count = COALESCE(attempt_count, 0) + 1,
                last_attempt_at = datetime('now'),
                processing_started_at = ?,
                processing_token = ?,
                processing_expires_at = ?,
                updated_at = datetime('now')
            WHERE id = ?
              AND account_id = ?
              AND (
                    status IN (?, ?)
                    OR (
                        status = ?
                        AND processing_expires_at IS NOT NULL
                        AND processing_expires_at <= ?
                    )
              )
            """,
            (
                CREATION_PRODUCT_STATUS_PROCESSING,
                now,
                token,
                expires_at,
                row["id"],
                normalized_account_id,
                CREATION_PRODUCT_STATUS_READY,
                CREATION_PRODUCT_STATUS_NEW,
                CREATION_PRODUCT_STATUS_PROCESSING,
                now,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        claimed = conn.execute(
            "SELECT * FROM creation_products WHERE id = ?",
            (row["id"],),
        ).fetchone()
    return _serialize_creation_product_row(claimed) if claimed is not None else None


def mark_creation_product_created(
    channel_id: int,
    message_id: int,
    created_product_id: Optional[str],
    *,
    account_id: Optional[str] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    normalized_created_product_id = str(created_product_id or "").strip() or None
    _ensure_creation_db_initialized()
    with _connect(_creation_products_db_path()) as conn:
        cursor = conn.execute(
            """
            UPDATE creation_products
            SET status = ?,
                created_product_id = ?,
                last_error = NULL,
                skip_reason = NULL,
                processing_started_at = NULL,
                processing_token = NULL,
                processing_expires_at = NULL,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                CREATION_PRODUCT_STATUS_CREATED,
                normalized_created_product_id,
                normalized_account_id,
                int(channel_id),
                int(message_id),
            ),
        )
    return cursor.rowcount == 1


def mark_creation_product_failed(
    channel_id: int,
    message_id: int,
    error_message: Optional[str],
    *,
    account_id: Optional[str] = None,
) -> int:
    normalized_account_id = _current_account_id(account_id)
    normalized_error = str(error_message or "").strip() or None
    _ensure_creation_db_initialized()
    with _connect(_creation_products_db_path()) as conn:
        conn.execute(
            """
            UPDATE creation_products
            SET status = ?,
                last_error = ?,
                processing_started_at = NULL,
                processing_token = NULL,
                processing_expires_at = NULL,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                CREATION_PRODUCT_STATUS_FAILED,
                normalized_error,
                normalized_account_id,
                int(channel_id),
                int(message_id),
            ),
        )
        row = conn.execute(
            """
            SELECT COALESCE(attempt_count, 0) AS attempt_count
            FROM creation_products
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (normalized_account_id, int(channel_id), int(message_id)),
        ).fetchone()
    return int(row["attempt_count"] or 0) if row else 0


def mark_creation_product_skipped(
    channel_id: int,
    message_id: int,
    reason: Optional[str],
    *,
    account_id: Optional[str] = None,
    created_product_id: Optional[str] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    normalized_reason = str(reason or "").strip() or None
    normalized_created_product_id = str(created_product_id or "").strip() or None
    _ensure_creation_db_initialized()
    with _connect(_creation_products_db_path()) as conn:
        cursor = conn.execute(
            """
            UPDATE creation_products
            SET status = ?,
                created_product_id = ?,
                skip_reason = ?,
                last_error = NULL,
                processing_started_at = NULL,
                processing_token = NULL,
                processing_expires_at = NULL,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                CREATION_PRODUCT_STATUS_SKIPPED,
                normalized_created_product_id,
                normalized_reason,
                normalized_account_id,
                int(channel_id),
                int(message_id),
            ),
        )
    return cursor.rowcount == 1


def count_legacy_telegram_products(
    *,
    channel_ids: Optional[list[int]] = None,
) -> int:
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    normalized_channel_ids = sorted({int(channel_id) for channel_id in channel_ids or []})
    with _connect(telegram_db_path) as conn:
        if not normalized_channel_ids:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM telegram_products
                WHERE account_id = ?
                """,
                (LEGACY_TELEGRAM_ACCOUNT_ID,),
            ).fetchone()
            return int(row[0] if row else 0)
        placeholders = ",".join(["?"] * len(normalized_channel_ids))
        row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM telegram_products
            WHERE account_id = ?
              AND channel_id IN ({placeholders})
            """,
            (LEGACY_TELEGRAM_ACCOUNT_ID, *normalized_channel_ids),
        ).fetchone()
    return int(row[0] if row else 0)


def seed_account_telegram_products_from_legacy(
    account_id: str,
    channel_ids: list[int],
    *,
    include_failed: bool = True,
    include_processing: bool = True,
) -> int:
    target_account_id = str(account_id).strip()
    if not target_account_id:
        raise ValueError("account_id is required")
    if target_account_id == LEGACY_TELEGRAM_ACCOUNT_ID:
        raise ValueError("target account_id cannot be the legacy account")
    normalized_channel_ids = sorted({int(channel_id) for channel_id in channel_ids or []})
    if not normalized_channel_ids:
        return 0
    source_statuses = [TELEGRAM_PRODUCT_STATUS_QUEUED]
    if include_failed:
        source_statuses.append(TELEGRAM_PRODUCT_STATUS_FAILED)
    if include_processing:
        source_statuses.append(TELEGRAM_PRODUCT_STATUS_PROCESSING)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    channel_placeholders = ",".join(["?"] * len(normalized_channel_ids))
    status_placeholders = ",".join(["?"] * len(source_statuses))
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            f"""
            INSERT INTO telegram_products (
                account_id,
                channel_id,
                message_id,
                raw_message,
                parsed_data,
                status,
                created,
                created_product_id,
                created_at,
                updated_at,
                status_updated_at,
                create_attempts,
                last_create_error
            )
            SELECT
                ?,
                channel_id,
                message_id,
                raw_message,
                parsed_data,
                ?,
                0,
                NULL,
                created_at,
                datetime('now'),
                datetime('now'),
                0,
                NULL
            FROM telegram_products
            WHERE account_id = ?
              AND channel_id IN ({channel_placeholders})
              AND status IN ({status_placeholders})
            ON CONFLICT(account_id, channel_id, message_id) DO NOTHING
            """,
            (
                target_account_id,
                TELEGRAM_PRODUCT_STATUS_QUEUED,
                LEGACY_TELEGRAM_ACCOUNT_ID,
                *normalized_channel_ids,
                *source_statuses,
            ),
        )
        inserted = int(cursor.rowcount or 0)
    seed_telegram_scan_cursors_from_existing_products(account_id)
    return inserted


def get_max_telegram_product_message_id(
    channel_id: int,
    *,
    account_id: Optional[str] = None,
) -> Optional[int]:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        row = conn.execute(
            """
            SELECT MAX(message_id) AS max_message_id
            FROM telegram_products
            WHERE account_id = ? AND channel_id = ?
            """,
            (normalized_account_id, channel_id),
        ).fetchone()
    if row is None or row["max_message_id"] is None:
        return None
    return int(row["max_message_id"])


def seed_telegram_scan_cursors_from_existing_products(
    account_id: str,
    *,
    channel_id: Optional[int] = None,
) -> int:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    params: tuple[object, ...]
    where_clause = "account_id = ?"
    params = (normalized_account_id,)
    if channel_id is not None:
        where_clause += " AND channel_id = ?"
        params = (normalized_account_id, channel_id)
    with _connect(telegram_db_path) as conn:
        changes_before = conn.total_changes
        conn.execute(
            f"""
            INSERT INTO telegram_scan_cursors (
                account_id,
                channel_id,
                last_checked_message_id,
                backfill_before_message_id,
                last_scan_finished_at,
                last_scan_error,
                backfill_scan_finished_at,
                backfill_scan_error,
                updated_at
            )
            SELECT
                account_id,
                channel_id,
                MAX(message_id),
                MAX(message_id),
                datetime('now'),
                NULL,
                datetime('now'),
                NULL,
                datetime('now')
            FROM telegram_products
            WHERE {where_clause}
            GROUP BY account_id, channel_id
            ON CONFLICT(account_id, channel_id) DO UPDATE SET
                last_checked_message_id = CASE
                    WHEN telegram_scan_cursors.last_checked_message_id IS NULL
                        OR excluded.last_checked_message_id > telegram_scan_cursors.last_checked_message_id
                    THEN excluded.last_checked_message_id
                    ELSE telegram_scan_cursors.last_checked_message_id
                END,
                backfill_before_message_id = CASE
                    WHEN telegram_scan_cursors.backfill_before_message_id IS NULL
                        THEN excluded.backfill_before_message_id
                    WHEN excluded.backfill_before_message_id IS NULL
                        THEN telegram_scan_cursors.backfill_before_message_id
                    WHEN excluded.backfill_before_message_id < telegram_scan_cursors.backfill_before_message_id
                        THEN excluded.backfill_before_message_id
                    ELSE telegram_scan_cursors.backfill_before_message_id
                END,
                last_scan_error = NULL,
                backfill_scan_error = NULL,
                updated_at = datetime('now')
            """,
            params,
        )
        return int(conn.total_changes - changes_before)


def seed_account_telegram_products_from_existing_db(
    account_id: str,
    *,
    include_created: bool = True,
    include_failed: bool = True,
    include_processing: bool = True,
    db_path: Optional[Path] = None,
) -> int:
    target_account_id = str(account_id).strip()
    if not target_account_id:
        raise ValueError("account_id is required")
    if target_account_id == LEGACY_TELEGRAM_ACCOUNT_ID:
        raise ValueError("target account_id cannot be the legacy account")
    source_statuses = [TELEGRAM_PRODUCT_STATUS_QUEUED]
    if include_created:
        source_statuses.append(TELEGRAM_PRODUCT_STATUS_CREATED)
    if include_failed:
        source_statuses.append(TELEGRAM_PRODUCT_STATUS_FAILED)
    if include_processing:
        source_statuses.append(TELEGRAM_PRODUCT_STATUS_PROCESSING)
    telegram_db_path = Path(db_path) if db_path is not None else _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    status_placeholders = ",".join(["?"] * len(source_statuses))
    with _connect(telegram_db_path) as conn:
        changes_before = conn.total_changes
        conn.execute(
            f"""
            WITH seed_source AS (
                SELECT MIN(id) AS source_id
                FROM telegram_products
                WHERE account_id != ?
                  AND status IN ({status_placeholders})
                GROUP BY channel_id, message_id
            )
            INSERT INTO telegram_products (
                account_id,
                channel_id,
                message_id,
                raw_message,
                parsed_data,
                status,
                created,
                created_product_id,
                created_at,
                updated_at,
                status_updated_at,
                create_attempts,
                last_create_error
            )
            SELECT
                ?,
                source.channel_id,
                source.message_id,
                source.raw_message,
                source.parsed_data,
                ?,
                0,
                NULL,
                source.created_at,
                datetime('now'),
                datetime('now'),
                0,
                NULL
            FROM telegram_products AS source
            JOIN seed_source
              ON seed_source.source_id = source.id
            ON CONFLICT(account_id, channel_id, message_id) DO NOTHING
            """,
            (
                target_account_id,
                *source_statuses,
                target_account_id,
                TELEGRAM_PRODUCT_STATUS_QUEUED,
            ),
        )
        inserted = int(conn.total_changes - changes_before)
    seed_telegram_scan_cursors_from_existing_products(target_account_id)
    return inserted


def claim_next_telegram_product_for_creation(
    *,
    account_id: Optional[str] = None,
) -> Optional[sqlite3.Row]:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"""
            SELECT *
            FROM telegram_products
            WHERE account_id = ?
              AND status IN (?, ?)
              AND COALESCE(create_attempts, 0) < ?
            ORDER BY
                CASE status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    ELSE 2
                END,
                created_at DESC,
                message_id DESC
            LIMIT 1
            """,
            (
                normalized_account_id,
                TELEGRAM_PRODUCT_STATUS_QUEUED,
                TELEGRAM_PRODUCT_STATUS_FAILED,
                MAX_PRODUCT_CREATE_ATTEMPTS,
                TELEGRAM_PRODUCT_STATUS_QUEUED,
                TELEGRAM_PRODUCT_STATUS_FAILED,
            ),
        ).fetchone()
        if row is None:
            return None
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET status = ?,
                created = 0,
                updated_at = datetime('now'),
                status_updated_at = datetime('now')
            WHERE id = ? AND account_id = ? AND status IN (?, ?)
            """,
            (
                TELEGRAM_PRODUCT_STATUS_PROCESSING,
                row["id"],
                normalized_account_id,
                TELEGRAM_PRODUCT_STATUS_QUEUED,
                TELEGRAM_PRODUCT_STATUS_FAILED,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        return conn.execute(
            """
            SELECT *
            FROM telegram_products
            WHERE id = ?
            """,
            (row["id"],),
        ).fetchone()


def save_telegram_channels(channels: list[tuple[int, str, Optional[str]]]) -> None:
    if not channels:
        return
    from telegram_subscription.sync import get_telegram_channel_records, set_telegram_channels

    current = {
        int(record["channel_id"]): dict(record)
        for record in get_telegram_channel_records()
    }
    for entry in channels:
        if len(entry) == 2:
            channel_id, name = entry
            alias = None
        else:
            channel_id, name, alias = entry
        text = str(name).strip()
        if not text:
            text = str(channel_id)
        normalized_id = int(channel_id)
        current[normalized_id] = {
            "channel_id": normalized_id,
            "name": text,
            "alias": _normalize_telegram_channel_alias(alias),
            "source_link": current.get(normalized_id, {}).get("source_link"),
        }
    set_telegram_channels(current.values())


def load_telegram_channels() -> list[dict]:
    from telegram_subscription.sync import get_telegram_channel_records

    return [
        {
            "channel_id": int(record["channel_id"]),
            "name": str(record["name"]),
            "alias": str(record["alias"]),
            "source_link": record.get("source_link"),
        }
        for record in get_telegram_channel_records()
    ]


def delete_telegram_channel(channel_id: int) -> None:
    from telegram_subscription.sync import get_telegram_channel_records, set_telegram_channels

    set_telegram_channels(
        [
            record
            for record in get_telegram_channel_records()
            if int(record["channel_id"]) != int(channel_id)
        ]
    )


def rename_telegram_channel(channel_id: int, name: str) -> bool:
    from telegram_subscription.sync import get_telegram_channel_records, set_telegram_channels

    text = str(name).strip()
    if not text:
        return False
    updated = False
    channels: list[dict] = []
    for record in get_telegram_channel_records():
        current_channel_id = int(record["channel_id"])
        if current_channel_id == int(channel_id):
            channels.append({**record, "name": text})
            updated = True
        else:
            channels.append(record)
    if updated:
        set_telegram_channels(channels)
    return updated


def update_telegram_channel_alias(channel_id: int, alias: Optional[str]) -> bool:
    from telegram_subscription.sync import get_telegram_channel_records, set_telegram_channels

    value = _normalize_telegram_channel_alias(alias)
    updated = False
    channels: list[dict] = []
    for record in get_telegram_channel_records():
        current_channel_id = int(record["channel_id"])
        if current_channel_id == int(channel_id):
            channels.append({**record, "alias": value})
            updated = True
        else:
            channels.append(record)
    if updated:
        set_telegram_channels(channels)
    return updated


def update_telegram_channel_id(old_channel_id: int, new_channel_id: int) -> bool:
    from telegram_subscription.sync import get_telegram_channel_records, set_telegram_channels

    if old_channel_id == new_channel_id:
        return False
    channels = get_telegram_channel_records()
    if any(int(record["channel_id"]) == int(new_channel_id) for record in channels):
        return False
    updated = False
    next_channels: list[dict] = []
    for record in channels:
        channel_id = int(record["channel_id"])
        if channel_id == int(old_channel_id):
            next_channels.append({**record, "channel_id": int(new_channel_id)})
            updated = True
        else:
            next_channels.append(record)
    if not updated:
        return False
    set_telegram_channels(next_channels)
    normalized_account_id = _current_account_id()
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        try:
            conn.execute(
                """
                UPDATE telegram_products
                SET channel_id = ?, updated_at = datetime('now')
                WHERE account_id = ? AND channel_id = ?
                """,
                (new_channel_id, normalized_account_id, old_channel_id),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return False
    return True


def get_next_uncreated_telegram_product(
    channel_id: int,
    *,
    account_id: Optional[str] = None,
) -> Optional[sqlite3.Row]:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        return conn.execute(
            """
            SELECT *
            FROM telegram_products
            WHERE account_id = ?
              AND channel_id = ?
              AND status IN (?, ?)
              AND COALESCE(create_attempts, 0) < ?
            ORDER BY
                CASE status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    ELSE 2
                END,
                created_at DESC,
                message_id DESC
            LIMIT 1
            """,
            (
                normalized_account_id,
                channel_id,
                TELEGRAM_PRODUCT_STATUS_QUEUED,
                TELEGRAM_PRODUCT_STATUS_FAILED,
                MAX_PRODUCT_CREATE_ATTEMPTS,
                TELEGRAM_PRODUCT_STATUS_QUEUED,
                TELEGRAM_PRODUCT_STATUS_FAILED,
            ),
        ).fetchone()


def mark_telegram_product_created(
    channel_id: int,
    message_id: int,
    created_product_id: Optional[str] = None,
    *,
    account_id: Optional[str] = None,
) -> None:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        normalized_created_product_id = str(created_product_id or "").strip() or None
        is_skipped = bool(
            normalized_created_product_id
            and normalized_created_product_id.startswith("SKIPPED_")
        )
        conn.execute(
            """
            UPDATE telegram_products
            SET status = ?,
                created = 1,
                created_product_id = ?,
                last_create_error = ?,
                shafa_deactivated_at = NULL,
                shafa_deactivate_attempts = 0,
                last_shafa_deactivate_error = NULL,
                deactivation_status = NULL,
                deactivation_queued_at = NULL,
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_retry_count = 0,
                deactivation_failed_at = NULL,
                deactivation_error = NULL,
                deactivation_completed_at = NULL,
                deactivation_check_status = NULL,
                deactivation_last_checked_at = NULL,
                deactivation_next_check_at = NULL,
                shafa_deleted_at = NULL,
                shafa_delete_attempts = 0,
                last_shafa_delete_error = NULL,
                updated_at = datetime('now')
                ,
                status_updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                (
                    TELEGRAM_PRODUCT_STATUS_SKIPPED
                    if is_skipped
                    else TELEGRAM_PRODUCT_STATUS_CREATED
                ),
                normalized_created_product_id,
                normalized_created_product_id if is_skipped else None,
                normalized_account_id,
                channel_id,
                message_id,
            ),
        )


def upsert_created_telegram_product_mapping(
    channel_id: int,
    message_id: int,
    raw_message: str,
    parsed_data: dict,
    created_product_id: str,
    *,
    account_id: Optional[str] = None,
    telegram_message_date: object = None,
) -> None:
    normalized_account_id = _current_account_id(account_id)
    normalized_created_product_id = str(created_product_id or "").strip()
    if not normalized_created_product_id:
        return
    normalized_date = _normalize_datetime_text(telegram_message_date)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute(
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
                telegram_message_date,
                last_create_error
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, NULL)
            ON CONFLICT(account_id, channel_id, message_id) DO UPDATE SET
                raw_message = COALESCE(NULLIF(excluded.raw_message, ''), telegram_products.raw_message),
                parsed_data = COALESCE(excluded.parsed_data, telegram_products.parsed_data),
                status = excluded.status,
                created = 1,
                created_product_id = excluded.created_product_id,
                telegram_message_date = COALESCE(
                    excluded.telegram_message_date,
                    telegram_products.telegram_message_date
                ),
                last_create_error = NULL,
                shafa_deactivated_at = NULL,
                shafa_deactivate_attempts = 0,
                last_shafa_deactivate_error = NULL,
                deactivation_status = NULL,
                deactivation_queued_at = NULL,
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_retry_count = 0,
                deactivation_failed_at = NULL,
                deactivation_error = NULL,
                deactivation_completed_at = NULL,
                deactivation_check_status = NULL,
                deactivation_last_checked_at = NULL,
                deactivation_next_check_at = NULL,
                shafa_deleted_at = NULL,
                shafa_delete_attempts = 0,
                last_shafa_delete_error = NULL,
                updated_at = datetime('now'),
                status_updated_at = datetime('now')
            """,
            (
                normalized_account_id,
                int(channel_id),
                int(message_id),
                str(raw_message or ""),
                json.dumps(parsed_data, ensure_ascii=True),
                TELEGRAM_PRODUCT_STATUS_CREATED,
                normalized_created_product_id,
                normalized_date,
            ),
        )


def list_created_telegram_products_missing_date(
    *,
    limit: int = 100,
    account_id: Optional[str] = None,
) -> list[dict]:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    row_limit = max(int(limit), 1)
    with _connect(telegram_db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                account_id,
                channel_id,
                message_id,
                created_product_id
            FROM telegram_products
            WHERE account_id = ?
              AND status = ?
              AND created = 1
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
              AND (
                    telegram_message_date IS NULL
                    OR TRIM(telegram_message_date) = ''
              )
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
            ORDER BY datetime(created_at) ASC, message_id ASC
            LIMIT ?
            """,
            (
                normalized_account_id,
                TELEGRAM_PRODUCT_STATUS_CREATED,
                row_limit,
            ),
        ).fetchall()
    return [
        {
            "account_id": str(row["account_id"]),
            "channel_id": int(row["channel_id"]),
            "message_id": int(row["message_id"]),
            "created_product_id": str(row["created_product_id"]),
        }
        for row in rows
    ]


def set_telegram_product_message_date(
    channel_id: int,
    message_id: int,
    telegram_message_date: object,
    *,
    account_id: Optional[str] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    normalized_telegram_message_date = _normalize_datetime_text(telegram_message_date)
    if normalized_telegram_message_date is None:
        return False
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET telegram_message_date = ?,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                normalized_telegram_message_date,
                normalized_account_id,
                channel_id,
                message_id,
            ),
        )
    return cursor.rowcount == 1


def backfill_telegram_product_message_dates_from_existing_db(
    *,
    limit: int = 100,
    account_id: Optional[str] = None,
) -> int:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    row_limit = max(int(limit), 1)
    with _connect(telegram_db_path) as conn:
        rows = conn.execute(
            """
            SELECT target.channel_id, target.message_id, source.telegram_message_date
            FROM telegram_products AS target
            JOIN telegram_products AS source
              ON source.channel_id = target.channel_id
             AND source.message_id = target.message_id
             AND source.account_id != target.account_id
            WHERE target.account_id = ?
              AND (
                    target.telegram_message_date IS NULL
                    OR TRIM(target.telegram_message_date) = ''
              )
              AND source.telegram_message_date IS NOT NULL
              AND TRIM(source.telegram_message_date) != ''
            GROUP BY target.channel_id, target.message_id
            ORDER BY datetime(source.telegram_message_date) ASC, target.message_id ASC
            LIMIT ?
            """,
            (
                normalized_account_id,
                row_limit,
            ),
        ).fetchall()
        updated = 0
        for row in rows:
            cursor = conn.execute(
                """
                UPDATE telegram_products
                SET telegram_message_date = ?,
                    updated_at = datetime('now')
                WHERE account_id = ? AND channel_id = ? AND message_id = ?
                  AND (
                        telegram_message_date IS NULL
                        OR TRIM(telegram_message_date) = ''
                  )
                """,
                (
                    row["telegram_message_date"],
                    normalized_account_id,
                    int(row["channel_id"]),
                    int(row["message_id"]),
                ),
            )
            updated += int(cursor.rowcount or 0)
    return updated


def _extract_product_name_from_parsed_data(parsed_data: object) -> Optional[str]:
    text = str(parsed_data or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("name") or "").strip()
    return name or None


def shared_telegram_product_key(channel_id: int, message_id: int) -> str:
    return f"tg:{int(channel_id)}:{int(message_id)}"


def _parse_datetime_utc(value: object) -> Optional[datetime]:
    text = _normalize_datetime_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _serialize_shared_task_account_row(row: sqlite3.Row) -> dict:
    return {
        "task_id": row["task_id"],
        "telegram_product_key": row["telegram_product_key"],
        "account_id": row["account_id"],
        "shafa_product_id": row["shafa_product_id"],
        "status": row["status"],
        "retry_count": int(row["retry_count"] or 0),
        "last_error": row["last_error"],
        "processing_token": row["processing_token"],
        "processing_started_at": (
            float(row["processing_started_at"])
            if row["processing_started_at"] is not None
            else None
        ),
        "processing_expires_at": (
            float(row["processing_expires_at"])
            if row["processing_expires_at"] is not None
            else None
        ),
        "next_retry_at": (
            float(row["next_retry_at"]) if row["next_retry_at"] is not None else None
        ),
        "completed_at": row["completed_at"],
        "telegram_message_date": row["telegram_message_date"],
        "reason": row["reason"],
    }


def reconcile_shared_telegram_products(
    *,
    account_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, int]:
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    normalized_account_id = (
        _current_account_id(account_id) if account_id is not None else None
    )
    row_limit = None if limit is None or int(limit) <= 0 else max(int(limit), 1)
    account_filter = "AND account_id = ?" if normalized_account_id is not None else ""
    limit_clause = "LIMIT ?" if row_limit is not None else ""
    params: list[object] = [TELEGRAM_PRODUCT_STATUS_CREATED]
    if normalized_account_id is not None:
        params.append(normalized_account_id)
    if row_limit is not None:
        params.append(row_limit)

    with _connect(telegram_db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                account_id,
                channel_id,
                message_id,
                created_product_id,
                parsed_data,
                telegram_message_date,
                shafa_deactivated_at,
                shafa_deleted_at
            FROM telegram_products
            WHERE status = ?
              AND created = 1
              AND account_id IS NOT NULL
              AND TRIM(account_id) != ''
              AND account_id != ?
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
              {account_filter}
            ORDER BY channel_id ASC, message_id ASC, account_id ASC
            {limit_clause}
            """,
            (TELEGRAM_PRODUCT_STATUS_CREATED, LEGACY_TELEGRAM_ACCOUNT_ID, *params[1:]),
        ).fetchall()

        products_seen: set[str] = set()
        memberships_seen = 0
        for row in rows:
            channel_id = int(row["channel_id"])
            message_id = int(row["message_id"])
            key = shared_telegram_product_key(channel_id, message_id)
            title = _extract_product_name_from_parsed_data(row["parsed_data"])
            message_date = _normalize_datetime_text(row["telegram_message_date"])
            age_source = "telegram_message_date" if message_date else None
            if row["shafa_deleted_at"]:
                account_status = SHARED_ACCOUNT_PRODUCT_MISSING
            elif row["shafa_deactivated_at"]:
                account_status = SHARED_ACCOUNT_PRODUCT_DEACTIVATED
            else:
                account_status = SHARED_ACCOUNT_PRODUCT_ACTIVE

            conn.execute(
                """
                INSERT INTO shared_telegram_products (
                    telegram_product_key,
                    channel_id,
                    message_id,
                    telegram_message_date,
                    product_title,
                    checked_status,
                    deactivation_status,
                    age_source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id, message_id) DO UPDATE SET
                    telegram_message_date = COALESCE(
                        shared_telegram_products.telegram_message_date,
                        excluded.telegram_message_date
                    ),
                    product_title = COALESCE(
                        excluded.product_title,
                        shared_telegram_products.product_title
                    ),
                    age_source = COALESCE(
                        shared_telegram_products.age_source,
                        excluded.age_source
                    ),
                    updated_at = datetime('now')
                """,
                (
                    key,
                    channel_id,
                    message_id,
                    message_date,
                    title,
                    SHARED_PRODUCT_CHECK_UNCHECKED,
                    SHARED_PRODUCT_DEACTIVATION_NONE,
                    age_source,
                ),
            )
            products_seen.add(key)

            conn.execute(
                """
                INSERT INTO shared_telegram_product_accounts (
                    telegram_product_key,
                    account_id,
                    shafa_product_id,
                    product_title,
                    account_product_status,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(telegram_product_key, account_id) DO UPDATE SET
                    shafa_product_id = excluded.shafa_product_id,
                    product_title = COALESCE(
                        excluded.product_title,
                        shared_telegram_product_accounts.product_title
                    ),
                    account_product_status = excluded.account_product_status,
                    last_seen_at = datetime('now'),
                    updated_at = datetime('now')
                """,
                (
                    key,
                    str(row["account_id"]),
                    str(row["created_product_id"]),
                    title,
                    account_status,
                ),
            )
            if account_status == SHARED_ACCOUNT_PRODUCT_ACTIVE:
                conn.execute(
                    """
                    UPDATE shared_telegram_products
                    SET checked_status = CASE
                            WHEN deactivation_status = ? THEN ?
                            ELSE checked_status
                        END,
                        next_check_at = CASE
                            WHEN deactivation_status = ? THEN NULL
                            ELSE next_check_at
                        END,
                        updated_at = datetime('now')
                    WHERE telegram_product_key = ?
                    """,
                    (
                        SHARED_PRODUCT_DEACTIVATION_COMPLETED,
                        SHARED_PRODUCT_CHECK_UNCHECKED,
                        SHARED_PRODUCT_DEACTIVATION_COMPLETED,
                        key,
                    ),
                )
            memberships_seen += 1

        copied_dates = copy_shared_telegram_product_dates_from_memberships(conn)

    return {
        "products": len(products_seen),
        "memberships": memberships_seen,
        "dates_copied": copied_dates,
    }


def copy_shared_telegram_product_dates_from_memberships(
    conn: sqlite3.Connection,
) -> int:
    rows = conn.execute(
        """
        SELECT
            shared.telegram_product_key,
            MIN(datetime(source.telegram_message_date)) AS copied_date
        FROM shared_telegram_products AS shared
        JOIN telegram_products AS source
          ON source.channel_id = shared.channel_id
         AND source.message_id = shared.message_id
        WHERE (
                shared.telegram_message_date IS NULL
                OR TRIM(shared.telegram_message_date) = ''
              )
          AND source.telegram_message_date IS NOT NULL
          AND TRIM(source.telegram_message_date) != ''
        GROUP BY shared.telegram_product_key
        """
    ).fetchall()
    updated = 0
    for row in rows:
        copied_date = _normalize_datetime_text(row["copied_date"])
        if not copied_date:
            continue
        cursor = conn.execute(
            """
            UPDATE shared_telegram_products
            SET telegram_message_date = ?,
                age_source = COALESCE(age_source, 'telegram_message_date'),
                checked_status = CASE
                    WHEN checked_status IN (?, ?) THEN ?
                    ELSE checked_status
                END,
                next_check_at = NULL,
                updated_at = datetime('now')
            WHERE telegram_product_key = ?
              AND (
                    telegram_message_date IS NULL
                    OR TRIM(telegram_message_date) = ''
                  )
            """,
            (
                copied_date,
                SHARED_PRODUCT_CHECK_DATE_MISSING,
                SHARED_PRODUCT_CHECK_NEEDS_RETRY,
                SHARED_PRODUCT_CHECK_UNCHECKED,
                row["telegram_product_key"],
            ),
        )
        updated += int(cursor.rowcount or 0)
    return updated


def plan_shared_deactivation_tasks(
    *,
    older_than_days: int = 183,
    limit: int = 100,
    account_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, int]:
    started_at = time.perf_counter()
    age_days = max(int(older_than_days), 183)
    row_limit = max(int(limit), 1)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    reconcile_shared_telegram_products(account_id=account_id)

    checked = old = fresh = date_missing = tasks = account_tasks = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=age_days)
    with _connect(telegram_db_path) as conn:
        copy_shared_telegram_product_dates_from_memberships(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM shared_telegram_products
            WHERE (
                    checked_status IN (?, ?, ?)
                    OR last_checked_at IS NULL
                    OR datetime(last_checked_at) <= datetime('now', '-1 day')
                  )
              AND (
                    next_check_at IS NULL
                    OR datetime(next_check_at) <= datetime('now')
                  )
            ORDER BY
                CASE checked_status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    ELSE 3
                END,
                datetime(telegram_message_date) ASC,
                channel_id ASC,
                message_id ASC
            LIMIT ?
            """,
            (
                SHARED_PRODUCT_CHECK_UNCHECKED,
                SHARED_PRODUCT_CHECK_NEEDS_RETRY,
                SHARED_PRODUCT_CHECK_DATE_MISSING,
                SHARED_PRODUCT_CHECK_UNCHECKED,
                SHARED_PRODUCT_CHECK_NEEDS_RETRY,
                SHARED_PRODUCT_CHECK_DATE_MISSING,
                row_limit,
            ),
        ).fetchall()

        for row in rows:
            checked += 1
            key = str(row["telegram_product_key"])
            message_date_text = _normalize_datetime_text(row["telegram_message_date"])
            message_dt = _parse_datetime_utc(message_date_text)
            if message_dt is None:
                date_missing += 1
                if not dry_run:
                    conn.execute(
                        """
                        UPDATE shared_telegram_products
                        SET checked_status = ?,
                            last_checked_at = datetime('now'),
                            next_check_at = datetime('now', '+1 day'),
                            updated_at = datetime('now')
                        WHERE telegram_product_key = ?
                        """,
                        (SHARED_PRODUCT_CHECK_DATE_MISSING, key),
                    )
                continue

            if message_dt > cutoff:
                fresh += 1
                if not dry_run:
                    conn.execute(
                        """
                        UPDATE shared_telegram_products
                        SET checked_status = ?,
                            last_checked_at = datetime('now'),
                            next_check_at = datetime('now', '+1 day'),
                            updated_at = datetime('now')
                        WHERE telegram_product_key = ?
                        """,
                        (SHARED_PRODUCT_CHECK_FRESH, key),
                    )
                continue

            old += 1
            task_id = uuid.uuid4().hex
            reason = f"telegram_message_older_than_{age_days}_days"
            if not dry_run:
                conn.execute(
                    """
                    INSERT INTO shared_deactivation_tasks (
                        task_id,
                        telegram_product_key,
                        telegram_message_date,
                        reason,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(telegram_product_key) DO UPDATE SET
                        telegram_message_date = excluded.telegram_message_date,
                        reason = excluded.reason,
                        status = CASE
                            WHEN shared_deactivation_tasks.status = ? THEN ?
                            ELSE shared_deactivation_tasks.status
                        END,
                        updated_at = datetime('now')
                    """,
                    (
                        task_id,
                        key,
                        message_date_text,
                        reason,
                        SHARED_TASK_STATUS_PENDING,
                        SHARED_TASK_STATUS_COMPLETED,
                        SHARED_TASK_STATUS_PARTIAL,
                    ),
                )
                task_row = conn.execute(
                    """
                    SELECT task_id
                    FROM shared_deactivation_tasks
                    WHERE telegram_product_key = ?
                    """,
                    (key,),
                ).fetchone()
                if task_row is None:
                    continue
                resolved_task_id = str(task_row["task_id"])
                tasks += 1
                membership_rows = conn.execute(
                    """
                    SELECT account_id, shafa_product_id
                    FROM shared_telegram_product_accounts
                    WHERE telegram_product_key = ?
                      AND account_product_status = ?
                      AND shafa_product_id IS NOT NULL
                      AND TRIM(shafa_product_id) != ''
                    """,
                    (key, SHARED_ACCOUNT_PRODUCT_ACTIVE),
                ).fetchall()
                for membership in membership_rows:
                    cursor = conn.execute(
                        """
                        INSERT INTO shared_deactivation_task_accounts (
                            task_id,
                            telegram_product_key,
                            account_id,
                            shafa_product_id,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(task_id, account_id) DO UPDATE SET
                            shafa_product_id = CASE
                                WHEN shared_deactivation_task_accounts.status = ?
                                    THEN shared_deactivation_task_accounts.shafa_product_id
                                ELSE excluded.shafa_product_id
                            END,
                            status = CASE
                                WHEN shared_deactivation_task_accounts.status IN (?, ?)
                                    THEN shared_deactivation_task_accounts.status
                                ELSE excluded.status
                            END,
                            updated_at = datetime('now')
                        """,
                        (
                            resolved_task_id,
                            key,
                            str(membership["account_id"]),
                            str(membership["shafa_product_id"]),
                            SHARED_ACCOUNT_TASK_PENDING,
                            SHARED_ACCOUNT_TASK_COMPLETED,
                            SHARED_ACCOUNT_TASK_COMPLETED,
                            SHARED_ACCOUNT_TASK_PROCESSING,
                        ),
                    )
                    account_tasks += int(cursor.rowcount or 0)
                conn.execute(
                    """
                    UPDATE shared_telegram_products
                    SET checked_status = ?,
                        deactivation_status = ?,
                        last_checked_at = datetime('now'),
                        next_check_at = NULL,
                        age_source = COALESCE(age_source, 'telegram_message_date'),
                        updated_at = datetime('now')
                    WHERE telegram_product_key = ?
                    """,
                    (
                        SHARED_PRODUCT_CHECK_OLD,
                        SHARED_PRODUCT_DEACTIVATION_QUEUED,
                        key,
                    ),
                )
                update_shared_deactivation_parent_status(conn, resolved_task_id)

    return {
        "checked": checked,
        "old": old,
        "fresh": fresh,
        "date_missing": date_missing,
        "tasks": tasks,
        "account_tasks": account_tasks,
        "dry_run": int(bool(dry_run)),
        "duration_ms": round((time.perf_counter() - started_at) * 1000),
    }


def claim_shared_deactivation_task_for_account(
    *,
    account_id: Optional[str] = None,
    lease_seconds: float = 900.0,
    max_retries: int = 3,
    now_ts: Optional[float] = None,
) -> Optional[dict]:
    normalized_account_id = _current_account_id(account_id)
    current_ts = float(now_ts if now_ts is not None else time.time())
    lease_expires_at = current_ts + max(float(lease_seconds), 1.0)
    retry_limit = max(int(max_retries), 1)
    token = uuid.uuid4().hex
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT account_task.*, parent.telegram_message_date, parent.reason
            FROM shared_deactivation_task_accounts AS account_task
            JOIN shared_deactivation_tasks AS parent
              ON parent.task_id = account_task.task_id
            WHERE account_task.account_id = ?
              AND parent.status != ?
              AND (
                    account_task.status = ?
                    OR account_task.status = ?
                    OR (
                        account_task.status = ?
                        AND COALESCE(account_task.retry_count, 0) < ?
                    )
                    OR (
                        account_task.status = ?
                        AND account_task.processing_expires_at IS NOT NULL
                        AND account_task.processing_expires_at <= ?
                    )
                  )
              AND (
                    account_task.next_retry_at IS NULL
                    OR account_task.next_retry_at <= ?
                  )
            ORDER BY
                CASE account_task.status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    WHEN ? THEN 3
                    ELSE 4
                END,
                account_task.created_at ASC
            LIMIT 1
            """,
            (
                normalized_account_id,
                SHARED_TASK_STATUS_COMPLETED,
                SHARED_ACCOUNT_TASK_PENDING,
                SHARED_ACCOUNT_TASK_RETRY_SCHEDULED,
                SHARED_ACCOUNT_TASK_FAILED,
                retry_limit,
                SHARED_ACCOUNT_TASK_PROCESSING,
                current_ts,
                current_ts,
                SHARED_ACCOUNT_TASK_PENDING,
                SHARED_ACCOUNT_TASK_RETRY_SCHEDULED,
                SHARED_ACCOUNT_TASK_FAILED,
                SHARED_ACCOUNT_TASK_PROCESSING,
            ),
        ).fetchone()
        if row is None:
            return None
        cursor = conn.execute(
            """
            UPDATE shared_deactivation_task_accounts
            SET status = ?,
                processing_token = ?,
                processing_started_at = ?,
                processing_expires_at = ?,
                updated_at = datetime('now')
            WHERE task_id = ?
              AND account_id = ?
              AND (
                    status = ?
                    OR status = ?
                    OR (
                        status = ?
                        AND COALESCE(retry_count, 0) < ?
                    )
                    OR (
                        status = ?
                        AND processing_expires_at IS NOT NULL
                        AND processing_expires_at <= ?
                    )
                  )
            """,
            (
                SHARED_ACCOUNT_TASK_PROCESSING,
                token,
                current_ts,
                lease_expires_at,
                row["task_id"],
                normalized_account_id,
                SHARED_ACCOUNT_TASK_PENDING,
                SHARED_ACCOUNT_TASK_RETRY_SCHEDULED,
                SHARED_ACCOUNT_TASK_FAILED,
                retry_limit,
                SHARED_ACCOUNT_TASK_PROCESSING,
                current_ts,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        claimed = conn.execute(
            """
            SELECT account_task.*, parent.telegram_message_date, parent.reason
            FROM shared_deactivation_task_accounts AS account_task
            JOIN shared_deactivation_tasks AS parent
              ON parent.task_id = account_task.task_id
            WHERE account_task.task_id = ?
              AND account_task.account_id = ?
              AND account_task.processing_token = ?
            """,
            (row["task_id"], normalized_account_id, token),
        ).fetchone()
        update_shared_deactivation_parent_status(conn, str(row["task_id"]))
    return _serialize_shared_task_account_row(claimed) if claimed is not None else None


def complete_shared_deactivation_task_for_account(
    *,
    task_id: str,
    account_id: Optional[str],
    processing_token: str,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    token = str(processing_token or "").strip()
    if not token:
        return False
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE shared_deactivation_task_accounts
            SET status = ?,
                last_error = NULL,
                processing_token = NULL,
                processing_started_at = NULL,
                processing_expires_at = NULL,
                next_retry_at = NULL,
                completed_at = datetime('now'),
                updated_at = datetime('now')
            WHERE task_id = ?
              AND account_id = ?
              AND processing_token = ?
              AND status = ?
            """,
            (
                SHARED_ACCOUNT_TASK_COMPLETED,
                task_id,
                normalized_account_id,
                token,
                SHARED_ACCOUNT_TASK_PROCESSING,
            ),
        )
        updated = cursor.rowcount == 1
        if updated:
            row = conn.execute(
                """
                SELECT
                    account_task.telegram_product_key,
                    account_task.shafa_product_id,
                    shared.channel_id,
                    shared.message_id
                FROM shared_deactivation_task_accounts AS account_task
                JOIN shared_telegram_products AS shared
                  ON shared.telegram_product_key = account_task.telegram_product_key
                WHERE account_task.task_id = ? AND account_task.account_id = ?
                """,
                (task_id, normalized_account_id),
            ).fetchone()
            if row is not None:
                conn.execute(
                    """
                    UPDATE telegram_products
                    SET shafa_deactivated_at = COALESCE(
                            shafa_deactivated_at,
                            datetime('now')
                        ),
                        last_shafa_deactivate_error = NULL,
                        deactivation_status = ?,
                        deactivation_processing_started_at = NULL,
                        deactivation_processing_token = NULL,
                        deactivation_processing_expires_at = NULL,
                        deactivation_failed_at = NULL,
                        deactivation_error = NULL,
                        deactivation_completed_at = datetime('now'),
                        updated_at = datetime('now')
                    WHERE account_id = ?
                      AND channel_id = ?
                      AND message_id = ?
                      AND created_product_id = ?
                    """,
                    (
                        TELEGRAM_DEACTIVATION_STATUS_COMPLETED,
                        normalized_account_id,
                        int(row["channel_id"]),
                        int(row["message_id"]),
                        str(row["shafa_product_id"]),
                    ),
                )
                conn.execute(
                    """
                    UPDATE shared_telegram_product_accounts
                    SET account_product_status = ?,
                        updated_at = datetime('now')
                    WHERE telegram_product_key = ?
                      AND account_id = ?
                    """,
                    (
                        SHARED_ACCOUNT_PRODUCT_DEACTIVATED,
                        row["telegram_product_key"],
                        normalized_account_id,
                    ),
                )
            update_shared_deactivation_parent_status(conn, task_id)
    return updated


def skip_shared_deactivation_task_not_found_for_account(
    *,
    task_id: str,
    account_id: Optional[str],
    processing_token: str,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    token = str(processing_token or "").strip()
    if not token:
        return False
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE shared_deactivation_task_accounts
            SET status = ?,
                last_error = NULL,
                processing_token = NULL,
                processing_started_at = NULL,
                processing_expires_at = NULL,
                next_retry_at = NULL,
                completed_at = datetime('now'),
                updated_at = datetime('now')
            WHERE task_id = ?
              AND account_id = ?
              AND processing_token = ?
              AND status = ?
            """,
            (
                SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
                task_id,
                normalized_account_id,
                token,
                SHARED_ACCOUNT_TASK_PROCESSING,
            ),
        )
        updated = cursor.rowcount == 1
        if updated:
            row = conn.execute(
                """
                SELECT
                    account_task.telegram_product_key,
                    account_task.shafa_product_id,
                    shared.channel_id,
                    shared.message_id
                FROM shared_deactivation_task_accounts AS account_task
                JOIN shared_telegram_products AS shared
                  ON shared.telegram_product_key = account_task.telegram_product_key
                WHERE account_task.task_id = ? AND account_task.account_id = ?
                """,
                (task_id, normalized_account_id),
            ).fetchone()
            if row is not None:
                conn.execute(
                    """
                    UPDATE telegram_products
                    SET shafa_deleted_at = COALESCE(
                            shafa_deleted_at,
                            datetime('now')
                        ),
                        last_shafa_deactivate_error = NULL,
                        deactivation_status = ?,
                        deactivation_processing_started_at = NULL,
                        deactivation_processing_token = NULL,
                        deactivation_processing_expires_at = NULL,
                        deactivation_failed_at = NULL,
                        deactivation_error = NULL,
                        deactivation_completed_at = datetime('now'),
                        updated_at = datetime('now')
                    WHERE account_id = ?
                      AND channel_id = ?
                      AND message_id = ?
                      AND created_product_id = ?
                    """,
                    (
                        TELEGRAM_DEACTIVATION_STATUS_SKIPPED_NOT_FOUND,
                        normalized_account_id,
                        int(row["channel_id"]),
                        int(row["message_id"]),
                        str(row["shafa_product_id"]),
                    ),
                )
                conn.execute(
                    """
                    UPDATE shared_telegram_product_accounts
                    SET account_product_status = ?,
                        updated_at = datetime('now')
                    WHERE telegram_product_key = ?
                      AND account_id = ?
                    """,
                    (
                        SHARED_ACCOUNT_PRODUCT_MISSING,
                        row["telegram_product_key"],
                        normalized_account_id,
                    ),
                )
            update_shared_deactivation_parent_status(conn, task_id)
    return updated


def fail_shared_deactivation_task_for_account(
    *,
    task_id: str,
    account_id: Optional[str],
    processing_token: str,
    error_message: str,
    retry_delay_seconds: float = 300.0,
    max_retries: int = 3,
    now_ts: Optional[float] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    token = str(processing_token or "").strip()
    if not token:
        return False
    retry_limit = max(int(max_retries), 1)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(retry_count, 0) AS retry_count
            FROM shared_deactivation_task_accounts
            WHERE task_id = ?
              AND account_id = ?
              AND processing_token = ?
              AND status = ?
            """,
            (
                task_id,
                normalized_account_id,
                token,
                SHARED_ACCOUNT_TASK_PROCESSING,
            ),
        ).fetchone()
        if row is None:
            return False
        next_retry_count = int(row["retry_count"] or 0) + 1
        next_status = (
            SHARED_ACCOUNT_TASK_RETRY_SCHEDULED
            if next_retry_count < retry_limit
            else SHARED_ACCOUNT_TASK_FAILED
        )
        current_ts = float(now_ts if now_ts is not None else time.time())
        next_retry_at = (
            current_ts + max(float(retry_delay_seconds), 1.0)
            if next_status == SHARED_ACCOUNT_TASK_RETRY_SCHEDULED
            else None
        )
        cursor = conn.execute(
            """
            UPDATE shared_deactivation_task_accounts
            SET status = ?,
                retry_count = ?,
                last_error = ?,
                processing_token = NULL,
                processing_started_at = NULL,
                processing_expires_at = NULL,
                next_retry_at = ?,
                updated_at = datetime('now')
            WHERE task_id = ?
              AND account_id = ?
              AND processing_token = ?
              AND status = ?
            """,
            (
                next_status,
                next_retry_count,
                str(error_message or "").strip() or None,
                next_retry_at,
                task_id,
                normalized_account_id,
                token,
                SHARED_ACCOUNT_TASK_PROCESSING,
            ),
        )
        updated = cursor.rowcount == 1
        if updated:
            update_shared_deactivation_parent_status(conn, task_id)
    return updated


def update_shared_deactivation_parent_status(
    conn: sqlite3.Connection,
    task_id: str,
) -> None:
    rows = conn.execute(
        """
        SELECT status
        FROM shared_deactivation_task_accounts
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchall()
    if not rows:
        next_status = SHARED_TASK_STATUS_PENDING
    else:
        statuses = {str(row["status"]) for row in rows}
        terminal_success_statuses = {
            SHARED_ACCOUNT_TASK_COMPLETED,
            SHARED_ACCOUNT_TASK_SKIPPED,
            SHARED_ACCOUNT_TASK_SKIPPED_NOT_FOUND,
        }
        if statuses <= terminal_success_statuses:
            next_status = SHARED_TASK_STATUS_COMPLETED
        elif statuses == {SHARED_ACCOUNT_TASK_FAILED}:
            next_status = SHARED_TASK_STATUS_FAILED
        elif SHARED_ACCOUNT_TASK_PROCESSING in statuses:
            next_status = SHARED_TASK_STATUS_PROCESSING
        elif statuses & terminal_success_statuses:
            next_status = SHARED_TASK_STATUS_PARTIAL
        elif SHARED_ACCOUNT_TASK_FAILED in statuses and statuses <= {
            SHARED_ACCOUNT_TASK_FAILED,
            SHARED_ACCOUNT_TASK_SKIPPED,
        }:
            next_status = SHARED_TASK_STATUS_FAILED
        else:
            next_status = SHARED_TASK_STATUS_PENDING
    conn.execute(
        """
        UPDATE shared_deactivation_tasks
        SET status = ?,
            updated_at = datetime('now')
        WHERE task_id = ?
        """,
        (next_status, task_id),
    )
    task_row = conn.execute(
        """
        SELECT telegram_product_key
        FROM shared_deactivation_tasks
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchone()
    if task_row is None:
        return
    product_status = {
        SHARED_TASK_STATUS_COMPLETED: SHARED_PRODUCT_DEACTIVATION_COMPLETED,
        SHARED_TASK_STATUS_FAILED: SHARED_PRODUCT_DEACTIVATION_FAILED,
        SHARED_TASK_STATUS_PARTIAL: SHARED_PRODUCT_DEACTIVATION_PARTIAL,
        SHARED_TASK_STATUS_PROCESSING: SHARED_PRODUCT_DEACTIVATION_PARTIAL,
    }.get(next_status, SHARED_PRODUCT_DEACTIVATION_QUEUED)
    conn.execute(
        """
        UPDATE shared_telegram_products
        SET deactivation_status = ?,
            updated_at = datetime('now')
        WHERE telegram_product_key = ?
        """,
        (product_status, task_row["telegram_product_key"]),
    )


def _extract_message_id_from_payload(raw_payload: object) -> Optional[int]:
    text = str(raw_payload or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    def _walk(value: object) -> Optional[int]:
        if isinstance(value, dict):
            for key in (
                "message_id",
                "messageId",
                "telegram_message_id",
                "telegramMessageId",
            ):
                raw_message_id = value.get(key)
                if raw_message_id is None or str(raw_message_id).strip() == "":
                    continue
                try:
                    return int(raw_message_id)
                except (TypeError, ValueError):
                    continue
            for nested in value.values():
                found = _walk(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = _walk(item)
                if found is not None:
                    return found
        return None

    return _walk(payload)


def _serialize_created_telegram_product_row(row: sqlite3.Row) -> dict:
    def _optional(key: str):
        try:
            return row[key]
        except (IndexError, KeyError):
            return None

    return {
        "account_id": str(row["account_id"]),
        "channel_id": int(row["channel_id"]),
        "message_id": int(row["message_id"]),
        "created_product_id": str(row["created_product_id"]),
        "product_name": _extract_product_name_from_parsed_data(row["parsed_data"]),
        "telegram_message_date": row["telegram_message_date"],
        "shafa_deactivate_attempts": int(row["shafa_deactivate_attempts"] or 0),
        "last_shafa_deactivate_error": row["last_shafa_deactivate_error"],
        "shafa_delete_attempts": int(row["shafa_delete_attempts"] or 0),
        "last_shafa_delete_error": row["last_shafa_delete_error"],
        "deactivation_check_status": _optional("deactivation_check_status"),
        "deactivation_last_checked_at": _optional("deactivation_last_checked_at"),
        "deactivation_next_check_at": _optional("deactivation_next_check_at"),
    }


def list_created_telegram_products_for_age_check(
    *,
    account_id: Optional[str] = None,
) -> list[dict]:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                account_id,
                channel_id,
                message_id,
                created_product_id,
                parsed_data,
                telegram_message_date,
                shafa_deactivate_attempts,
                last_shafa_deactivate_error,
                shafa_delete_attempts,
                last_shafa_delete_error,
                deactivation_check_status,
                deactivation_last_checked_at,
                deactivation_next_check_at
            FROM telegram_products
            WHERE account_id = ?
              AND status = ?
              AND created = 1
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
            ORDER BY
                CASE
                    WHEN telegram_message_date IS NULL OR TRIM(telegram_message_date) = ''
                        THEN 1
                    ELSE 0
                END,
                datetime(telegram_message_date) ASC,
                message_id ASC
            """
            ,
            (
                normalized_account_id,
                TELEGRAM_PRODUCT_STATUS_CREATED,
            ),
        ).fetchall()
    return [_serialize_created_telegram_product_row(row) for row in rows]


def mark_telegram_product_deactivation_check(
    channel_id: int,
    message_id: int,
    *,
    check_status: str,
    next_check_at: Optional[datetime] = None,
    account_id: Optional[str] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    normalized_status = str(check_status or "").strip() or None
    next_check_text = (
        next_check_at.astimezone(timezone.utc).isoformat()
        if next_check_at is not None
        else None
    )
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET deactivation_check_status = ?,
                deactivation_last_checked_at = datetime('now'),
                deactivation_next_check_at = ?,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                normalized_status,
                next_check_text,
                normalized_account_id,
                channel_id,
                message_id,
            ),
        )
    return cursor.rowcount == 1


def list_expired_created_telegram_products(
    *,
    older_than_days: int,
    limit: int = 20,
    account_id: Optional[str] = None,
) -> list[dict]:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    age_days = max(int(older_than_days), 183)
    row_limit = max(int(limit), 1)
    with _connect(telegram_db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                account_id,
                channel_id,
                message_id,
                created_product_id,
                parsed_data,
                telegram_message_date,
                shafa_deactivate_attempts,
                last_shafa_deactivate_error,
                shafa_delete_attempts,
                last_shafa_delete_error
            FROM telegram_products
            WHERE account_id = ?
              AND status = ?
              AND created = 1
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
              AND telegram_message_date IS NOT NULL
              AND TRIM(telegram_message_date) != ''
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
              AND datetime(telegram_message_date) <= datetime('now', ?)
            ORDER BY datetime(telegram_message_date) ASC, message_id ASC
            LIMIT ?
            """,
            (
                normalized_account_id,
                TELEGRAM_PRODUCT_STATUS_CREATED,
                f"-{age_days} days",
                row_limit,
            ),
        ).fetchall()
    return [_serialize_created_telegram_product_row(row) for row in rows]


def _serialize_deactivation_queue_row(row: sqlite3.Row) -> dict:
    item = _serialize_created_telegram_product_row(row)
    item.update(
        {
            "deactivation_status": row["deactivation_status"],
            "deactivation_queued_at": row["deactivation_queued_at"],
            "deactivation_processing_started_at": (
                float(row["deactivation_processing_started_at"])
                if row["deactivation_processing_started_at"] is not None
                else None
            ),
            "deactivation_processing_token": row["deactivation_processing_token"],
            "deactivation_processing_expires_at": (
                float(row["deactivation_processing_expires_at"])
                if row["deactivation_processing_expires_at"] is not None
                else None
            ),
            "deactivation_retry_count": int(row["deactivation_retry_count"] or 0),
            "deactivation_failed_at": row["deactivation_failed_at"],
            "deactivation_error": row["deactivation_error"],
            "deactivation_completed_at": row["deactivation_completed_at"],
        }
    )
    return item


def enqueue_expired_telegram_products_for_deactivation(
    *,
    older_than_days: int,
    limit: int = 100,
    account_id: Optional[str] = None,
) -> int:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    age_days = max(int(older_than_days), 183)
    row_limit = max(int(limit), 1)
    with _connect(telegram_db_path) as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM telegram_products
            WHERE account_id = ?
              AND status = ?
              AND created = 1
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
              AND telegram_message_date IS NOT NULL
              AND TRIM(telegram_message_date) != ''
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
              AND datetime(telegram_message_date) <= datetime('now', ?)
              AND (
                    deactivation_status IS NULL
                    OR TRIM(deactivation_status) = ''
                    OR deactivation_status = ?
                  )
            ORDER BY datetime(telegram_message_date) ASC, message_id ASC
            LIMIT ?
            """,
            (
                normalized_account_id,
                TELEGRAM_PRODUCT_STATUS_CREATED,
                f"-{age_days} days",
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
                row_limit,
            ),
        ).fetchall()
        if not rows:
            return 0
        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join(["?"] * len(ids))
        cursor = conn.execute(
            f"""
            UPDATE telegram_products
            SET deactivation_status = ?,
                deactivation_check_status = ?,
                deactivation_last_checked_at = datetime('now'),
                deactivation_next_check_at = NULL,
                deactivation_queued_at = COALESCE(
                    deactivation_queued_at,
                    datetime('now')
                ),
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_failed_at = NULL,
                deactivation_error = NULL,
                updated_at = datetime('now')
            WHERE account_id = ?
              AND id IN ({placeholders})
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
              AND (
                    deactivation_status IS NULL
                    OR TRIM(deactivation_status) = ''
                    OR deactivation_status = ?
                  )
            """,
            (
                TELEGRAM_DEACTIVATION_STATUS_PENDING,
                TELEGRAM_DEACTIVATION_CHECK_OLD,
                normalized_account_id,
                *ids,
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
            ),
        )
    return int(cursor.rowcount or 0)


def enqueue_telegram_product_deactivation(
    channel_id: int,
    message_id: int,
    *,
    account_id: Optional[str] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET deactivation_status = ?,
                deactivation_check_status = ?,
                deactivation_last_checked_at = datetime('now'),
                deactivation_next_check_at = NULL,
                deactivation_queued_at = COALESCE(
                    deactivation_queued_at,
                    datetime('now')
                ),
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_failed_at = NULL,
                deactivation_error = NULL,
                updated_at = datetime('now')
            WHERE account_id = ?
              AND channel_id = ?
              AND message_id = ?
              AND status = ?
              AND created = 1
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
              AND (
                    deactivation_status IS NULL
                    OR TRIM(deactivation_status) = ''
                    OR deactivation_status IN (?, ?)
                  )
            """,
            (
                TELEGRAM_DEACTIVATION_STATUS_PENDING,
                TELEGRAM_DEACTIVATION_CHECK_OLD,
                normalized_account_id,
                channel_id,
                message_id,
                TELEGRAM_PRODUCT_STATUS_CREATED,
                TELEGRAM_DEACTIVATION_STATUS_PENDING,
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
            ),
        )
    return cursor.rowcount == 1


def claim_telegram_product_deactivation(
    *,
    account_id: Optional[str] = None,
    channel_id: Optional[int] = None,
    message_id: Optional[int] = None,
    lease_seconds: float = 900.0,
    max_retries: int = 3,
    now_ts: Optional[float] = None,
) -> Optional[dict]:
    normalized_account_id = _current_account_id(account_id)
    lease_duration_seconds = max(float(lease_seconds), 1.0)
    current_ts = float(now_ts if now_ts is not None else time.time())
    lease_expires_at = current_ts + lease_duration_seconds
    retry_limit = max(int(max_retries), 1)
    lease_token = uuid.uuid4().hex
    queue_filters = ""
    params: list[object] = [
        normalized_account_id,
        TELEGRAM_PRODUCT_STATUS_CREATED,
        TELEGRAM_DEACTIVATION_STATUS_PENDING,
        TELEGRAM_DEACTIVATION_STATUS_PROCESSING,
        current_ts,
        TELEGRAM_DEACTIVATION_STATUS_FAILED,
        retry_limit,
    ]
    if channel_id is not None:
        queue_filters += " AND channel_id = ?"
        params.append(int(channel_id))
    if message_id is not None:
        queue_filters += " AND message_id = ?"
        params.append(int(message_id))
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"""
            SELECT *
            FROM telegram_products
            WHERE account_id = ?
              AND status = ?
              AND created = 1
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
              AND (
                    deactivation_status = ?
                    OR (
                        deactivation_status = ?
                        AND deactivation_processing_expires_at IS NOT NULL
                        AND deactivation_processing_expires_at <= ?
                    )
                    OR (
                        deactivation_status = ?
                        AND COALESCE(deactivation_retry_count, 0) < ?
                    )
                  )
              {queue_filters}
            ORDER BY
                CASE deactivation_status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    ELSE 3
                END,
                datetime(telegram_message_date) ASC,
                message_id ASC
            LIMIT 1
            """,
            (
                *params,
                TELEGRAM_DEACTIVATION_STATUS_PENDING,
                TELEGRAM_DEACTIVATION_STATUS_PROCESSING,
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
            ),
        ).fetchone()
        if row is None:
            return None
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET deactivation_status = ?,
                deactivation_processing_started_at = ?,
                deactivation_processing_token = ?,
                deactivation_processing_expires_at = ?,
                updated_at = datetime('now')
            WHERE id = ?
              AND account_id = ?
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
              AND (
                    deactivation_status = ?
                    OR (
                        deactivation_status = ?
                        AND deactivation_processing_expires_at IS NOT NULL
                        AND deactivation_processing_expires_at <= ?
                    )
                    OR (
                        deactivation_status = ?
                        AND COALESCE(deactivation_retry_count, 0) < ?
                    )
                  )
            """,
            (
                TELEGRAM_DEACTIVATION_STATUS_PROCESSING,
                current_ts,
                lease_token,
                lease_expires_at,
                int(row["id"]),
                normalized_account_id,
                TELEGRAM_DEACTIVATION_STATUS_PENDING,
                TELEGRAM_DEACTIVATION_STATUS_PROCESSING,
                current_ts,
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
                retry_limit,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        claimed = conn.execute(
            """
            SELECT
                account_id,
                channel_id,
                message_id,
                created_product_id,
                parsed_data,
                telegram_message_date,
                shafa_deactivate_attempts,
                last_shafa_deactivate_error,
                shafa_delete_attempts,
                last_shafa_delete_error,
                deactivation_status,
                deactivation_queued_at,
                deactivation_processing_started_at,
                deactivation_processing_token,
                deactivation_processing_expires_at,
                deactivation_retry_count,
                deactivation_failed_at,
                deactivation_error,
                deactivation_completed_at
            FROM telegram_products
            WHERE id = ?
            """,
            (int(row["id"]),),
        ).fetchone()
    return _serialize_deactivation_queue_row(claimed) if claimed is not None else None


def list_telegram_product_deactivation_queue(
    *,
    account_id: Optional[str] = None,
    limit: int = 20,
    max_retries: int = 3,
    now_ts: Optional[float] = None,
) -> list[dict]:
    normalized_account_id = _current_account_id(account_id)
    row_limit = max(int(limit), 1)
    retry_limit = max(int(max_retries), 1)
    current_ts = float(now_ts if now_ts is not None else time.time())
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                account_id,
                channel_id,
                message_id,
                created_product_id,
                parsed_data,
                telegram_message_date,
                shafa_deactivate_attempts,
                last_shafa_deactivate_error,
                shafa_delete_attempts,
                last_shafa_delete_error,
                deactivation_status,
                deactivation_queued_at,
                deactivation_processing_started_at,
                deactivation_processing_token,
                deactivation_processing_expires_at,
                deactivation_retry_count,
                deactivation_failed_at,
                deactivation_error,
                deactivation_completed_at
            FROM telegram_products
            WHERE account_id = ?
              AND status = ?
              AND created = 1
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
              AND shafa_deactivated_at IS NULL
              AND shafa_deleted_at IS NULL
              AND (
                    deactivation_status = ?
                    OR (
                        deactivation_status = ?
                        AND COALESCE(deactivation_retry_count, 0) < ?
                    )
                    OR (
                        deactivation_status = ?
                        AND deactivation_processing_expires_at IS NOT NULL
                        AND deactivation_processing_expires_at <= ?
                    )
                  )
            ORDER BY
                CASE deactivation_status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    ELSE 3
                END,
                datetime(telegram_message_date) ASC,
                message_id ASC
            LIMIT ?
            """,
            (
                normalized_account_id,
                TELEGRAM_PRODUCT_STATUS_CREATED,
                TELEGRAM_DEACTIVATION_STATUS_PENDING,
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
                retry_limit,
                TELEGRAM_DEACTIVATION_STATUS_PROCESSING,
                current_ts,
                TELEGRAM_DEACTIVATION_STATUS_PENDING,
                TELEGRAM_DEACTIVATION_STATUS_PROCESSING,
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
                row_limit,
            ),
        ).fetchall()
    return [_serialize_deactivation_queue_row(row) for row in rows]


def finish_telegram_product_deactivation(
    channel_id: int,
    message_id: int,
    lease_token: str,
    *,
    success: bool,
    error_message: Optional[str] = None,
    account_id: Optional[str] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    token = str(lease_token or "").strip()
    if not token:
        return False
    normalized_error = str(error_message or "").strip() or None
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        if success:
            cursor = conn.execute(
                """
                UPDATE telegram_products
                SET shafa_deactivated_at = COALESCE(
                        shafa_deactivated_at,
                        datetime('now')
                    ),
                    last_shafa_deactivate_error = NULL,
                    deactivation_status = ?,
                    deactivation_processing_started_at = NULL,
                    deactivation_processing_token = NULL,
                    deactivation_processing_expires_at = NULL,
                    deactivation_failed_at = NULL,
                    deactivation_error = NULL,
                    deactivation_completed_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE account_id = ?
                  AND channel_id = ?
                  AND message_id = ?
                  AND deactivation_processing_token = ?
                """,
                (
                    TELEGRAM_DEACTIVATION_STATUS_COMPLETED,
                    normalized_account_id,
                    channel_id,
                    message_id,
                    token,
                ),
            )
            return cursor.rowcount == 1
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET shafa_deactivate_attempts = COALESCE(shafa_deactivate_attempts, 0) + 1,
                last_shafa_deactivate_error = ?,
                deactivation_status = ?,
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_retry_count = COALESCE(deactivation_retry_count, 0) + 1,
                deactivation_failed_at = datetime('now'),
                deactivation_error = ?,
                updated_at = datetime('now')
            WHERE account_id = ?
              AND channel_id = ?
              AND message_id = ?
              AND deactivation_processing_token = ?
            """,
            (
                normalized_error,
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
                normalized_error,
                normalized_account_id,
                channel_id,
                message_id,
                token,
            ),
        )
    return cursor.rowcount == 1


def skip_telegram_product_deactivation_not_found(
    channel_id: int,
    message_id: int,
    lease_token: str,
    *,
    account_id: Optional[str] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    token = str(lease_token or "").strip()
    if not token:
        return False
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET shafa_deleted_at = COALESCE(shafa_deleted_at, datetime('now')),
                last_shafa_deactivate_error = NULL,
                deactivation_status = ?,
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_failed_at = NULL,
                deactivation_error = NULL,
                deactivation_completed_at = datetime('now'),
                deactivation_check_status = ?,
                deactivation_last_checked_at = datetime('now'),
                deactivation_next_check_at = NULL,
                updated_at = datetime('now')
            WHERE account_id = ?
              AND channel_id = ?
              AND message_id = ?
              AND deactivation_processing_token = ?
            """,
            (
                TELEGRAM_DEACTIVATION_STATUS_SKIPPED_NOT_FOUND,
                TELEGRAM_DEACTIVATION_CHECK_OLD,
                normalized_account_id,
                channel_id,
                message_id,
                token,
            ),
        )
    return cursor.rowcount == 1


def mark_telegram_product_deactivated_on_shafa(
    channel_id: int,
    message_id: int,
    *,
    account_id: Optional[str] = None,
) -> None:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            UPDATE telegram_products
            SET shafa_deactivated_at = datetime('now'),
                last_shafa_deactivate_error = NULL,
                deactivation_status = ?,
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_failed_at = NULL,
                deactivation_error = NULL,
                deactivation_completed_at = datetime('now'),
                deactivation_check_status = ?,
                deactivation_last_checked_at = datetime('now'),
                deactivation_next_check_at = NULL,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                TELEGRAM_DEACTIVATION_STATUS_COMPLETED,
                TELEGRAM_DEACTIVATION_CHECK_OLD,
                normalized_account_id,
                channel_id,
                message_id,
            ),
        )


def mark_telegram_product_not_found_on_shafa(
    channel_id: int,
    message_id: int,
    *,
    account_id: Optional[str] = None,
) -> bool:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET shafa_deleted_at = COALESCE(shafa_deleted_at, datetime('now')),
                last_shafa_deactivate_error = NULL,
                deactivation_status = ?,
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_failed_at = NULL,
                deactivation_error = NULL,
                deactivation_completed_at = datetime('now'),
                deactivation_check_status = ?,
                deactivation_last_checked_at = datetime('now'),
                deactivation_next_check_at = NULL,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                TELEGRAM_DEACTIVATION_STATUS_SKIPPED_NOT_FOUND,
                TELEGRAM_DEACTIVATION_CHECK_OLD,
                normalized_account_id,
                channel_id,
                message_id,
            ),
        )
    return cursor.rowcount == 1


def record_telegram_product_shafa_deactivate_failure(
    channel_id: int,
    message_id: int,
    error_message: Optional[str],
    *,
    account_id: Optional[str] = None,
) -> int:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    normalized_error = str(error_message or "").strip() or None
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            UPDATE telegram_products
            SET shafa_deactivate_attempts = COALESCE(shafa_deactivate_attempts, 0) + 1,
                last_shafa_deactivate_error = ?,
                deactivation_status = ?,
                deactivation_processing_started_at = NULL,
                deactivation_processing_token = NULL,
                deactivation_processing_expires_at = NULL,
                deactivation_retry_count = COALESCE(deactivation_retry_count, 0) + 1,
                deactivation_failed_at = datetime('now'),
                deactivation_error = ?,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                normalized_error,
                TELEGRAM_DEACTIVATION_STATUS_FAILED,
                normalized_error,
                normalized_account_id,
                channel_id,
                message_id,
            ),
        )
        row = conn.execute(
            """
            SELECT COALESCE(shafa_deactivate_attempts, 0) AS shafa_deactivate_attempts
            FROM telegram_products
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (normalized_account_id, channel_id, message_id),
        ).fetchone()
    return int(row["shafa_deactivate_attempts"] or 0) if row else 0


def mark_telegram_product_deleted_from_shafa(
    channel_id: int,
    message_id: int,
    *,
    account_id: Optional[str] = None,
) -> None:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            UPDATE telegram_products
            SET shafa_deleted_at = datetime('now'),
                last_shafa_delete_error = NULL,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (normalized_account_id, channel_id, message_id),
        )


def record_telegram_product_shafa_delete_failure(
    channel_id: int,
    message_id: int,
    error_message: Optional[str],
    *,
    account_id: Optional[str] = None,
) -> int:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    normalized_error = str(error_message or "").strip() or None
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            UPDATE telegram_products
            SET shafa_delete_attempts = COALESCE(shafa_delete_attempts, 0) + 1,
                last_shafa_delete_error = ?,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                normalized_error,
                normalized_account_id,
                channel_id,
                message_id,
            ),
        )
        row = conn.execute(
            """
            SELECT COALESCE(shafa_delete_attempts, 0) AS shafa_delete_attempts
            FROM telegram_products
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (normalized_account_id, channel_id, message_id),
        ).fetchone()
    return int(row["shafa_delete_attempts"] or 0) if row else 0


def increment_telegram_product_attempt(
    channel_id: int,
    message_id: int,
    failure_reason: Optional[str] = None,
    *,
    account_id: Optional[str] = None,
) -> int:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    normalized_reason = str(failure_reason or "").strip() or None
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            UPDATE telegram_products
            SET status = ?,
                created = 0,
                created_product_id = NULL,
                create_attempts = COALESCE(create_attempts, 0) + 1,
                last_create_error = ?,
                updated_at = datetime('now'),
                status_updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                TELEGRAM_PRODUCT_STATUS_FAILED,
                normalized_reason,
                normalized_account_id,
                channel_id,
                message_id,
            ),
        )
        row = conn.execute(
            """
            SELECT COALESCE(create_attempts, 0) AS create_attempts
            FROM telegram_products
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (normalized_account_id, channel_id, message_id),
        ).fetchone()
    if not row:
        return 0
    return int(row["create_attempts"] or 0)


def reset_telegram_products_created(
    channel_id: Optional[int] = None,
    *,
    account_id: Optional[str] = None,
) -> int:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    if channel_id is None:
        where_clause = (
            "account_id = ? AND ("
            "status != ? OR created != 0 OR created_product_id IS NOT NULL "
            "OR COALESCE(create_attempts, 0) != 0 OR last_create_error IS NOT NULL"
            ")"
        )
        params: tuple[object, ...] = (
            normalized_account_id,
            TELEGRAM_PRODUCT_STATUS_QUEUED,
        )
    else:
        where_clause = (
            "account_id = ? AND ("
            "status != ? OR created != 0 OR created_product_id IS NOT NULL "
            "OR COALESCE(create_attempts, 0) != 0 OR last_create_error IS NOT NULL"
            ") AND channel_id = ?"
        )
        params = (
            normalized_account_id,
            TELEGRAM_PRODUCT_STATUS_QUEUED,
            channel_id,
        )
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            f"""
            UPDATE telegram_products
            SET status = ?,
                created = 0,
                created_product_id = NULL,
                create_attempts = 0,
                last_create_error = NULL,
                updated_at = datetime('now'),
                status_updated_at = datetime('now')
            WHERE {where_clause}
            """,
            (TELEGRAM_PRODUCT_STATUS_QUEUED, *params),
        )
    return cursor.rowcount


def telegram_products_exist(*, account_id: Optional[str] = None) -> bool:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM telegram_products
            WHERE account_id = ?
            LIMIT 1
            """,
            (normalized_account_id,),
        ).fetchone()
    return row is not None


def get_telegram_scan_cursor(
    channel_id: int,
    *,
    account_id: Optional[str] = None,
) -> dict:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        row = conn.execute(
            """
            SELECT
                account_id,
                channel_id,
                last_checked_message_id,
                backfill_before_message_id,
                backfill_history_limit_reached,
                backfill_history_window_days,
                backfill_history_limit_reached_at,
                last_scan_started_at,
                last_scan_finished_at,
                last_scan_error,
                backfill_scan_started_at,
                backfill_scan_finished_at,
                backfill_scan_error,
                updated_at
            FROM telegram_scan_cursors
            WHERE account_id = ? AND channel_id = ?
            """,
            (normalized_account_id, channel_id),
        ).fetchone()
    return {
        "account_id": normalized_account_id,
        "channel_id": channel_id,
        "last_checked_message_id": (
            int(row["last_checked_message_id"])
            if row and row["last_checked_message_id"] is not None
            else None
        ),
        "backfill_before_message_id": (
            int(row["backfill_before_message_id"])
            if row and row["backfill_before_message_id"] is not None
            else None
        ),
        "backfill_history_limit_reached": bool(
            row["backfill_history_limit_reached"]
        ) if row and row["backfill_history_limit_reached"] is not None else False,
        "backfill_history_window_days": (
            int(row["backfill_history_window_days"])
            if row and row["backfill_history_window_days"] is not None
            else None
        ),
        "backfill_history_limit_reached_at": (
            row["backfill_history_limit_reached_at"] if row else None
        ),
        "last_scan_started_at": row["last_scan_started_at"] if row else None,
        "last_scan_finished_at": row["last_scan_finished_at"] if row else None,
        "last_scan_error": row["last_scan_error"] if row else None,
        "backfill_scan_started_at": (
            row["backfill_scan_started_at"] if row else None
        ),
        "backfill_scan_finished_at": (
            row["backfill_scan_finished_at"] if row else None
        ),
        "backfill_scan_error": row["backfill_scan_error"] if row else None,
        "updated_at": row["updated_at"] if row else None,
    }


def mark_telegram_scan_started(
    channel_id: int,
    *,
    account_id: Optional[str] = None,
) -> None:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            INSERT INTO telegram_scan_cursors (
                account_id,
                channel_id,
                last_scan_started_at,
                last_scan_error,
                updated_at
            )
            VALUES (?, ?, datetime('now'), NULL, datetime('now'))
            ON CONFLICT(account_id, channel_id) DO UPDATE SET
                last_scan_started_at = datetime('now'),
                last_scan_error = NULL,
                updated_at = datetime('now')
            """,
            (normalized_account_id, channel_id),
        )


def mark_telegram_backfill_started(
    channel_id: int,
    *,
    account_id: Optional[str] = None,
) -> None:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            INSERT INTO telegram_scan_cursors (
                account_id,
                channel_id,
                backfill_scan_started_at,
                backfill_scan_error,
                updated_at
            )
            VALUES (?, ?, datetime('now'), NULL, datetime('now'))
            ON CONFLICT(account_id, channel_id) DO UPDATE SET
                backfill_scan_started_at = datetime('now'),
                backfill_scan_error = NULL,
                updated_at = datetime('now')
            """,
            (normalized_account_id, channel_id),
        )


def finish_telegram_scan(
    channel_id: int,
    *,
    last_checked_message_id: Optional[int],
    account_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        existing = conn.execute(
            """
            SELECT last_checked_message_id
            FROM telegram_scan_cursors
            WHERE account_id = ? AND channel_id = ?
            """,
            (normalized_account_id, channel_id),
        ).fetchone()
        current_last_checked = (
            int(existing["last_checked_message_id"])
            if existing and existing["last_checked_message_id"] is not None
            else None
        )
        next_last_checked = current_last_checked
        if last_checked_message_id is not None:
            processed_message_id = int(last_checked_message_id)
            if next_last_checked is None or processed_message_id > next_last_checked:
                next_last_checked = processed_message_id
        conn.execute(
            """
            INSERT INTO telegram_scan_cursors (
                account_id,
                channel_id,
                last_checked_message_id,
                last_scan_finished_at,
                last_scan_error,
                updated_at
            )
            VALUES (?, ?, ?, datetime('now'), ?, datetime('now'))
            ON CONFLICT(account_id, channel_id) DO UPDATE SET
                last_checked_message_id = excluded.last_checked_message_id,
                last_scan_finished_at = datetime('now'),
                last_scan_error = excluded.last_scan_error,
                updated_at = datetime('now')
            """,
            (
                normalized_account_id,
                channel_id,
                next_last_checked,
                str(error_message).strip() or None,
            ),
        )


def finish_telegram_backfill(
    channel_id: int,
    *,
    backfill_before_message_id: Optional[int],
    account_id: Optional[str] = None,
    error_message: Optional[str] = None,
    history_limit_reached: Optional[bool] = None,
    history_window_days: Optional[int] = None,
) -> None:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        existing = conn.execute(
            """
            SELECT
                backfill_before_message_id,
                backfill_history_limit_reached,
                backfill_history_window_days,
                backfill_history_limit_reached_at
            FROM telegram_scan_cursors
            WHERE account_id = ? AND channel_id = ?
            """,
            (normalized_account_id, channel_id),
        ).fetchone()
        current_backfill_before = (
            int(existing["backfill_before_message_id"])
            if existing and existing["backfill_before_message_id"] is not None
            else None
        )
        next_backfill_before = current_backfill_before
        if backfill_before_message_id is not None:
            processed_message_id = int(backfill_before_message_id)
            if next_backfill_before is None or processed_message_id < next_backfill_before:
                next_backfill_before = processed_message_id
        next_history_limit_reached = (
            bool(existing["backfill_history_limit_reached"])
            if existing and existing["backfill_history_limit_reached"] is not None
            else False
        )
        if history_limit_reached is not None:
            next_history_limit_reached = bool(history_limit_reached)
        next_history_window_days = (
            int(existing["backfill_history_window_days"])
            if existing and existing["backfill_history_window_days"] is not None
            else None
        )
        if history_window_days is not None:
            next_history_window_days = int(history_window_days)
        next_history_limit_reached_at = (
            str(existing["backfill_history_limit_reached_at"])
            if existing and existing["backfill_history_limit_reached_at"] is not None
            else None
        )
        if history_limit_reached is True:
            next_history_limit_reached_at = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.gmtime(),
            )
        elif history_limit_reached is False:
            next_history_limit_reached_at = None
        conn.execute(
            """
            INSERT INTO telegram_scan_cursors (
                account_id,
                channel_id,
                backfill_before_message_id,
                backfill_history_limit_reached,
                backfill_history_window_days,
                backfill_history_limit_reached_at,
                backfill_scan_finished_at,
                backfill_scan_error,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
            ON CONFLICT(account_id, channel_id) DO UPDATE SET
                backfill_before_message_id = excluded.backfill_before_message_id,
                backfill_history_limit_reached = excluded.backfill_history_limit_reached,
                backfill_history_window_days = excluded.backfill_history_window_days,
                backfill_history_limit_reached_at = excluded.backfill_history_limit_reached_at,
                backfill_scan_finished_at = datetime('now'),
                backfill_scan_error = excluded.backfill_scan_error,
                updated_at = datetime('now')
            """,
            (
                normalized_account_id,
                channel_id,
                next_backfill_before,
                1 if next_history_limit_reached else 0,
                next_history_window_days,
                next_history_limit_reached_at,
                str(error_message).strip() or None,
            ),
        )


def _normalize_telegram_fetch_scope(scope: str) -> str:
    text = str(scope or "").strip().casefold()
    return text or "default"


def claim_telegram_fetch(
    scope: str,
    min_interval_seconds: float,
    lease_seconds: float,
    *,
    now_ts: Optional[float] = None,
) -> tuple[str, Optional[str]]:
    normalized_scope = _normalize_telegram_fetch_scope(scope)
    interval_seconds = max(float(min_interval_seconds), 0.0)
    lease_duration_seconds = max(float(lease_seconds), 1.0)
    current_ts = float(now_ts if now_ts is not None else time.time())
    due_before_ts = current_ts - interval_seconds
    lease_expires_at = current_ts + lease_duration_seconds
    lease_token = uuid.uuid4().hex
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            INSERT INTO telegram_fetch_state (scope, updated_at)
            VALUES (?, datetime('now'))
            ON CONFLICT(scope) DO NOTHING
            """,
            (normalized_scope,),
        )
        cursor = conn.execute(
            """
            UPDATE telegram_fetch_state
            SET lease_expires_at = ?,
                lease_token = ?,
                updated_at = datetime('now')
            WHERE scope = ?
              AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
              AND (last_fetch_at IS NULL OR last_fetch_at <= ?)
            """,
            (
                lease_expires_at,
                lease_token,
                normalized_scope,
                current_ts,
                due_before_ts,
            ),
        )
        if cursor.rowcount == 1:
            return "acquired", lease_token
        row = conn.execute(
            """
            SELECT last_fetch_at, lease_expires_at
            FROM telegram_fetch_state
            WHERE scope = ?
            """,
            (normalized_scope,),
        ).fetchone()
    if row and row["lease_expires_at"] is not None and float(row["lease_expires_at"]) > current_ts:
        return "in_progress", None
    return "not_due", None


def finish_telegram_fetch(
    scope: str,
    lease_token: str,
    *,
    success: bool,
    finished_at_ts: Optional[float] = None,
) -> None:
    normalized_scope = _normalize_telegram_fetch_scope(scope)
    token = str(lease_token or "").strip()
    if not token:
        return
    finished_ts = float(finished_at_ts if finished_at_ts is not None else time.time())
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        if success:
            conn.execute(
                """
                UPDATE telegram_fetch_state
                SET last_fetch_at = ?,
                    lease_expires_at = NULL,
                    lease_token = NULL,
                    updated_at = datetime('now')
                WHERE scope = ? AND lease_token = ?
                """,
                (finished_ts, normalized_scope, token),
            )
            return
        conn.execute(
            """
            UPDATE telegram_fetch_state
            SET lease_expires_at = NULL,
                lease_token = NULL,
                updated_at = datetime('now')
            WHERE scope = ? AND lease_token = ?
            """,
            (normalized_scope, token),
        )


def save_cookies(cookies: list[dict]) -> None:
    if not cookies:
        return
    _ensure_db_initialized()
    with _connect() as conn:
        _cleanup_non_shafa_cookies(conn, allow_subdomains=True)
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            domain = cookie.get("domain")
            if not domain or not _is_allowed_cookie_domain(
                domain, allow_subdomains=True
            ):
                continue
            if not name or value is None or not domain:
                continue
            path = cookie.get("path") or "/"
            conn.execute(
                """
                INSERT INTO cookies
                    (domain, name, value, path, expires, http_only, secure, same_site)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain, name, path)
                DO UPDATE SET
                    value = excluded.value,
                    expires = excluded.expires,
                    http_only = excluded.http_only,
                    secure = excluded.secure,
                    same_site = excluded.same_site,
                    last_updated = datetime('now')
                """,
                (
                    domain,
                    name,
                    value,
                    path,
                    cookie.get("expires"),
                    1 if cookie.get("httpOnly") else 0,
                    1 if cookie.get("secure") else 0,
                    cookie.get("sameSite"),
                ),
            )


def load_cookies(
    domain: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    resolved_db_path = Path(db_path) if db_path is not None else _account_db_path()
    _ensure_db_initialized(resolved_db_path)
    with _connect(resolved_db_path) as conn:
        if domain:
            normalized = _normalize_domain(domain)
            rows = conn.execute(
                """
                SELECT domain, name, value, path, expires, http_only, secure, same_site
                FROM cookies
                WHERE domain IN (?, ?)
                """,
                (normalized, f".{normalized}"),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT domain, name, value, path, expires, http_only, secure, same_site
                FROM cookies
                """
            ).fetchall()

    cookies: list[dict] = []
    for row in rows:
        if not row["domain"] or not row["name"]:
            continue
        cookie = {
            "name": row["name"],
            "value": row["value"],
            "domain": row["domain"],
            "path": row["path"] or "/",
            "httpOnly": bool(row["http_only"]),
            "secure": bool(row["secure"]),
        }
        if row["expires"] is not None:
            cookie["expires"] = row["expires"]
        if row["same_site"]:
            cookie["sameSite"] = row["same_site"]
        cookies.append(cookie)
    return cookies


def delete_all_cookies() -> int:
    _ensure_db_initialized()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM cookies").fetchone()
        count = int(row["count"]) if row else 0
        conn.execute("DELETE FROM cookies")
    return count


def cleanup_cookies(allow_subdomains: bool = True) -> int:
    _ensure_db_initialized()
    with _connect() as conn:
        return _cleanup_non_shafa_cookies(conn, allow_subdomains=allow_subdomains)


def _is_allowed_cookie_domain(domain: str, allow_subdomains: bool) -> bool:
    normalized = _normalize_domain(domain).lower()
    base = _COOKIE_BASE_DOMAIN.lower()
    if allow_subdomains:
        return normalized == base or normalized.endswith(f".{base}")
    return normalized == base


def _cleanup_non_shafa_cookies(
    conn: sqlite3.Connection,
    allow_subdomains: bool,
) -> int:
    rows = conn.execute("SELECT id, domain FROM cookies").fetchall()
    to_delete = []
    for row in rows:
        if not _is_allowed_cookie_domain(
            row["domain"], allow_subdomains=allow_subdomains
        ):
            to_delete.append((row["id"],))
    if to_delete:
        conn.executemany("DELETE FROM cookies WHERE id = ?", to_delete)
    return len(to_delete)


def _normalize_domain(domain: str) -> str:
    domain = domain.strip()
    if "://" in domain:
        parsed = urlparse(domain)
        if parsed.hostname:
            domain = parsed.hostname
    return domain.lstrip(".")
