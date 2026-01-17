import json
import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from data.const import DB_PATH

_COOKIE_BASE_DOMAIN = "shafa.ua"


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS sold_products;

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

            CREATE TABLE IF NOT EXISTS sizes (
                id INTEGER PRIMARY KEY,
                primary_size_name TEXT NOT NULL
            );

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
        _ensure_telegram_channels_schema(conn)


def _ensure_telegram_channels_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(telegram_channels)").fetchall()
    }
    if "alias" not in columns:
        conn.execute("ALTER TABLE telegram_channels ADD COLUMN alias TEXT")


def save_uploaded_product(
    product_id: Optional[str],
    product_raw_data: dict,
    photo_ids: list[str],
) -> None:
    size = product_raw_data.get("size")
    if size is None or str(size).strip() == "":
        return
    init_db()
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
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT product_id, name, created_at
            FROM uploaded_products
            WHERE product_id IS NOT NULL AND TRIM(product_id) != ''
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


def list_uploaded_product_payloads(limit: Optional[int] = None) -> list[dict]:
    init_db()
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


def save_sizes(sizes: list[dict]) -> None:
    if not sizes:
        return
    rows: list[tuple[object, str]] = []
    for size in sizes:
        size_id = size.get("id")
        primary_name = size.get("primarySizeName")
        if size_id is None or not primary_name:
            continue
        rows.append((size_id, str(primary_name)))
    if not rows:
        return
    init_db()
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO sizes (id, primary_size_name)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                primary_size_name = excluded.primary_size_name
            """,
            rows,
        )


def save_brands(brands: list[dict]) -> None:
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
    init_db()
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


def get_size_id_by_name(primary_size_name: str) -> Optional[int]:
    name = str(primary_size_name).strip()
    if not name:
        return None
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM sizes
            WHERE primary_size_name = ?
            COLLATE NOCASE
            """,
            (name,),
        ).fetchone()
    return row["id"] if row else None


def size_id_exists(size_id: int) -> bool:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM sizes
            WHERE id = ?
            LIMIT 1
            """,
            (size_id,),
        ).fetchone()
    return bool(row)


def get_brand_id_by_name(brand_name: str) -> Optional[int]:
    name = str(brand_name).strip()
    if not name:
        return None
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM brands
            WHERE name = ?
            COLLATE NOCASE
            """,
            (name,),
        ).fetchone()
    return row["id"] if row else None


def list_brand_names() -> list[str]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM brands
            WHERE name IS NOT NULL AND TRIM(name) != ''
            ORDER BY name
            """
        ).fetchall()
    return [row["name"] for row in rows]


def save_telegram_product(
    channel_id: int,
    message_id: int,
    raw_message: str,
    parsed_data: dict,
) -> bool:
    size = parsed_data.get("size")
    if size is None or str(size).strip() == "":
        return False
    init_db()
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
    init_db()
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
    init_db()
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
    init_db()
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
    init_db()
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
    init_db()
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
    init_db()
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
    init_db()
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
    init_db()
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


def save_cookies(cookies: list[dict]) -> None:
    if not cookies:
        return
    init_db()
    with _connect() as conn:
        _cleanup_non_shafa_cookies(conn, allow_subdomains=True)
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            domain = cookie.get("domain")
            if not domain or not _is_allowed_cookie_domain(domain, allow_subdomains=True):
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
    init_db()
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
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM cookies").fetchone()
        count = int(row["count"]) if row else 0
        conn.execute("DELETE FROM cookies")
    return count


def cleanup_cookies(allow_subdomains: bool = True) -> int:
    init_db()
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
        if not _is_allowed_cookie_domain(row["domain"], allow_subdomains=allow_subdomains):
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
