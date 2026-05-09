import json
import os
import sqlite3
import time
import uuid
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
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            status_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            create_attempts INTEGER NOT NULL DEFAULT 0,
            last_create_error TEXT,
            UNIQUE(account_id, channel_id, message_id)
        )
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


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(
        db_path,
        timeout=_sqlite_timeout_seconds(),
        factory=_RetryingConnection,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {_sqlite_busy_timeout_ms()}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    global _DB_INITIALIZED_PATHS
    db_path = Path(db_path)
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


def _ensure_db_initialized(db_path: Path = DB_PATH) -> None:
    db_path = Path(db_path)
    if db_path in _DB_INITIALIZED_PATHS:
        return
    init_db(db_path)


def _telegram_products_db_path() -> Path:
    return Path(TELEGRAM_PRODUCTS_DB_PATH)


def _normalize_catalog_slug(catalog_slug: Optional[str]) -> Optional[str]:
    if catalog_slug is None:
        return None
    text = str(catalog_slug).strip()
    if not text:
        return None
    return text.casefold()


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
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(uploaded_products)").fetchall()
    }
    if "is_active" not in columns:
        conn.execute(
            "ALTER TABLE uploaded_products ADD COLUMN is_active "
            "INTEGER NOT NULL DEFAULT 1"
        )


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
    created_at_source = "created_at" if "created_at" in columns else "NULL"
    updated_at_source = "updated_at" if "updated_at" in columns else "NULL"
    status_updated_at_source = (
        "status_updated_at" if "status_updated_at" in columns else "NULL"
    )
    last_create_error_expr = (
        "last_create_error" if "last_create_error" in columns else "NULL"
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
            created_at,
            updated_at,
            status_updated_at,
            create_attempts,
            last_create_error
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
            COALESCE({created_at_source}, datetime('now')),
            COALESCE({updated_at_source}, {created_at_source}, datetime('now')),
            COALESCE(
                {status_updated_at_source},
                {updated_at_source},
                {created_at_source},
                datetime('now')
            ),
            {create_attempts_expr},
            {last_create_error_expr}
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


def list_uploaded_products(limit: int = 20) -> list[dict]:
    _ensure_db_initialized()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT product_id, name, created_at
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


def mark_uploaded_products_deactivated(
    product_ids: list[int],
    db_path: Path = DB_PATH,
) -> int:
    if not product_ids:
        return 0
    normalized_ids = [str(pid).strip() for pid in product_ids if str(pid).strip()]
    if not normalized_ids:
        return 0
    _ensure_db_initialized(db_path)
    placeholders = ",".join(["?"] * len(normalized_ids))
    with _connect(db_path) as conn:
        cursor = conn.execute(
            f"""
            UPDATE uploaded_products
            SET is_active = 0
            WHERE product_id IN ({placeholders})
            """,
            normalized_ids,
        )
    return cursor.rowcount


def list_uploaded_product_payloads(limit: Optional[int] = None) -> list[dict]:
    _ensure_db_initialized()
    with _connect() as conn:
        if limit is None:
            rows = conn.execute(
                """
                SELECT id, product_id, name, photo_ids, raw_payload, created_at
                FROM uploaded_products
                WHERE raw_payload IS NOT NULL AND TRIM(raw_payload) != ''
                ORDER BY id
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, product_id, name, photo_ids, raw_payload, created_at
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


def list_active_uploaded_product_payloads(
    limit: Optional[int] = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    _ensure_db_initialized(db_path)
    with _connect(db_path) as conn:
        if limit is None:
            rows = conn.execute(
                """
                SELECT id, product_id, name, photo_ids, raw_payload, created_at
                FROM uploaded_products
                WHERE product_id IS NOT NULL AND TRIM(product_id) != ''
                  AND COALESCE(is_active, 1) = 1
                ORDER BY created_at DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, product_id, name, photo_ids, raw_payload, created_at
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
            "id": row["id"],
            "product_id": row["product_id"],
            "name": row["name"],
            "photo_ids": row["photo_ids"],
            "raw_payload": row["raw_payload"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_invalid_uploaded_product(
    product_id: Optional[str],
    name: str,
    invalid_reason: str,
    *,
    raw_payload: Optional[str] = None,
    created_at: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> None:
    normalized_product_id = str(product_id or "").strip() or None
    normalized_name = str(name or "").strip()
    normalized_reason = str(invalid_reason or "").strip()
    if not normalized_product_id or not normalized_name or not normalized_reason:
        return
    _ensure_db_initialized(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO invalid_uploaded_products (
                product_id,
                name,
                invalid_reason,
                raw_payload,
                created_at,
                detected_at,
                processed,
                processed_at,
                last_error
            )
            VALUES (?, ?, ?, ?, ?, datetime('now'), 0, NULL, NULL)
            ON CONFLICT(product_id) DO UPDATE SET
                name = excluded.name,
                invalid_reason = excluded.invalid_reason,
                raw_payload = excluded.raw_payload,
                created_at = COALESCE(excluded.created_at, invalid_uploaded_products.created_at),
                detected_at = datetime('now'),
                processed = 0,
                processed_at = NULL,
                last_error = NULL
            """,
            (
                normalized_product_id,
                normalized_name,
                normalized_reason,
                raw_payload,
                created_at,
            ),
        )


def list_pending_invalid_uploaded_products(
    limit: Optional[int] = None,
    *,
    db_path: Path = DB_PATH,
) -> list[dict]:
    _ensure_db_initialized(db_path)
    with _connect(db_path) as conn:
        if limit is None:
            rows = conn.execute(
                """
                SELECT id, product_id, name, invalid_reason, raw_payload, created_at, detected_at
                FROM invalid_uploaded_products
                WHERE processed = 0
                ORDER BY detected_at DESC, id DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, product_id, name, invalid_reason, raw_payload, created_at, detected_at
                FROM invalid_uploaded_products
                WHERE processed = 0
                ORDER BY detected_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [
        {
            "id": row["id"],
            "product_id": row["product_id"],
            "name": row["name"],
            "invalid_reason": row["invalid_reason"],
            "raw_payload": row["raw_payload"],
            "created_at": row["created_at"],
            "detected_at": row["detected_at"],
        }
        for row in rows
    ]


def mark_invalid_uploaded_products_processed(
    product_ids: list[object],
    *,
    db_path: Path = DB_PATH,
    last_error: Optional[str] = None,
) -> int:
    normalized_ids = [str(item).strip() for item in product_ids if str(item).strip()]
    if not normalized_ids:
        return 0
    _ensure_db_initialized(db_path)
    placeholders = ",".join(["?"] * len(normalized_ids))
    with _connect(db_path) as conn:
        cursor = conn.execute(
            f"""
            UPDATE invalid_uploaded_products
            SET processed = 1,
                processed_at = datetime('now'),
                last_error = ?
            WHERE product_id IN ({placeholders})
            """,
            [str(last_error or "").strip() or None, *normalized_ids],
        )
    return cursor.rowcount


def mark_invalid_uploaded_products_error(
    product_ids: list[object],
    *,
    last_error: str,
    db_path: Path = DB_PATH,
) -> int:
    normalized_ids = [str(item).strip() for item in product_ids if str(item).strip()]
    if not normalized_ids:
        return 0
    _ensure_db_initialized(db_path)
    placeholders = ",".join(["?"] * len(normalized_ids))
    with _connect(db_path) as conn:
        cursor = conn.execute(
            f"""
            UPDATE invalid_uploaded_products
            SET last_error = ?,
                processed = 0,
                processed_at = NULL
            WHERE product_id IN ({placeholders})
            """,
            [str(last_error).strip() or None, *normalized_ids],
        )
    return cursor.rowcount


def clear_invalid_uploaded_products(
    product_ids: list[object],
    *,
    db_path: Path = DB_PATH,
) -> int:
    normalized_ids = [str(item).strip() for item in product_ids if str(item).strip()]
    if not normalized_ids:
        return 0
    _ensure_db_initialized(db_path)
    placeholders = ",".join(["?"] * len(normalized_ids))
    with _connect(db_path) as conn:
        cursor = conn.execute(
            f"DELETE FROM invalid_uploaded_products WHERE product_id IN ({placeholders})",
            normalized_ids,
        )
    return cursor.rowcount


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
) -> bool:
    size = parsed_data.get("size")
    if size is None or str(size).strip() == "":
        return False
    normalized_account_id = _current_account_id(account_id)
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
                (account_id, channel_id, message_id, raw_message, parsed_data)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id, channel_id, message_id) DO NOTHING
            """,
            (
                normalized_account_id,
                channel_id,
                message_id,
                raw_message,
                json.dumps(parsed_data, ensure_ascii=True),
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
) -> None:
    normalized_account_id = _current_account_id(account_id)
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        existing = conn.execute(
            """
            SELECT backfill_before_message_id
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
        conn.execute(
            """
            INSERT INTO telegram_scan_cursors (
                account_id,
                channel_id,
                backfill_before_message_id,
                backfill_scan_finished_at,
                backfill_scan_error,
                updated_at
            )
            VALUES (?, ?, ?, datetime('now'), ?, datetime('now'))
            ON CONFLICT(account_id, channel_id) DO UPDATE SET
                backfill_before_message_id = excluded.backfill_before_message_id,
                backfill_scan_finished_at = datetime('now'),
                backfill_scan_error = excluded.backfill_scan_error,
                updated_at = datetime('now')
            """,
            (
                normalized_account_id,
                channel_id,
                next_backfill_before,
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


def load_cookies(domain: Optional[str] = None, db_path: Path = DB_PATH) -> list[dict]:
    _ensure_db_initialized(db_path)
    with _connect(db_path) as conn:
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
