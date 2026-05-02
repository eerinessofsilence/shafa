import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import re

from data.const import DB_PATH, TELEGRAM_PRODUCTS_DB_PATH
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

            CREATE TABLE IF NOT EXISTS telegram_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                raw_message TEXT,
                parsed_data TEXT,
                created INTEGER NOT NULL DEFAULT 0,
                created_product_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(channel_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_telegram_products_created
                ON telegram_products(created);
            CREATE INDEX IF NOT EXISTS idx_telegram_products_channel
                ON telegram_products(channel_id);

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
        _ensure_uploaded_products_schema(conn)
        _ensure_telegram_products_schema(conn)
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


def _ensure_telegram_products_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(telegram_products)").fetchall()
    }
    if "create_attempts" not in columns:
        conn.execute(
            "ALTER TABLE telegram_products ADD COLUMN create_attempts "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "last_create_error" not in columns:
        conn.execute("ALTER TABLE telegram_products ADD COLUMN last_create_error TEXT")


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


def mark_uploaded_products_deactivated(product_ids: list[int]) -> int:
    if not product_ids:
        return 0
    normalized_ids = [str(pid).strip() for pid in product_ids if str(pid).strip()]
    if not normalized_ids:
        return 0
    _ensure_db_initialized()
    placeholders = ",".join(["?"] * len(normalized_ids))
    with _connect() as conn:
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


def save_telegram_product(
    channel_id: int,
    message_id: int,
    raw_message: str,
    parsed_data: dict,
) -> bool:
    size = parsed_data.get("size")
    if size is None or str(size).strip() == "":
        return False
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO telegram_products
                (channel_id, message_id, raw_message, parsed_data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(channel_id, message_id) DO NOTHING
            """,
            (
                channel_id,
                message_id,
                raw_message,
                json.dumps(parsed_data, ensure_ascii=True),
            ),
        )
    return cursor.rowcount == 1


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
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        try:
            conn.execute(
                """
                UPDATE telegram_products
                SET channel_id = ?, updated_at = datetime('now')
                WHERE channel_id = ?
                """,
                (new_channel_id, old_channel_id),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return False
    return True


def get_next_uncreated_telegram_product(channel_id: int) -> Optional[sqlite3.Row]:
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        return conn.execute(
            """
            SELECT *
            FROM telegram_products
            WHERE channel_id = ? AND created = 0
            ORDER BY message_id DESC
            LIMIT 1
            """,
            (channel_id,),
        ).fetchone()


def mark_telegram_product_created(
    channel_id: int,
    message_id: int,
    created_product_id: Optional[str] = None,
) -> None:
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            UPDATE telegram_products
            SET created = 1,
                created_product_id = ?,
                updated_at = datetime('now')
            WHERE channel_id = ? AND message_id = ?
            """,
            (created_product_id, channel_id, message_id),
        )


def increment_telegram_product_attempt(
    channel_id: int,
    message_id: int,
    failure_reason: Optional[str] = None,
) -> int:
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    normalized_reason = str(failure_reason or "").strip() or None
    with _connect(telegram_db_path) as conn:
        conn.execute(
            """
            UPDATE telegram_products
            SET create_attempts = COALESCE(create_attempts, 0) + 1,
                last_create_error = ?,
                updated_at = datetime('now')
            WHERE channel_id = ? AND message_id = ?
            """,
            (normalized_reason, channel_id, message_id),
        )
        row = conn.execute(
            """
            SELECT COALESCE(create_attempts, 0) AS create_attempts
            FROM telegram_products
            WHERE channel_id = ? AND message_id = ?
            """,
            (channel_id, message_id),
        ).fetchone()
    if not row:
        return 0
    return int(row["create_attempts"] or 0)


def reset_telegram_products_created(channel_id: Optional[int] = None) -> int:
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    if channel_id is None:
        where_clause = (
            "created != 0 OR created_product_id IS NOT NULL "
            "OR COALESCE(create_attempts, 0) != 0 OR last_create_error IS NOT NULL"
        )
        params: tuple[object, ...] = ()
    else:
        where_clause = (
            "("
            "created != 0 OR created_product_id IS NOT NULL "
            "OR COALESCE(create_attempts, 0) != 0 OR last_create_error IS NOT NULL"
            ") AND channel_id = ?"
        )
        params = (channel_id,)
    with _connect(telegram_db_path) as conn:
        cursor = conn.execute(
            f"""
            UPDATE telegram_products
            SET created = 0,
                created_product_id = NULL,
                create_attempts = 0,
                last_create_error = NULL,
                updated_at = datetime('now')
            WHERE {where_clause}
            """,
            params,
        )
    return cursor.rowcount


def telegram_products_exist() -> bool:
    telegram_db_path = _telegram_products_db_path()
    _ensure_db_initialized(telegram_db_path)
    with _connect(telegram_db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM telegram_products
            LIMIT 1
            """
        ).fetchone()
    return row is not None


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


def load_cookies(domain: Optional[str] = None) -> list[dict]:
    _ensure_db_initialized()
    with _connect() as conn:
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
