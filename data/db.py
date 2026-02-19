import json
import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from data.const import DB_PATH

_COOKIE_BASE_DOMAIN = "shafa.ua"
_DB_INITIALIZED = False
_SIZE_ID_BY_NAME_CACHE: Optional[dict[str, int]] = None
_SIZE_ID_BY_NAME_CATALOG_CACHE: Optional[dict[tuple[str, str], int]] = None
_SIZE_IDS_CACHE: Optional[set[int]] = None
_SIZE_IDS_CATALOG_CACHE: Optional[dict[str, set[int]]] = None
_BRAND_ID_BY_NAME_CACHE: Optional[dict[str, int]] = None
_BRAND_NAMES_CACHE: Optional[list[str]] = None


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    global _DB_INITIALIZED
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

            CREATE TABLE IF NOT EXISTS telegram_channels (
                channel_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                alias TEXT
            );

            CREATE TABLE IF NOT EXISTS size_catalogs (
                catalog_slug TEXT NOT NULL,
                size_id INTEGER NOT NULL,
                primary_size_name TEXT NOT NULL,
                PRIMARY KEY (catalog_slug, size_id)
            );
            CREATE INDEX IF NOT EXISTS idx_size_catalogs_name
                ON size_catalogs(catalog_slug, primary_size_name);

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
        _ensure_telegram_channels_schema(conn)
        _ensure_size_catalogs_schema(conn)
    _DB_INITIALIZED = True


def _ensure_db_initialized() -> None:
    if _DB_INITIALIZED:
        return
    init_db()


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
        key = str(name).strip().casefold()
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


def _ensure_telegram_channels_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(telegram_channels)").fetchall()
    }
    if "alias" not in columns:
        conn.execute("ALTER TABLE telegram_channels ADD COLUMN alias TEXT")


def _ensure_size_catalogs_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS size_catalogs (
            catalog_slug TEXT NOT NULL,
            size_id INTEGER NOT NULL,
            primary_size_name TEXT NOT NULL,
            PRIMARY KEY (catalog_slug, size_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_size_catalogs_name "
        "ON size_catalogs(catalog_slug, primary_size_name)"
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


def save_sizes(sizes: list[dict], catalog_slug: Optional[str] = None) -> None:
    global _SIZE_ID_BY_NAME_CACHE, _SIZE_ID_BY_NAME_CATALOG_CACHE
    global _SIZE_IDS_CACHE, _SIZE_IDS_CATALOG_CACHE
    if not sizes:
        return
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    if normalized_catalog_slug is None:
        return
    rows: list[tuple[str, object, str]] = []
    for size in sizes:
        size_id = size.get("id")
        primary_name = size.get("primarySizeName")
        if size_id is None or not primary_name:
            continue
        rows.append((normalized_catalog_slug, size_id, str(primary_name)))
    if not rows:
        return
    _ensure_db_initialized()
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO size_catalogs (catalog_slug, size_id, primary_size_name)
            VALUES (?, ?, ?)
            ON CONFLICT(catalog_slug, size_id) DO UPDATE SET
                primary_size_name = excluded.primary_size_name
            """,
            rows,
        )
    _SIZE_ID_BY_NAME_CACHE = None
    _SIZE_ID_BY_NAME_CATALOG_CACHE = None
    _SIZE_IDS_CACHE = None
    _SIZE_IDS_CATALOG_CACHE = None


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
    name = str(primary_size_name).strip()
    if not name:
        return None
    key = name.casefold()
    mapping, mapping_by_catalog, _, ids_by_catalog = _load_sizes_cache()
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    if normalized_catalog_slug:
        if normalized_catalog_slug in ids_by_catalog:
            return mapping_by_catalog.get((normalized_catalog_slug, key))
    return mapping.get(key)


def size_id_exists(size_id: int, catalog_slug: Optional[str] = None) -> bool:
    _, _, ids, ids_by_catalog = _load_sizes_cache()
    normalized_catalog_slug = _normalize_catalog_slug(catalog_slug)
    if normalized_catalog_slug:
        scoped_ids = ids_by_catalog.get(normalized_catalog_slug)
        if scoped_ids is not None:
            return size_id in scoped_ids
    return size_id in ids


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
    _ensure_db_initialized()
    with _connect() as conn:
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
    rows: list[tuple[int, str, Optional[str]]] = []
    for entry in channels:
        if len(entry) == 2:
            channel_id, name = entry
            alias = None
        else:
            channel_id, name, alias = entry
        text = str(name).strip()
        if not text:
            text = str(channel_id)
        rows.append((int(channel_id), text, alias))
    if not rows:
        return
    _ensure_db_initialized()
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO telegram_channels (channel_id, name, alias)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                name = excluded.name,
                alias = COALESCE(excluded.alias, telegram_channels.alias)
            """,
            rows,
        )


def load_telegram_channels() -> list[dict]:
    _ensure_db_initialized()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT channel_id, name, alias
            FROM telegram_channels
            ORDER BY channel_id
            """
        ).fetchall()
    return [
        {"channel_id": row["channel_id"], "name": row["name"], "alias": row["alias"]}
        for row in rows
    ]


def delete_telegram_channel(channel_id: int) -> None:
    _ensure_db_initialized()
    with _connect() as conn:
        conn.execute(
            """
            DELETE FROM telegram_channels
            WHERE channel_id = ?
            """,
            (channel_id,),
        )


def rename_telegram_channel(channel_id: int, name: str) -> bool:
    text = str(name).strip()
    if not text:
        return False
    _ensure_db_initialized()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE telegram_channels
            SET name = ?
            WHERE channel_id = ?
            """,
            (text, channel_id),
        )
    return cursor.rowcount > 0


def update_telegram_channel_alias(channel_id: int, alias: Optional[str]) -> bool:
    text = str(alias).strip() if alias is not None else ""
    value = text or None
    _ensure_db_initialized()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE telegram_channels
            SET alias = ?
            WHERE channel_id = ?
            """,
            (value, channel_id),
        )
    return cursor.rowcount > 0


def update_telegram_channel_id(old_channel_id: int, new_channel_id: int) -> bool:
    if old_channel_id == new_channel_id:
        return False
    _ensure_db_initialized()
    with _connect() as conn:
        try:
            cursor = conn.execute(
                """
                UPDATE telegram_channels
                SET channel_id = ?
                WHERE channel_id = ?
                """,
                (new_channel_id, old_channel_id),
            )
            if cursor.rowcount <= 0:
                return False
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
    _ensure_db_initialized()
    with _connect() as conn:
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
    _ensure_db_initialized()
    with _connect() as conn:
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


def reset_telegram_products_created(channel_id: Optional[int] = None) -> int:
    _ensure_db_initialized()
    if channel_id is None:
        where_clause = "created != 0 OR created_product_id IS NOT NULL"
        params: tuple[object, ...] = ()
    else:
        where_clause = (
            "(created != 0 OR created_product_id IS NOT NULL) AND channel_id = ?"
        )
        params = (channel_id,)
    with _connect() as conn:
        cursor = conn.execute(
            f"""
            UPDATE telegram_products
            SET created = 0,
                created_product_id = NULL,
                updated_at = datetime('now')
            WHERE {where_clause}
            """,
            params,
        )
    return cursor.rowcount


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
