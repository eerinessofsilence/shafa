import argparse
import asyncio
import concurrent.futures
import multiprocessing
import queue
from contextlib import redirect_stdout
from io import StringIO
import json
import os
import random
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from deactivate_products_by_date import (
    AccountSession,
    _apply_account_environment as _apply_deactivation_account_environment,
    _clamped_workers,
    _print_account_header,
    _session_from_data,
    _session_to_data,
    configure_account_environment,
    filter_excluded_sessions,
    find_all_accounts_dirs,
    list_account_sessions,
    parse_cli_date,
)


HALF_YEAR_DAYS = 183
DEFAULT_PRODUCT_TYPES = ("INACTIVE",)
PRODUCT_TYPE_ALIASES = {
    "DEACTIVATED": "INACTIVE",
}
DEFAULT_TELEGRAM_DATE_BACKFILL_LIMIT = 100000
DEFAULT_TELEGRAM_DATE_BACKFILL_BATCH_SIZE = 50
DEFAULT_ACTIVATION_SLEEP_MIN_SECONDS = 8.0
DEFAULT_ACTIVATION_SLEEP_MAX_SECONDS = 15.0
DEFAULT_MAX_ACCOUNT_WORKERS = 5
SCRIPT_ROOT = Path(__file__).resolve().parent
ACTIVATION_CHECK_STATUS_ELIGIBLE = "eligible_for_activation"
ACTIVATION_CHECK_STATUS_TOO_OLD = "too_old_for_activation"
ACTIVATION_CHECK_STATUS_MISSING_DATE = "missing_telegram_message_date"
ACTIVATION_CHECK_STATUS_FUTURE_DATE = "future_telegram_message_date"
ACTIVATION_CHECK_STATUS_UNTRUSTED_AGE = "untrusted_age_source"
ACTIVATION_CHECK_STATUS_ACTIVATED = "activated_on_shafa"
ACTIVATION_CHECK_STATUS_FAILED = "activation_failed"
ACTIVATION_CHECK_COLUMNS = {
    "activation_check_status": "TEXT",
    "activation_last_checked_at": "TEXT",
    "activation_checked_age_source": "TEXT",
    "activation_checked_telegram_message_date": "TEXT",
}


@dataclass(frozen=True)
class ActivationCandidate:
    product_id: str
    name: str
    telegram_date: date
    telegram_age_days: int
    product_type: str = ""
    status_title: str = ""
    price: object = None
    url: str = ""
    channel_id: Optional[int] = None
    message_id: Optional[int] = None
    age_source: str = "telegram_message_date"


def _ensure_shafa_logic_on_path() -> None:
    shafa_logic_dir = SCRIPT_ROOT / "shafa_logic"
    if shafa_logic_dir.is_dir():
        text_path = str(shafa_logic_dir)
        if text_path not in sys.path:
            sys.path.insert(0, text_path)


def _default_shared_telegram_db_path(
    selected: Optional[AccountSession] = None,
) -> Path:
    if selected is not None:
        accounts_dir = selected.accounts_dir or selected.state_dir.parent
        return accounts_dir.parent / "telegram_shared" / "telegram_feed.sqlite3"
    return SCRIPT_ROOT / "telegram_shared" / "telegram_feed.sqlite3"


def _apply_account_environment(selected: AccountSession) -> None:
    explicit_shared_db_path = str(
        os.getenv("SHAFA_SHARED_TELEGRAM_DB_PATH") or ""
    ).strip()
    explicit_telegram_session_path = str(
        os.getenv("SHAFA_TELEGRAM_SESSION_PATH") or ""
    ).strip()
    _apply_deactivation_account_environment(selected)
    if not explicit_shared_db_path:
        os.environ["SHAFA_SHARED_TELEGRAM_DB_PATH"] = str(
            _default_shared_telegram_db_path(selected)
        )
    if not explicit_telegram_session_path:
        os.environ["SHAFA_TELEGRAM_SESSION_PATH"] = str(
            selected.state_dir / "telegram.session"
        )
    _load_account_telegram_credentials(selected)


def _load_account_telegram_credentials(selected: AccountSession) -> None:
    credentials_path = selected.state_dir / ".env"
    if not credentials_path.exists():
        return
    wanted = {"SHAFA_TELEGRAM_API_ID", "SHAFA_TELEGRAM_API_HASH"}
    try:
        lines = credentials_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in wanted or str(os.getenv(key) or "").strip():
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def parse_telegram_datetime(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return datetime.combine(parsed_date, datetime.min.time())
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _row_value(row: Optional[sqlite3.Row], key: str, default: object = None) -> object:
    if row is None:
        return default
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def normalize_products_type(products_type: object) -> str:
    normalized = str(products_type or "").strip().upper()
    return PRODUCT_TYPE_ALIASES.get(normalized, normalized)


def fetch_products_by_type(
    *,
    products_type: str,
    page_size: int = 50,
    feed_func: Optional[Callable[..., dict]] = None,
) -> list[dict]:
    if feed_func is None:
        _ensure_shafa_logic_on_path()
        from core.requests.get_my_clothes_products_feed import (
            get_my_clothes_products_feed,
        )

        feed_func = get_my_clothes_products_feed

    normalized_page_size = max(int(page_size), 1)
    normalized_type = normalize_products_type(products_type)
    if not normalized_type:
        raise ValueError("products_type is required")

    products: list[dict] = []
    seen_ids: set[str] = set()
    after: Optional[str] = None

    while True:
        feed = feed_func(
            first=normalized_page_size,
            products_type=normalized_type,
            after=after,
        )
        if not feed:
            raise RuntimeError(
                f"Не удалось загрузить товары Shafa типа {normalized_type}."
            )

        errors = feed.get("errors") or []
        if errors:
            raise RuntimeError(f"Shafa вернула GraphQL errors: {errors}")

        edges = feed.get("edges") or []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node") or {}
            if not isinstance(node, dict):
                continue
            product_id = str(node.get("id") or "").strip()
            if not product_id or product_id in seen_ids:
                continue
            seen_ids.add(product_id)
            item = dict(node)
            item["_products_type"] = normalized_type
            products.append(item)

        page_info = feed.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break

        next_after = str(page_info.get("endCursor") or "").strip() or None
        if next_after is None or next_after == after:
            break
        after = next_after

    return products


def fetch_inactive_products(
    *,
    product_types: list[str],
    page_size: int = 50,
    feed_func: Optional[Callable[..., dict]] = None,
) -> list[dict]:
    products: list[dict] = []
    seen_ids: set[str] = set()
    for product_type in product_types:
        for product in fetch_products_by_type(
            products_type=product_type,
            page_size=page_size,
            feed_func=feed_func,
        ):
            product_id = str(product.get("id") or "").strip()
            if not product_id or product_id in seen_ids:
                continue
            seen_ids.add(product_id)
            products.append(product)
    return products


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_activation_check_columns(conn: sqlite3.Connection) -> bool:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_products'"
    ).fetchone()
    if table is None:
        return False
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(telegram_products)").fetchall()
    }
    for column, column_type in ACTIVATION_CHECK_COLUMNS.items():
        if column not in columns:
            conn.execute(
                f"ALTER TABLE telegram_products ADD COLUMN {column} {column_type}"
            )
    return True


def _mark_telegram_product_activation_check(
    *,
    account_id: object,
    channel_id: object,
    message_id: object,
    check_status: str,
    telegram_message_date: object = None,
    age_source: str = "telegram_message_date",
) -> bool:
    if channel_id is None or message_id is None:
        return False
    telegram_db_path = _shared_telegram_db_path()
    if not telegram_db_path.exists():
        return False
    normalized_account_id = str(account_id or _current_account_id() or "").strip()
    with _connect_sqlite(telegram_db_path) as conn:
        if not _ensure_activation_check_columns(conn):
            return False
        if normalized_account_id:
            cursor = conn.execute(
                """
                UPDATE telegram_products
                SET activation_check_status = ?,
                    activation_last_checked_at = datetime('now'),
                    activation_checked_age_source = ?,
                    activation_checked_telegram_message_date = ?,
                    updated_at = datetime('now')
                WHERE account_id = ?
                  AND channel_id = ?
                  AND message_id = ?
                """,
                (
                    str(check_status or "").strip(),
                    str(age_source or "").strip(),
                    str(telegram_message_date or "").strip() or None,
                    normalized_account_id,
                    int(channel_id),
                    int(message_id),
                ),
            )
            if cursor.rowcount:
                return True
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET activation_check_status = ?,
                activation_last_checked_at = datetime('now'),
                activation_checked_age_source = ?,
                activation_checked_telegram_message_date = ?,
                updated_at = datetime('now')
            WHERE channel_id = ?
              AND message_id = ?
            """,
            (
                str(check_status or "").strip(),
                str(age_source or "").strip(),
                str(telegram_message_date or "").strip() or None,
                int(channel_id),
                int(message_id),
            ),
        )
    return cursor.rowcount > 0


def _account_db_path() -> Path:
    raw = str(os.getenv("SHAFA_DB_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve(strict=False)
    return Path(__file__).resolve().parent / "data" / "shafa.sqlite3"


def _shared_telegram_db_path() -> Path:
    raw = str(os.getenv("SHAFA_SHARED_TELEGRAM_DB_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve(strict=False)
    return _default_shared_telegram_db_path()


def _current_account_id() -> str:
    return str(os.getenv("SHAFA_ACCOUNT_ID") or "").strip()


def _load_uploaded_product_row(product_id: str) -> Optional[sqlite3.Row]:
    db_path = _account_db_path()
    if not db_path.exists():
        return None
    with _connect_sqlite(db_path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='uploaded_products'"
        ).fetchone()
        if table is None:
            return None
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(uploaded_products)").fetchall()
        }
        optional_columns = [
            "id",
            "product_id",
            "name",
            "price",
            "raw_payload",
            "status_title",
            "is_active",
            "created_at",
            "shafa_created_at",
        ]
        selected_columns = [column for column in optional_columns if column in columns]
        if not selected_columns:
            return None
        row = conn.execute(
            f"""
            SELECT {", ".join(selected_columns)}
            FROM uploaded_products
            WHERE product_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()
    return row


def _raw_payload_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_inactive_uploaded_product_row(row: sqlite3.Row) -> bool:
    raw_is_active = _row_value(row, "is_active")
    if raw_is_active is not None and str(raw_is_active).strip().lower() in {
        "0",
        "false",
        "no",
        "ні",
        "нет",
    }:
        return True
    status_title = str(_row_value(row, "status_title") or "").strip().lower()
    return any(
        marker in status_title
        for marker in (
            "деактив",
            "неактив",
            "inactive",
            "not active",
            "deactivated",
        )
    )


def list_inactive_uploaded_products_from_account_db() -> list[dict]:
    db_path = _account_db_path()
    if not db_path.exists():
        return []
    with _connect_sqlite(db_path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='uploaded_products'"
        ).fetchone()
        if table is None:
            return []
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(uploaded_products)").fetchall()
        }
        if "product_id" not in columns:
            return []
        optional_columns = [
            "id",
            "product_id",
            "name",
            "price",
            "raw_payload",
            "status_title",
            "is_active",
            "created_at",
            "shafa_created_at",
        ]
        selected_columns = [column for column in optional_columns if column in columns]
        order_by = "id DESC" if "id" in columns else "product_id DESC"
        rows = conn.execute(
            f"""
            SELECT {", ".join(selected_columns)}
            FROM uploaded_products
            WHERE product_id IS NOT NULL
              AND TRIM(product_id) != ''
            ORDER BY {order_by}
            """
        ).fetchall()

    products: list[dict] = []
    seen_ids: set[str] = set()
    for row in rows:
        product_id = str(_row_value(row, "product_id") or "").strip()
        if not product_id or product_id in seen_ids:
            continue
        if not _is_inactive_uploaded_product_row(row):
            continue
        seen_ids.add(product_id)
        raw_payload = _raw_payload_dict(_row_value(row, "raw_payload"))
        name = str(_row_value(row, "name") or raw_payload.get("name") or "").strip()
        price = _row_value(row, "price")
        if price is None:
            price = raw_payload.get("price")
        created_at = (
            str(_row_value(row, "shafa_created_at") or "").strip()
            or str(_row_value(row, "created_at") or "").strip()
        )
        products.append(
            {
                "id": product_id,
                "name": name,
                "price": price,
                "statusTitle": str(_row_value(row, "status_title") or "").strip(),
                "_products_type": "account_db_inactive",
                "_account_db_created_at": created_at,
            }
        )
    return products


def _load_telegram_row_for_product(product_id: str) -> Optional[sqlite3.Row]:
    telegram_db_path = _shared_telegram_db_path()
    if not telegram_db_path.exists():
        return None
    account_id = _current_account_id()
    with _connect_sqlite(telegram_db_path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_products'"
        ).fetchone()
        if table is None:
            return None
        if account_id:
            row = conn.execute(
                """
                SELECT
                    account_id,
                    channel_id,
                    message_id,
                    created_product_id,
                    telegram_message_date,
                    parsed_data
                FROM telegram_products
                WHERE account_id = ?
                  AND created_product_id = ?
                  AND status = 'created'
                  AND created = 1
                ORDER BY
                    telegram_message_date DESC,
                    updated_at DESC,
                    channel_id DESC,
                    message_id DESC
                LIMIT 1
                """,
                (account_id, product_id),
            ).fetchone()
            if row is not None:
                return row
        return conn.execute(
            """
            SELECT
                account_id,
                channel_id,
                message_id,
                created_product_id,
                telegram_message_date,
                parsed_data
            FROM telegram_products
            WHERE created_product_id = ?
              AND status = 'created'
              AND created = 1
            ORDER BY
                CASE
                    WHEN telegram_message_date IS NOT NULL
                     AND TRIM(telegram_message_date) != '' THEN 0
                    ELSE 1
                END,
                updated_at DESC,
                channel_id DESC,
                message_id DESC
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()


def _load_missing_telegram_date_rows_for_product_ids(
    product_ids: list[str],
    *,
    limit: int,
) -> list[dict[str, object]]:
    return _load_telegram_date_rows_for_product_ids(
        product_ids,
        limit=limit,
        missing_only=True,
    )


def _iter_chunks(items: list[str], chunk_size: int) -> list[list[str]]:
    normalized_chunk_size = max(int(chunk_size), 1)
    return [
        items[index : index + normalized_chunk_size]
        for index in range(0, len(items), normalized_chunk_size)
    ]


def _load_telegram_date_rows_for_product_ids(
    product_ids: list[str],
    *,
    limit: int,
    missing_only: bool = False,
) -> list[dict[str, object]]:
    normalized_ids = [
        str(product_id or "").strip()
        for product_id in product_ids
        if str(product_id or "").strip()
    ]
    if not normalized_ids:
        return []
    telegram_db_path = _shared_telegram_db_path()
    if not telegram_db_path.exists():
        return []
    account_id = _current_account_id()
    row_limit = max(int(limit), 1)
    missing_condition = """
              AND (
                    telegram_message_date IS NULL
                    OR TRIM(telegram_message_date) = ''
              )
    """ if missing_only else ""
    account_order = "CASE WHEN account_id = ? THEN 0 ELSE 1 END," if account_id else ""
    account_order_params = (account_id,) if account_id else ()
    selected: list[dict[str, object]] = []
    selected_product_ids: set[str] = set()
    with _connect_sqlite(telegram_db_path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_products'"
        ).fetchone()
        if table is None:
            return []
        for id_chunk in _iter_chunks(list(dict.fromkeys(normalized_ids)), 800):
            if len(selected) >= row_limit:
                break
            placeholders = ",".join(["?"] * len(id_chunk))
            rows = conn.execute(
                f"""
                SELECT
                    account_id,
                    channel_id,
                    message_id,
                    created_product_id,
                    telegram_message_date
                FROM telegram_products
                WHERE created_product_id IN ({placeholders})
                  AND status = 'created'
                  AND created = 1
                  AND created_product_id IS NOT NULL
                  AND TRIM(created_product_id) != ''
                  AND created_product_id NOT LIKE 'SKIPPED_%'
                  {missing_condition}
                ORDER BY
                    {account_order}
                    CASE
                        WHEN telegram_message_date IS NOT NULL
                         AND TRIM(telegram_message_date) != '' THEN 0
                        ELSE 1
                    END,
                    updated_at DESC,
                    channel_id ASC,
                    message_id ASC
                """,
                (*id_chunk, *account_order_params),
            ).fetchall()
            for row in rows:
                product_id = str(row["created_product_id"] or "").strip()
                if not product_id or product_id in selected_product_ids:
                    continue
                selected_product_ids.add(product_id)
                selected.append(dict(row))
                if len(selected) >= row_limit:
                    break
    return selected


def _count_telegram_rows_for_product_ids(product_ids: list[str]) -> int:
    normalized_ids = [
        str(product_id or "").strip()
        for product_id in product_ids
        if str(product_id or "").strip()
    ]
    if not normalized_ids:
        return 0
    telegram_db_path = _shared_telegram_db_path()
    if not telegram_db_path.exists():
        return 0
    account_id = _current_account_id()
    placeholders = ",".join(["?"] * len(normalized_ids))
    with _connect_sqlite(telegram_db_path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_products'"
        ).fetchone()
        if table is None:
            return 0
        if account_id:
            row = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM telegram_products
                WHERE account_id = ?
                  AND created_product_id IN ({placeholders})
                  AND status = 'created'
                  AND created = 1
                """,
                (account_id, *normalized_ids),
            ).fetchone()
            if row is not None and int(row[0] or 0) > 0:
                return int(row[0] or 0)
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT created_product_id)
            FROM telegram_products
            WHERE created_product_id IN ({placeholders})
              AND status = 'created'
              AND created = 1
            """,
            (*normalized_ids,),
        ).fetchone()
    return int(row[0] or 0) if row is not None else 0


def clear_telegram_message_dates_for_product_ids(
    product_ids: list[str],
    *,
    limit: int,
) -> int:
    normalized_ids = [
        str(product_id or "").strip()
        for product_id in product_ids
        if str(product_id or "").strip()
    ]
    if not normalized_ids or int(limit) <= 0:
        return 0
    telegram_db_path = _shared_telegram_db_path()
    if not telegram_db_path.exists():
        return 0
    account_id = _current_account_id()
    if not account_id:
        return 0
    placeholders = ",".join(["?"] * len(normalized_ids))
    row_limit = max(int(limit), 1)
    with _connect_sqlite(telegram_db_path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_products'"
        ).fetchone()
        if table is None:
            return 0
        rows = conn.execute(
            f"""
            SELECT channel_id, message_id
            FROM telegram_products
            WHERE account_id = ?
              AND created_product_id IN ({placeholders})
              AND status = 'created'
              AND created = 1
              AND telegram_message_date IS NOT NULL
              AND TRIM(telegram_message_date) != ''
            ORDER BY channel_id ASC, message_id ASC
            LIMIT ?
            """,
            (account_id, *normalized_ids, row_limit),
        ).fetchall()
        cleared = 0
        for row in rows:
            cursor = conn.execute(
                """
                UPDATE telegram_products
                SET telegram_message_date = NULL,
                    updated_at = datetime('now')
                WHERE account_id = ? AND channel_id = ? AND message_id = ?
                """,
                (account_id, int(row["channel_id"]), int(row["message_id"])),
            )
            cleared += int(cursor.rowcount or 0)
    return cleared


def _update_telegram_message_date(
    *,
    account_id: str,
    channel_id: int,
    message_id: int,
    telegram_message_date: datetime,
) -> bool:
    telegram_db_path = _shared_telegram_db_path()
    if not telegram_db_path.exists():
        return False
    normalized_date = telegram_message_date.astimezone(timezone.utc).replace(
        tzinfo=None
    ).isoformat()
    with _connect_sqlite(telegram_db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE telegram_products
            SET telegram_message_date = ?,
                updated_at = datetime('now')
            WHERE account_id = ? AND channel_id = ? AND message_id = ?
            """,
            (
                normalized_date,
                str(account_id),
                int(channel_id),
                int(message_id),
            ),
        )
    return bool(cursor.rowcount)


async def _backfill_telegram_message_dates_from_telegram_async(
    rows: list[dict[str, object]],
) -> dict[str, int]:
    if not rows:
        return {"updated": 0, "failed": 0}
    _ensure_shafa_logic_on_path()
    from controller.data_controller import (
        _message_datetime_utc,
        _resolve_channel_peer,
        create_telegram_client,
    )
    from data.const import (
        TELEGRAM_API_HASH,
        TELEGRAM_API_ID,
        TELEGRAM_SESSION_PATH,
    )

    if TELEGRAM_API_ID is None or not str(TELEGRAM_API_HASH or "").strip():
        raise RuntimeError(
            "Нужны SHAFA_TELEGRAM_API_ID и SHAFA_TELEGRAM_API_HASH для Telegram backfill."
        )

    grouped_by_channel: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        grouped_by_channel.setdefault(int(row["channel_id"]), []).append(row)

    updated = 0
    failed = 0
    async with create_telegram_client(
        TELEGRAM_SESSION_PATH,
        int(TELEGRAM_API_ID),
        str(TELEGRAM_API_HASH),
        save_entities=False,
        account_id=_current_account_id(),
    ) as client:
        for channel_id, channel_rows in grouped_by_channel.items():
            try:
                channel_peer = await _resolve_channel_peer(client, channel_id)
                fetched_messages = await client.get_messages(
                    channel_peer,
                    ids=[int(row["message_id"]) for row in channel_rows],
                )
            except Exception as exc:
                failed += len(channel_rows)
                print(
                    "WARN: не удалось получить даты из Telegram "
                    f"channel_id={channel_id}. error={exc}"
                )
                continue

            if fetched_messages is None:
                fetched_list: list[object] = []
            elif isinstance(fetched_messages, list):
                fetched_list = fetched_messages
            else:
                fetched_list = [fetched_messages]

            messages_by_id = {
                int(getattr(message, "id", 0)): message
                for message in fetched_list
                if getattr(message, "id", None) is not None
            }
            for row in channel_rows:
                message_id = int(row["message_id"])
                message = messages_by_id.get(message_id)
                message_date = _message_datetime_utc(message) if message is not None else None
                if message_date is None:
                    failed += 1
                    continue
                if _update_telegram_message_date(
                    account_id=str(row["account_id"]),
                    channel_id=channel_id,
                    message_id=message_id,
                    telegram_message_date=message_date,
                ):
                    updated += 1
                else:
                    failed += 1
    return {"updated": updated, "failed": failed}


def backfill_missing_telegram_message_dates_for_product_ids(
    product_ids: list[str],
    *,
    limit: int = DEFAULT_TELEGRAM_DATE_BACKFILL_LIMIT,
    batch_size: int = DEFAULT_TELEGRAM_DATE_BACKFILL_BATCH_SIZE,
    sleep_min_seconds: float = 30.0,
    sleep_max_seconds: float = 60.0,
    refresh_existing: bool = True,
) -> dict[str, int]:
    total_limit = max(int(limit), 0)
    if total_limit <= 0:
        return {"checked": 0, "updated": 0, "failed": 0}
    normalized_batch_size = max(int(batch_size), 1)
    sleep_min = max(float(sleep_min_seconds), 0.0)
    sleep_max = max(float(sleep_max_seconds), sleep_min)

    checked = 0
    updated = 0
    failed = 0
    rows_to_refresh = _load_telegram_date_rows_for_product_ids(
        product_ids,
        limit=total_limit,
        missing_only=not refresh_existing,
    )
    if not rows_to_refresh:
        return {"checked": 0, "updated": 0, "failed": 0}

    batch_index = 0
    for offset in range(0, len(rows_to_refresh), normalized_batch_size):
        rows = rows_to_refresh[offset : offset + normalized_batch_size]
        batch_index += 1
        print(
            "Telegram date refresh batch start: "
            f"batch={batch_index} size={len(rows)} "
            f"checked_so_far={checked} total_rows={len(rows_to_refresh)} "
            f"refresh_existing={str(refresh_existing).lower()}."
        )
        result = asyncio.run(_backfill_telegram_message_dates_from_telegram_async(rows))
        checked += len(rows)
        updated += int(result["updated"])
        failed += int(result["failed"])
        print(
            "Telegram date refresh batch done: "
            f"batch={batch_index} checked={len(rows)} "
            f"updated={int(result['updated'])} failed={int(result['failed'])}."
        )
        if offset + normalized_batch_size >= len(rows_to_refresh):
            break
        delay = random.uniform(sleep_min, sleep_max)
        if delay > 0:
            print(
                "Telegram date refresh sleeping before next batch: "
                f"{delay:.1f} seconds."
            )
            time.sleep(delay)
    return {
        "checked": checked,
        "updated": updated,
        "failed": failed,
    }


def _load_telegram_row_for_identity(
    telegram_id: int,
    message_id: int,
) -> Optional[sqlite3.Row]:
    telegram_db_path = _shared_telegram_db_path()
    if not telegram_db_path.exists():
        return None
    account_id = _current_account_id()
    if not account_id:
        return None
    with _connect_sqlite(telegram_db_path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_products'"
        ).fetchone()
        if table is None:
            return None
        return conn.execute(
            """
            SELECT
                account_id,
                channel_id,
                message_id,
                created_product_id,
                telegram_message_date,
                parsed_data
            FROM telegram_products
            WHERE account_id = ?
              AND channel_id = ?
              AND message_id = ?
              AND status = 'created'
              AND created = 1
              AND created_product_id IS NOT NULL
              AND TRIM(created_product_id) != ''
              AND created_product_id NOT LIKE 'SKIPPED_%'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (account_id, int(telegram_id), int(message_id)),
        ).fetchone()


def _product_name_from_parsed_data(value: object) -> str:
    if isinstance(value, str):
        value = _raw_payload_dict(value)
    if not isinstance(value, dict):
        return ""
    for key in ("name", "title", "product_name"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""


def _candidate_from_telegram_row(
    telegram_row: sqlite3.Row,
    *,
    today: date,
    max_age_days: int,
) -> Optional[ActivationCandidate]:
    product_id = str(telegram_row["created_product_id"] or "").strip()
    if not product_id:
        return None
    telegram_datetime = parse_telegram_datetime(telegram_row["telegram_message_date"])
    if telegram_datetime is None:
        _mark_telegram_product_activation_check(
            account_id=telegram_row["account_id"],
            channel_id=telegram_row["channel_id"],
            message_id=telegram_row["message_id"],
            check_status=ACTIVATION_CHECK_STATUS_MISSING_DATE,
            telegram_message_date=telegram_row["telegram_message_date"],
        )
        print(
            "skip: telegram_message_date is missing or invalid "
            f"telegram_id={telegram_row['channel_id']} message_id={telegram_row['message_id']} "
            f"product_id={product_id}"
        )
        return None
    telegram_date = telegram_datetime.date()
    age_days = (today - telegram_date).days
    if age_days < 0:
        _mark_telegram_product_activation_check(
            account_id=telegram_row["account_id"],
            channel_id=telegram_row["channel_id"],
            message_id=telegram_row["message_id"],
            check_status=ACTIVATION_CHECK_STATUS_FUTURE_DATE,
            telegram_message_date=telegram_row["telegram_message_date"],
        )
        print(
            "skip: telegram_message_date is in the future "
            f"telegram_id={telegram_row['channel_id']} message_id={telegram_row['message_id']} "
            f"telegram_date={telegram_date.isoformat()} product_id={product_id}"
        )
        return None
    if age_days > max_age_days:
        _mark_telegram_product_activation_check(
            account_id=telegram_row["account_id"],
            channel_id=telegram_row["channel_id"],
            message_id=telegram_row["message_id"],
            check_status=ACTIVATION_CHECK_STATUS_TOO_OLD,
            telegram_message_date=telegram_row["telegram_message_date"],
        )
        print(
            "skip: telegram product is older than activation limit "
            f"telegram_id={telegram_row['channel_id']} message_id={telegram_row['message_id']} "
            f"telegram_date={telegram_date.isoformat()} age_days={age_days} "
            f"max_age_days={max_age_days} product_id={product_id}"
        )
        return None

    uploaded_row = _load_uploaded_product_row(product_id)
    name = str(_row_value(uploaded_row, "name") or "").strip()
    if not name:
        name = _product_name_from_parsed_data(telegram_row["parsed_data"])
    _mark_telegram_product_activation_check(
        account_id=telegram_row["account_id"],
        channel_id=telegram_row["channel_id"],
        message_id=telegram_row["message_id"],
        check_status=ACTIVATION_CHECK_STATUS_ELIGIBLE,
        telegram_message_date=telegram_row["telegram_message_date"],
    )
    return ActivationCandidate(
        product_id=product_id,
        name=name or "без названия",
        telegram_date=telegram_date,
        telegram_age_days=age_days,
        product_type="telegram_identity",
        status_title=str(_row_value(uploaded_row, "status_title") or "").strip(),
        channel_id=int(telegram_row["channel_id"]),
        message_id=int(telegram_row["message_id"]),
        age_source="telegram_message_date",
    )


def select_product_for_activation_by_telegram_identity(
    telegram_id: int,
    message_id: int,
    *,
    today: Optional[date] = None,
    max_age_days: int = HALF_YEAR_DAYS,
    telegram_date_backfill_batch_size: int = 50,
    telegram_date_backfill_sleep_min_seconds: float = 30.0,
    telegram_date_backfill_sleep_max_seconds: float = 60.0,
) -> Optional[ActivationCandidate]:
    telegram_row = _load_telegram_row_for_identity(
        telegram_id=int(telegram_id),
        message_id=int(message_id),
    )
    if telegram_row is None:
        print(
            "skip: telegram product mapping not found "
            f"telegram_id={telegram_id} message_id={message_id} "
            f"account_id={_current_account_id() or 'unknown'}"
        )
        return None
    backfill_missing_telegram_message_dates_for_product_ids(
        [str(telegram_row["created_product_id"])],
        limit=1,
        batch_size=telegram_date_backfill_batch_size,
        sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
        sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
        refresh_existing=True,
    )
    telegram_row = _load_telegram_row_for_identity(
        telegram_id=int(telegram_id),
        message_id=int(message_id),
    )
    if telegram_row is None:
        return None
    return _candidate_from_telegram_row(
        telegram_row,
        today=today or date.today(),
        max_age_days=max(int(max_age_days), 1),
    )


def _candidate_from_product(
    product: dict,
    *,
    today: date,
    max_age_days: int,
) -> Optional[ActivationCandidate]:
    product_id = str(product.get("id") or "").strip()
    if not product_id:
        return None
    uploaded_row = _load_uploaded_product_row(product_id)

    telegram_row = _load_telegram_row_for_product(product_id)
    age_source = "telegram_message_date"
    if telegram_row is None:
        return None
    telegram_datetime = parse_telegram_datetime(telegram_row["telegram_message_date"])
    if telegram_datetime is None:
        _mark_telegram_product_activation_check(
            account_id=telegram_row["account_id"],
            channel_id=telegram_row["channel_id"],
            message_id=telegram_row["message_id"],
            check_status=ACTIVATION_CHECK_STATUS_MISSING_DATE,
            telegram_message_date=telegram_row["telegram_message_date"],
        )
        return None
    telegram_date = telegram_datetime.date()
    channel_id = int(telegram_row["channel_id"])
    message_id = int(telegram_row["message_id"])

    age_days = (today - telegram_date).days
    if age_days < 0:
        _mark_telegram_product_activation_check(
            account_id=telegram_row["account_id"],
            channel_id=channel_id,
            message_id=message_id,
            check_status=ACTIVATION_CHECK_STATUS_FUTURE_DATE,
            telegram_message_date=telegram_row["telegram_message_date"],
        )
        return None
    if age_days > max_age_days:
        _mark_telegram_product_activation_check(
            account_id=telegram_row["account_id"],
            channel_id=channel_id,
            message_id=message_id,
            check_status=ACTIVATION_CHECK_STATUS_TOO_OLD,
            telegram_message_date=telegram_row["telegram_message_date"],
        )
        return None

    name = str(product.get("name") or _row_value(uploaded_row, "name") or "").strip()
    _mark_telegram_product_activation_check(
        account_id=telegram_row["account_id"],
        channel_id=channel_id,
        message_id=message_id,
        check_status=ACTIVATION_CHECK_STATUS_ELIGIBLE,
        telegram_message_date=telegram_row["telegram_message_date"],
    )
    return ActivationCandidate(
        product_id=product_id,
        name=name or "без названия",
        telegram_date=telegram_date,
        telegram_age_days=age_days,
        product_type=str(product.get("_products_type") or "").strip(),
        status_title=str(
            product.get("statusTitle") or _row_value(uploaded_row, "status_title") or ""
        ).strip(),
        price=product.get("price"),
        url=str(product.get("url") or "").strip(),
        channel_id=channel_id,
        message_id=message_id,
        age_source=age_source,
    )


def select_products_for_activation(
    products: list[dict],
    *,
    today: Optional[date] = None,
    max_age_days: int = HALF_YEAR_DAYS,
) -> list[ActivationCandidate]:
    resolved_today = today or date.today()
    normalized_max_age_days = max(int(max_age_days), 1)
    candidates: list[ActivationCandidate] = []
    for product in products:
        candidate = _candidate_from_product(
            product,
            today=resolved_today,
            max_age_days=normalized_max_age_days,
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _is_trusted_telegram_candidate(candidate: ActivationCandidate) -> bool:
    return (
        candidate.age_source == "telegram_message_date"
        and candidate.channel_id is not None
        and candidate.message_id is not None
    )


def _filter_trusted_telegram_candidates(
    candidates: list[ActivationCandidate],
) -> list[ActivationCandidate]:
    trusted: list[ActivationCandidate] = []
    for candidate in candidates:
        if _is_trusted_telegram_candidate(candidate):
            trusted.append(candidate)
            continue
        print(
            "skip: activation candidate does not have trusted Telegram age "
            f"product_id={candidate.product_id} "
            f"age_source={candidate.age_source or 'unknown'} "
            f"telegram={candidate.channel_id}:{candidate.message_id}"
        )
        _mark_telegram_product_activation_check(
            account_id=_current_account_id(),
            channel_id=candidate.channel_id,
            message_id=candidate.message_id,
            check_status=ACTIVATION_CHECK_STATUS_UNTRUSTED_AGE,
            telegram_message_date=candidate.telegram_date.isoformat(),
            age_source=candidate.age_source,
        )
    return trusted


def print_candidates(candidates: list[ActivationCandidate]) -> None:
    for index, candidate in enumerate(candidates, start=1):
        price = "" if candidate.price is None else f" | price={candidate.price}"
        url = "" if not candidate.url else f" | {candidate.url}"
        telegram = (
            ""
            if candidate.channel_id is None or candidate.message_id is None
            else f" | tg={candidate.channel_id}:{candidate.message_id}"
        )
        age_source = f" | age_source={candidate.age_source}"
        print(
            f"{index}. {candidate.telegram_date.isoformat()} "
            f"({candidate.telegram_age_days}d) | {candidate.product_id} | "
            f"{candidate.name} | {candidate.product_type} | "
            f"{candidate.status_title}{telegram}{age_source}{price}{url}"
        )


ACTIVATE_PRODUCTS_MUTATION = """
mutation activateProducts(
  $includeIds: [Int]
  $excludeIds: [Int]
  $allProducts: Boolean
) {
  activateProducts(
    includeIds: $includeIds
    excludeIds: $excludeIds
    allProducts: $allProducts
  ) {
    isSuccess
    errors {
      field
      messages {
        code
      }
    }
  }
}
"""


def _summarize_activation_errors(errors: list[dict]) -> str:
    parts: list[str] = []
    for err in errors:
        field = str(err.get("field") or "").strip() or "__all__"
        messages = err.get("messages") or []
        codes = [
            str(message.get("code") or "").strip()
            for message in messages
            if str(message.get("code") or "").strip()
        ]
        parts.append(f"{field}: {','.join(dict.fromkeys(codes))}" if codes else field)
    return " / ".join(parts) if parts else "unknown"


def activate_product(product_id: str) -> None:
    _ensure_shafa_logic_on_path()
    from core.no_playwright import (
        _base_headers,
        _debug_request_auth,
        _get_csrftoken_from_cookies,
        _load_shafa_cookies,
        _request_json,
    )
    from data.const import API_URL

    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        raise ValueError("product_id is required")
    try:
        product_id_int = int(normalized_product_id)
    except ValueError as exc:
        raise ValueError("product_id must be an integer") from exc

    cookies = _load_shafa_cookies()
    _debug_request_auth("activateProducts", cookies)
    if not cookies:
        raise RuntimeError("No saved cookies. Log in via main.py first.")

    csrftoken = _get_csrftoken_from_cookies(cookies)
    if not csrftoken:
        raise RuntimeError("csrftoken not found in cookies")

    payload = {
        "operationName": "activateProducts",
        "variables": {
            "includeIds": [product_id_int],
            "excludeIds": None,
            "allProducts": False,
        },
        "query": ACTIVATE_PRODUCTS_MUTATION,
    }
    headers = {
        **_base_headers(csrftoken),
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Referer": "https://shafa.ua/uk/my/clothes",
    }
    data = _request_json(
        API_URL,
        json.dumps(payload).encode("utf-8"),
        headers,
        cookies,
    )
    top_level_errors = data.get("errors") or []
    if top_level_errors:
        messages = [
            str(error.get("message") or "").strip()
            for error in top_level_errors
            if str(error.get("message") or "").strip()
        ]
        raise RuntimeError(" / ".join(messages) if messages else str(top_level_errors))

    result = data.get("data", {}).get("activateProducts") or {}
    if not result.get("isSuccess"):
        errors = result.get("errors") or []
        if errors:
            raise RuntimeError(_summarize_activation_errors(errors))
        raise RuntimeError("Product activation failed")


def mark_uploaded_product_active(
    product_id: str,
    *,
    status_title: Optional[str] = "Активно",
) -> bool:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        return False
    db_path = _account_db_path()
    if not db_path.exists():
        return False
    with _connect_sqlite(db_path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='uploaded_products'"
        ).fetchone()
        if table is None:
            return False
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(uploaded_products)").fetchall()
        }
        if "is_active" not in columns:
            conn.execute(
                "ALTER TABLE uploaded_products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )
        if "status_title" not in columns:
            conn.execute("ALTER TABLE uploaded_products ADD COLUMN status_title TEXT")
        cursor = conn.execute(
            """
            UPDATE uploaded_products
            SET is_active = 1,
                status_title = COALESCE(?, status_title)
            WHERE product_id = ?
            """,
            (str(status_title or "").strip() or None, normalized_product_id),
        )
    return bool(cursor.rowcount)


def activate_candidates(
    candidates: list[ActivationCandidate],
    *,
    activate_func: Optional[Callable[[str], None]] = None,
    mark_active_func: Optional[Callable[..., bool]] = None,
    sleep_min_seconds: float = DEFAULT_ACTIVATION_SLEEP_MIN_SECONDS,
    sleep_max_seconds: float = DEFAULT_ACTIVATION_SLEEP_MAX_SECONDS,
    on_candidate_processed: Optional[Callable[[ActivationCandidate, bool], None]] = None,
    account_name: str = "",
    progress_every: int = 1,
    verify_activation_flow: bool = False,
    log_func: Optional[Callable[[str], None]] = None,
) -> dict[str, int]:
    if activate_func is None and not verify_activation_flow:
        activate_func = activate_product
    if mark_active_func is None and not verify_activation_flow:
        mark_active_func = mark_uploaded_product_active

    activated = 0
    failed = 0
    mark_failed = 0
    sleep_min = max(float(sleep_min_seconds), 0.0)
    sleep_max = max(float(sleep_max_seconds), 0.0)
    normalized_progress_every = max(int(progress_every), 1)
    progress_account_name = str(account_name or os.getenv("SHAFA_ACCOUNT_NAME") or "").strip()
    progress_prefix = f"[{progress_account_name}] " if progress_account_name else ""

    def _log(message: str) -> None:
        if log_func is not None:
            log_func(message)
        else:
            print(message, flush=True)

    if candidates:
        _log(
            f"First activation attempt for account {progress_account_name or 'current'}",
        )

    for index, candidate in enumerate(candidates, start=1):
        should_print_progress = (
            index == 1
            or index == len(candidates)
            or index % normalized_progress_every == 0
        )
        if should_print_progress:
            _log(
                f"{progress_prefix}[{index}/{len(candidates)}] "
                f"Activating {candidate.product_id} | {candidate.name}",
            )
        success = False
        try:
            if verify_activation_flow:
                time.sleep(0.1)
            else:
                if activate_func is None:
                    raise RuntimeError("activate_func is not configured")
                activate_func(candidate.product_id)
        except Exception as exc:
            failed += 1
            _mark_telegram_product_activation_check(
                account_id=_current_account_id(),
                channel_id=candidate.channel_id,
                message_id=candidate.message_id,
                check_status=ACTIVATION_CHECK_STATUS_FAILED,
                telegram_message_date=candidate.telegram_date.isoformat(),
                age_source=candidate.age_source,
            )
            _log(f"{progress_prefix}ERROR {candidate.product_id}: {exc}")
        else:
            activated += 1
            _mark_telegram_product_activation_check(
                account_id=_current_account_id(),
                channel_id=candidate.channel_id,
                message_id=candidate.message_id,
                check_status=ACTIVATION_CHECK_STATUS_ACTIVATED,
                telegram_message_date=candidate.telegram_date.isoformat(),
                age_source=candidate.age_source,
            )
            if not verify_activation_flow:
                try:
                    if mark_active_func is None:
                        raise RuntimeError("mark_active_func is not configured")
                    mark_active_func(candidate.product_id, status_title="Активно")
                except Exception as exc:
                    mark_failed += 1
                    _log(
                        f"{progress_prefix}WARN {candidate.product_id}: "
                        f"товар активирован, но локальная БД не обновлена: {exc}",
                    )
                else:
                    if should_print_progress:
                        _log(f"{progress_prefix}OK {candidate.product_id}")
            elif should_print_progress:
                _log(f"{progress_prefix}OK simulated {candidate.product_id}")
            success = True

        if on_candidate_processed is not None:
            on_candidate_processed(candidate, success)

        if index < len(candidates):
            delay = 0.1 if verify_activation_flow else random.uniform(sleep_min, sleep_max)
            if should_print_progress:
                _log(
                    f"{progress_prefix}Sleeping {delay:.1f} seconds before next product",
                )
            time.sleep(delay)

    return {
        "activated": activated,
        "failed": failed,
        "mark_failed": mark_failed,
    }


def confirm_activation(count: int) -> bool:
    answer = input(
        f"Активировать {count} товаров? Введите yes или да для подтверждения: "
    )
    return answer.strip().lower() in {"yes", "да"}


def _empty_backfill_stats() -> dict[str, int]:
    return {
        "date_backfill_checked": 0,
        "date_loaded_from_telegram": 0,
        "date_load_failed": 0,
    }


def _add_backfill_stats(target: dict[str, int], source: dict[str, int]) -> None:
    for key in _empty_backfill_stats():
        target[key] = int(target.get(key, 0)) + int(source.get(key, 0))


def _emit_live_log(message: str, log_queue: object = None) -> None:
    if log_queue is not None:
        try:
            log_queue.put(str(message))
            return
        except Exception:
            pass
    print(str(message), flush=True)


def _drain_live_log_queue(log_queue: object) -> None:
    while True:
        try:
            message = log_queue.get_nowait()
        except queue.Empty:
            break
        print(str(message), flush=True)


def _is_shafa_auth_error_message(message: object) -> bool:
    normalized = str(message or "").lower()
    return (
        "user not authenticated" in normalized
        or "not authenticated" in normalized
        or "no saved cookies" in normalized
    )


def collect_current_account_candidates(
    page_size: int,
    product_types: list[str],
    max_age_days: int,
    telegram_date_backfill_limit: int = DEFAULT_TELEGRAM_DATE_BACKFILL_LIMIT,
    telegram_date_backfill_batch_size: int = DEFAULT_TELEGRAM_DATE_BACKFILL_BATCH_SIZE,
    telegram_date_backfill_sleep_min_seconds: float = 30.0,
    telegram_date_backfill_sleep_max_seconds: float = 60.0,
    clear_telegram_dates_limit: int = 0,
    backfill_stats: Optional[dict[str, int]] = None,
) -> list[ActivationCandidate]:
    stats = _empty_backfill_stats()
    print(f"Загружаю товары Shafa типов: {', '.join(product_types)}...")
    shafa_products = fetch_inactive_products(
        page_size=page_size,
        product_types=product_types,
    )
    account_db_products = list_inactive_uploaded_products_from_account_db()
    products_by_id: dict[str, dict] = {}
    products: list[dict] = []
    for product in shafa_products:
        product_id = str(product.get("id") or "").strip()
        if not product_id:
            continue
        products_by_id[product_id] = product
        products.append(product)
    for product in account_db_products:
        product_id = str(product.get("id") or "").strip()
        if not product_id:
            continue
        existing = products_by_id.get(product_id)
        if existing is None:
            products_by_id[product_id] = product
            products.append(product)
            continue
        for key in (
            "_account_db_created_at",
            "statusTitle",
            "price",
        ):
            if product.get(key) not in (None, ""):
                existing.setdefault(key, product.get(key))

    product_ids = [
        str(product.get("id") or "").strip()
        for product in products
        if str(product.get("id") or "").strip()
    ]
    matched_telegram_rows = _count_telegram_rows_for_product_ids(product_ids)
    print(
        "Telegram DB lookup: "
        f"path={_shared_telegram_db_path()} "
        f"matched_created_product_rows={matched_telegram_rows}."
    )
    print(
        "Account DB inactive uploaded_products: "
        f"{len(account_db_products)}. Combined inactive products: {len(products)}."
    )
    if clear_telegram_dates_limit > 0:
        cleared = clear_telegram_message_dates_for_product_ids(
            product_ids,
            limit=clear_telegram_dates_limit,
        )
        print(f"DB test setup: cleared telegram_message_date rows: {cleared}.")
    if telegram_date_backfill_limit > 0:
        try:
            backfill_result = backfill_missing_telegram_message_dates_for_product_ids(
                product_ids,
                limit=telegram_date_backfill_limit,
                batch_size=telegram_date_backfill_batch_size,
                sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
                sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
                refresh_existing=True,
            )
        except Exception as exc:
            print(f"WARN: Telegram date refresh failed: {exc}")
        else:
            stats["date_backfill_checked"] += int(backfill_result["checked"])
            stats["date_loaded_from_telegram"] += int(backfill_result["updated"])
            stats["date_load_failed"] += int(backfill_result["failed"])
            if backfill_result["checked"]:
                print(
                    "Telegram date refresh: "
                    f"checked={backfill_result['checked']} "
                    f"updated={backfill_result['updated']} "
                    f"failed={backfill_result['failed']}."
                )
    if backfill_stats is not None:
        _add_backfill_stats(backfill_stats, stats)
    candidates = select_products_for_activation(
        products,
        max_age_days=max_age_days,
    )
    print(
        f"Загружено неактивных товаров Shafa: {len(shafa_products)}. "
        f"Кандидатов младше {max_age_days} дней по Telegram: "
        f"{len(candidates)}."
    )
    return candidates


def process_current_account(
    page_size: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    dry_run: bool,
    yes: bool,
    product_types: list[str],
    max_age_days: int,
    telegram_date_backfill_limit: int = DEFAULT_TELEGRAM_DATE_BACKFILL_LIMIT,
    telegram_date_backfill_batch_size: int = DEFAULT_TELEGRAM_DATE_BACKFILL_BATCH_SIZE,
    telegram_date_backfill_sleep_min_seconds: float = 30.0,
    telegram_date_backfill_sleep_max_seconds: float = 60.0,
    clear_telegram_dates_limit: int = 0,
    candidates: Optional[list[ActivationCandidate]] = None,
    on_candidate_processed: Optional[Callable[[ActivationCandidate, bool], None]] = None,
    account_name: str = "",
    progress_every: int = 1,
    verify_activation_flow: bool = False,
    print_candidate_list: bool = True,
    live_log_func: Optional[Callable[[str], None]] = None,
) -> dict[str, int]:
    backfill_stats = _empty_backfill_stats()
    if candidates is None:
        candidates = collect_current_account_candidates(
            page_size=page_size,
            product_types=product_types,
            max_age_days=max_age_days,
            telegram_date_backfill_limit=telegram_date_backfill_limit,
            telegram_date_backfill_batch_size=telegram_date_backfill_batch_size,
            telegram_date_backfill_sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
            telegram_date_backfill_sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
            clear_telegram_dates_limit=clear_telegram_dates_limit,
            backfill_stats=backfill_stats,
        )
    else:
        print(
            f"Кандидатов младше {max_age_days} дней по Telegram: "
            f"{len(candidates)}."
        )
    candidates = _filter_trusted_telegram_candidates(candidates)

    if not candidates:
        return {
            "activated": 0,
            "failed": 0,
            "mark_failed": 0,
            **backfill_stats,
        }

    if print_candidate_list:
        print_candidates(candidates)
    if dry_run:
        print("dry-run: активация не выполнялась.")
        return {
            "activated": 0,
            "failed": 0,
            "mark_failed": 0,
            **backfill_stats,
        }

    if not verify_activation_flow and not yes and not confirm_activation(len(candidates)):
        print("Отменено.")
        return {
            "activated": 0,
            "failed": 0,
            "mark_failed": 0,
            **backfill_stats,
        }

    result = activate_candidates(
        candidates,
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        on_candidate_processed=on_candidate_processed,
        account_name=account_name,
        progress_every=progress_every,
        verify_activation_flow=verify_activation_flow,
        log_func=live_log_func,
    )
    print(
        "Готово. "
        f"Активировано: {result['activated']}. "
        f"Ошибок: {result['failed']}. "
            f"Ошибок локальной отметки: {result['mark_failed']}."
    )
    result.update(backfill_stats)
    return result


def _candidate_to_data(candidate: ActivationCandidate) -> dict[str, object]:
    return {
        "product_id": candidate.product_id,
        "name": candidate.name,
        "telegram_date": candidate.telegram_date.isoformat(),
        "telegram_age_days": candidate.telegram_age_days,
        "product_type": candidate.product_type,
        "status_title": candidate.status_title,
        "price": candidate.price,
        "url": candidate.url,
        "channel_id": candidate.channel_id,
        "message_id": candidate.message_id,
        "age_source": candidate.age_source,
    }


def _candidate_from_data(data: dict[str, object]) -> ActivationCandidate:
    channel_id = data.get("channel_id")
    message_id = data.get("message_id")
    return ActivationCandidate(
        product_id=str(data["product_id"]),
        name=str(data["name"]),
        telegram_date=parse_cli_date(data["telegram_date"]),
        telegram_age_days=int(data["telegram_age_days"]),
        product_type=str(data.get("product_type") or ""),
        status_title=str(data.get("status_title") or ""),
        price=data.get("price"),
        url=str(data.get("url") or ""),
        channel_id=int(channel_id) if channel_id is not None else None,
        message_id=int(message_id) if message_id is not None else None,
        age_source=str(data.get("age_source") or "telegram_message_date"),
    )


def collect_account_candidates_worker(
    session_data: dict[str, Optional[str]],
    page_size: int,
    product_types: list[str],
    max_age_days: int,
    telegram_date_backfill_limit: int,
    telegram_date_backfill_batch_size: int,
    telegram_date_backfill_sleep_min_seconds: float,
    telegram_date_backfill_sleep_max_seconds: float,
    clear_telegram_dates_limit: int,
) -> dict[str, object]:
    output = StringIO()
    backfill_stats = _empty_backfill_stats()
    try:
        with redirect_stdout(output):
            session = _session_from_data(session_data)
            _apply_account_environment(session)
            candidates = collect_current_account_candidates(
                page_size=page_size,
                product_types=product_types,
                max_age_days=max_age_days,
                telegram_date_backfill_limit=telegram_date_backfill_limit,
                telegram_date_backfill_batch_size=telegram_date_backfill_batch_size,
                telegram_date_backfill_sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
                telegram_date_backfill_sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
                clear_telegram_dates_limit=clear_telegram_dates_limit,
                backfill_stats=backfill_stats,
            )
    except Exception as exc:
        auth_failed = _is_shafa_auth_error_message(exc)
        return {
            "ok": False,
            "error": str(exc),
            "auth_failed": auth_failed,
            "candidates": [],
            "candidate_count": 0,
            "backfill_stats": backfill_stats,
            "log": output.getvalue(),
        }
    return {
        "ok": True,
        "error": "",
        "auth_failed": False,
        "candidates": [_candidate_to_data(candidate) for candidate in candidates],
        "candidate_count": len(candidates),
        "backfill_stats": backfill_stats,
        "log": output.getvalue(),
    }


def process_account_worker(
    session_data: dict[str, Optional[str]],
    page_size: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    product_types: list[str],
    max_age_days: int,
    telegram_date_backfill_limit: int,
    telegram_date_backfill_batch_size: int,
    telegram_date_backfill_sleep_min_seconds: float,
    telegram_date_backfill_sleep_max_seconds: float,
    clear_telegram_dates_limit: int,
    candidates_data: list[dict[str, object]],
    progress_every: int,
    verify_activation_flow: bool,
    log_queue: object = None,
) -> dict[str, object]:
    processed_count = 0
    try:
        session = _session_from_data(session_data)
        _apply_account_environment(session)
        candidates = [
            _candidate_from_data(candidate_data)
            for candidate_data in candidates_data
        ]
        if verify_activation_flow:
            candidates = candidates[:3]
        _emit_live_log(
            f"[{session.name}] Worker started with {len(candidates)} candidates",
            log_queue,
        )

        def _count_processed(
            candidate: ActivationCandidate,
            success: bool,
        ) -> None:
            nonlocal processed_count
            processed_count += 1

        result = process_current_account(
            page_size=page_size,
            sleep_min_seconds=sleep_min_seconds,
            sleep_max_seconds=sleep_max_seconds,
            dry_run=False,
            yes=True,
            product_types=product_types,
            max_age_days=max_age_days,
            telegram_date_backfill_limit=telegram_date_backfill_limit,
            telegram_date_backfill_batch_size=telegram_date_backfill_batch_size,
            telegram_date_backfill_sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
            telegram_date_backfill_sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
            clear_telegram_dates_limit=clear_telegram_dates_limit,
            candidates=candidates,
            on_candidate_processed=_count_processed,
            account_name=session.name,
            progress_every=progress_every,
            verify_activation_flow=verify_activation_flow,
            print_candidate_list=False,
            live_log_func=lambda message: _emit_live_log(message, log_queue),
        )
        _emit_live_log(
            f"Worker finished for account {session.name}: "
            f"activated={result['activated']} "
            f"failed={result['failed']} mark_failed={result['mark_failed']}",
            log_queue,
        )
    except Exception as exc:
        _emit_live_log(
            f"Worker failed for account {session_data.get('name')}: {exc}",
            log_queue,
        )
        return {
            "ok": False,
            "error": str(exc),
            "processed_count": processed_count,
            "activated": 0,
            "failed": 0,
            "mark_failed": 0,
            "date_backfill_checked": 0,
            "date_loaded_from_telegram": 0,
            "date_load_failed": 0,
            "log": "",
        }
    return {
        "ok": True,
        "error": "",
        "processed_count": processed_count,
        "activated": result["activated"],
        "failed": result["failed"],
        "mark_failed": result["mark_failed"],
        "date_backfill_checked": int(result.get("date_backfill_checked", 0)),
        "date_loaded_from_telegram": int(result.get("date_loaded_from_telegram", 0)),
        "date_load_failed": int(result.get("date_load_failed", 0)),
        "log": "",
    }


def _collect_all_account_candidates_sequential(
    sessions: list[AccountSession],
    page_size: int,
    product_types: list[str],
    max_age_days: int,
    telegram_date_backfill_limit: int,
    telegram_date_backfill_batch_size: int,
    telegram_date_backfill_sleep_min_seconds: float,
    telegram_date_backfill_sleep_max_seconds: float,
    clear_telegram_dates_limit: int,
) -> tuple[list[tuple[AccountSession, list[ActivationCandidate]]], int, int, dict[str, int]]:
    collected: list[tuple[AccountSession, list[ActivationCandidate]]] = []
    accounts_failed = 0
    accounts_auth_failed = 0
    backfill_totals = _empty_backfill_stats()
    for index, session in enumerate(sessions, start=1):
        _print_account_header(index, len(sessions), session, phase="activation collection")
        try:
            _apply_account_environment(session)
            account_backfill_stats = _empty_backfill_stats()
            candidates = collect_current_account_candidates(
                page_size=page_size,
                product_types=product_types,
                max_age_days=max_age_days,
                telegram_date_backfill_limit=telegram_date_backfill_limit,
                telegram_date_backfill_batch_size=telegram_date_backfill_batch_size,
                telegram_date_backfill_sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
                telegram_date_backfill_sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
                clear_telegram_dates_limit=clear_telegram_dates_limit,
                backfill_stats=account_backfill_stats,
            )
            _add_backfill_stats(backfill_totals, account_backfill_stats)
        except Exception as exc:
            if _is_shafa_auth_error_message(exc):
                accounts_auth_failed += 1
                print(f"WARN: account skipped, Shafa session is not authenticated: {exc}")
                continue
            accounts_failed += 1
            print(f"ERROR: account collection failed: {exc}")
            continue
        print(f"Кандидатов для аккаунта: {len(candidates)}")
        collected.append((session, candidates))
    return collected, accounts_failed, accounts_auth_failed, backfill_totals


def _collect_all_account_candidates_parallel(
    sessions: list[AccountSession],
    page_size: int,
    product_types: list[str],
    max_age_days: int,
    telegram_date_backfill_limit: int,
    telegram_date_backfill_batch_size: int,
    telegram_date_backfill_sleep_min_seconds: float,
    telegram_date_backfill_sleep_max_seconds: float,
    clear_telegram_dates_limit: int,
    max_workers: int,
) -> tuple[list[tuple[AccountSession, list[ActivationCandidate]]], int, int, dict[str, int]]:
    collected: list[tuple[AccountSession, list[ActivationCandidate]]] = []
    accounts_failed = 0
    accounts_auth_failed = 0
    backfill_totals = _empty_backfill_stats()
    worker_count = _clamped_workers(max_workers, len(sessions))
    future_to_session: dict[concurrent.futures.Future, tuple[int, AccountSession]] = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
        for index, session in enumerate(sessions, start=1):
            future = executor.submit(
                collect_account_candidates_worker,
                _session_to_data(session),
                page_size,
                product_types,
                max_age_days,
                telegram_date_backfill_limit,
                telegram_date_backfill_batch_size,
                telegram_date_backfill_sleep_min_seconds,
                telegram_date_backfill_sleep_max_seconds,
                clear_telegram_dates_limit,
            )
            future_to_session[future] = (index, session)

        for future in concurrent.futures.as_completed(future_to_session):
            index, session = future_to_session[future]
            _print_account_header(
                index,
                len(sessions),
                session,
                phase="activation collection",
            )
            try:
                result = future.result()
            except Exception as exc:
                if _is_shafa_auth_error_message(exc):
                    accounts_auth_failed += 1
                    print(f"WARN: account skipped, Shafa session is not authenticated: {exc}")
                    continue
                accounts_failed += 1
                print(f"ERROR: account collection failed: {exc}")
                continue

            log_text = str(result.get("log") or "")
            if log_text:
                print(log_text, end="" if log_text.endswith("\n") else "\n")
            if not result.get("ok"):
                result_stats = result.get("backfill_stats")
                if isinstance(result_stats, dict):
                    _add_backfill_stats(backfill_totals, result_stats)
                if result.get("auth_failed"):
                    accounts_auth_failed += 1
                    print(
                        "WARN: account skipped, Shafa session is not authenticated: "
                        f"{result.get('error')}"
                    )
                    continue
                accounts_failed += 1
                print(f"ERROR: account collection failed: {result.get('error')}")
                continue
            result_stats = result.get("backfill_stats")
            if isinstance(result_stats, dict):
                _add_backfill_stats(backfill_totals, result_stats)
            candidates = [
                _candidate_from_data(candidate)
                for candidate in result.get("candidates", [])
                if isinstance(candidate, dict)
            ]
            print(f"Кандидатов для аккаунта: {len(candidates)}")
            collected.append((session, candidates))
    return collected, accounts_failed, accounts_auth_failed, backfill_totals


def _print_all_account_summary(
    *,
    accounts_folders_count: int,
    accounts_processed: int,
    accounts_failed: int,
    accounts_auth_skipped: int,
    total_candidates: int,
    total_activated: int,
    total_failed: int,
    total_mark_failed: int,
    remaining: int,
    date_backfill_checked: int = 0,
    date_loaded_from_telegram: int = 0,
    date_load_failed: int = 0,
) -> None:
    print(
        "Summary. "
        f"Accounts folders found: {accounts_folders_count}. "
        f"Accounts processed: {accounts_processed}. "
        f"Accounts failed: {accounts_failed}. "
        f"Accounts auth skipped: {accounts_auth_skipped}. "
        f"Total candidates: {total_candidates}. "
        f"Total activated: {total_activated}. "
        f"Total failed: {total_failed}. "
        f"Total local mark_failed: {total_mark_failed}. "
        f"Date backfill checked: {date_backfill_checked}. "
        f"Date loaded from Telegram: {date_loaded_from_telegram}. "
        f"Date load failed: {date_load_failed}. "
        f"Remaining: {remaining}."
    )


def process_all_accounts(
    *,
    accounts_folders_count: int,
    sessions: list[AccountSession],
    page_size: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    dry_run: bool,
    yes: bool,
    parallel_accounts: bool,
    max_workers: int,
    progress_every: int,
    verify_activation_flow: bool,
    product_types: list[str],
    max_age_days: int,
    telegram_date_backfill_limit: int,
    telegram_date_backfill_batch_size: int,
    telegram_date_backfill_sleep_min_seconds: float,
    telegram_date_backfill_sleep_max_seconds: float,
    clear_telegram_dates_limit: int,
) -> None:
    backfill_totals = _empty_backfill_stats()
    accounts_auth_skipped = 0
    if parallel_accounts:
        (
            collected,
            accounts_failed,
            accounts_auth_skipped,
            backfill_totals,
        ) = _collect_all_account_candidates_parallel(
            sessions=sessions,
            page_size=page_size,
            product_types=product_types,
            max_age_days=max_age_days,
            telegram_date_backfill_limit=telegram_date_backfill_limit,
            telegram_date_backfill_batch_size=telegram_date_backfill_batch_size,
            telegram_date_backfill_sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
            telegram_date_backfill_sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
            clear_telegram_dates_limit=clear_telegram_dates_limit,
            max_workers=max_workers,
        )
    else:
        (
            collected,
            accounts_failed,
            accounts_auth_skipped,
            backfill_totals,
        ) = _collect_all_account_candidates_sequential(
            sessions=sessions,
            page_size=page_size,
            product_types=product_types,
            max_age_days=max_age_days,
            telegram_date_backfill_limit=telegram_date_backfill_limit,
            telegram_date_backfill_batch_size=telegram_date_backfill_batch_size,
            telegram_date_backfill_sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
            telegram_date_backfill_sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
            clear_telegram_dates_limit=clear_telegram_dates_limit,
        )

    total_candidates = sum(len(candidates) for _, candidates in collected)
    remaining = total_candidates
    print(f"Всего товаров к активации по всем аккаунтам: {total_candidates}")

    if dry_run:
        for index, (session, candidates) in enumerate(collected, start=1):
            _print_account_header(index, len(collected), session, phase="activation dry-run")
            print_candidates(candidates)
        _print_all_account_summary(
            accounts_folders_count=accounts_folders_count,
            accounts_processed=len(collected),
            accounts_failed=accounts_failed,
            accounts_auth_skipped=accounts_auth_skipped,
            total_candidates=total_candidates,
            total_activated=0,
            total_failed=0,
            total_mark_failed=0,
            remaining=remaining,
            date_backfill_checked=backfill_totals["date_backfill_checked"],
            date_loaded_from_telegram=backfill_totals["date_loaded_from_telegram"],
            date_load_failed=backfill_totals["date_load_failed"],
        )
        return

    if total_candidates == 0:
        _print_all_account_summary(
            accounts_folders_count=accounts_folders_count,
            accounts_processed=len(collected),
            accounts_failed=accounts_failed,
            accounts_auth_skipped=accounts_auth_skipped,
            total_candidates=total_candidates,
            total_activated=0,
            total_failed=0,
            total_mark_failed=0,
            remaining=remaining,
            date_backfill_checked=backfill_totals["date_backfill_checked"],
            date_loaded_from_telegram=backfill_totals["date_loaded_from_telegram"],
            date_load_failed=backfill_totals["date_load_failed"],
        )
        return

    if not verify_activation_flow and not yes and not confirm_activation(total_candidates):
        print("Отменено.")
        _print_all_account_summary(
            accounts_folders_count=accounts_folders_count,
            accounts_processed=len(collected),
            accounts_failed=accounts_failed,
            accounts_auth_skipped=accounts_auth_skipped,
            total_candidates=total_candidates,
            total_activated=0,
            total_failed=0,
            total_mark_failed=0,
            remaining=remaining,
            date_backfill_checked=backfill_totals["date_backfill_checked"],
            date_loaded_from_telegram=backfill_totals["date_loaded_from_telegram"],
            date_load_failed=backfill_totals["date_load_failed"],
        )
        return

    total_activated = 0
    total_failed = 0
    total_mark_failed = 0

    if parallel_accounts:
        worker_count = _clamped_workers(max_workers, len(collected))
        processed_candidates = 0
        completed_accounts = 0
        future_to_session: dict[
            concurrent.futures.Future,
            tuple[int, AccountSession],
        ] = {}
        with multiprocessing.Manager() as manager:
            live_log_queue = manager.Queue()
            with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
                for index, (session, candidates) in enumerate(collected, start=1):
                    submitted_count = min(len(candidates), 3) if verify_activation_flow else len(candidates)
                    print(
                        f"Submitting account {session.name} with {submitted_count} candidates",
                        flush=True,
                    )
                    future = executor.submit(
                        process_account_worker,
                        _session_to_data(session),
                        page_size,
                        sleep_min_seconds,
                        sleep_max_seconds,
                        product_types,
                        max_age_days,
                        telegram_date_backfill_limit,
                        telegram_date_backfill_batch_size,
                        telegram_date_backfill_sleep_min_seconds,
                        telegram_date_backfill_sleep_max_seconds,
                        clear_telegram_dates_limit,
                        [_candidate_to_data(candidate) for candidate in candidates],
                        progress_every,
                        verify_activation_flow,
                        live_log_queue,
                    )
                    future_to_session[future] = (index, session)

                while future_to_session:
                    done, _ = concurrent.futures.wait(
                        future_to_session,
                        timeout=0.5,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    _drain_live_log_queue(live_log_queue)
                    if not done:
                        continue
                    for future in done:
                        index, session = future_to_session.pop(future)
                        completed_accounts += 1
                        _print_account_header(
                            index,
                            len(collected),
                            session,
                            phase="activation",
                        )
                        try:
                            result = future.result()
                        except Exception as exc:
                            accounts_failed += 1
                            remaining = max(total_candidates - processed_candidates, 0)
                            print(f"ERROR: account failed: {exc}", flush=True)
                            continue

                        processed_count = int(result.get("processed_count") or 0)
                        processed_candidates += processed_count
                        if not result.get("ok"):
                            accounts_failed += 1
                            remaining = max(total_candidates - processed_candidates, 0)
                            print(f"ERROR: account failed: {result.get('error')}", flush=True)
                            continue

                        total_activated += int(result.get("activated") or 0)
                        total_failed += int(result.get("failed") or 0)
                        total_mark_failed += int(result.get("mark_failed") or 0)
                        backfill_totals["date_backfill_checked"] += int(
                            result.get("date_backfill_checked") or 0
                        )
                        backfill_totals["date_loaded_from_telegram"] += int(
                            result.get("date_loaded_from_telegram") or 0
                        )
                        backfill_totals["date_load_failed"] += int(
                            result.get("date_load_failed") or 0
                        )
                        remaining = max(total_candidates - processed_candidates, 0)
                        print(
                            "Глобально обработано аккаунтов: "
                            f"{completed_accounts}/{len(collected)}. "
                            f"Осталось товаров примерно: {remaining}",
                            flush=True,
                        )
                _drain_live_log_queue(live_log_queue)
    else:
        for index, (session, candidates) in enumerate(collected, start=1):
            _print_account_header(index, len(collected), session, phase="activation")

            def _decrement_remaining(
                candidate: ActivationCandidate,
                success: bool,
            ) -> None:
                nonlocal remaining
                remaining = max(remaining - 1, 0)
                print(f"Осталось товаров к активации: {remaining}")

            try:
                _apply_account_environment(session)
                effective_candidates = candidates[:3] if verify_activation_flow else candidates
                result = process_current_account(
                    page_size=page_size,
                    sleep_min_seconds=sleep_min_seconds,
                    sleep_max_seconds=sleep_max_seconds,
                    dry_run=False,
                    yes=True,
                    product_types=product_types,
                    max_age_days=max_age_days,
                    telegram_date_backfill_limit=telegram_date_backfill_limit,
                    telegram_date_backfill_batch_size=telegram_date_backfill_batch_size,
                    telegram_date_backfill_sleep_min_seconds=telegram_date_backfill_sleep_min_seconds,
                    telegram_date_backfill_sleep_max_seconds=telegram_date_backfill_sleep_max_seconds,
                    clear_telegram_dates_limit=clear_telegram_dates_limit,
                    candidates=effective_candidates,
                    on_candidate_processed=_decrement_remaining,
                    account_name=session.name,
                    progress_every=progress_every,
                    verify_activation_flow=verify_activation_flow,
                    print_candidate_list=False,
                )
            except Exception as exc:
                accounts_failed += 1
                print(f"ERROR: account failed: {exc}")
                continue
            total_activated += result["activated"]
            total_failed += result["failed"]
            total_mark_failed += result["mark_failed"]
            backfill_totals["date_backfill_checked"] += int(
                result.get("date_backfill_checked") or 0
            )
            backfill_totals["date_loaded_from_telegram"] += int(
                result.get("date_loaded_from_telegram") or 0
            )
            backfill_totals["date_load_failed"] += int(
                result.get("date_load_failed") or 0
            )

    _print_all_account_summary(
        accounts_folders_count=accounts_folders_count,
        accounts_processed=len(collected),
        accounts_failed=accounts_failed,
        accounts_auth_skipped=accounts_auth_skipped,
        total_candidates=total_candidates,
        total_activated=total_activated,
        total_failed=total_failed,
        total_mark_failed=total_mark_failed,
        remaining=remaining,
        date_backfill_checked=backfill_totals["date_backfill_checked"],
        date_loaded_from_telegram=backfill_totals["date_loaded_from_telegram"],
        date_load_failed=backfill_totals["date_load_failed"],
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Активирует неактивные/деактивированные товары Shafa, если их "
            "Telegram-сообщение младше половины года."
        )
    )
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--sleep-min", type=float, default=DEFAULT_ACTIVATION_SLEEP_MIN_SECONDS)
    parser.add_argument("--sleep-max", type=float, default=DEFAULT_ACTIVATION_SLEEP_MAX_SECONDS)
    parser.add_argument("--max-age-days", type=int, default=HALF_YEAR_DAYS)
    parser.add_argument(
        "--telegram-date-backfill-limit",
        type=int,
        default=DEFAULT_TELEGRAM_DATE_BACKFILL_LIMIT,
        help=(
            "Общий лимит товаров, для которых дата сообщения refresh-ится из Telegram "
            "перед расчётом возраста. 0 отключает Telegram refresh."
        ),
    )
    parser.add_argument(
        "--telegram-date-backfill-batch-size",
        type=int,
        default=DEFAULT_TELEGRAM_DATE_BACKFILL_BATCH_SIZE,
        help="Размер одной партии Telegram date refresh.",
    )
    parser.add_argument(
        "--telegram-date-backfill-sleep-min",
        type=float,
        default=30.0,
        help="Минимальная пауза между партиями Telegram date refresh.",
    )
    parser.add_argument(
        "--telegram-date-backfill-sleep-max",
        type=float,
        default=60.0,
        help="Максимальная пауза между партиями Telegram date refresh.",
    )
    parser.add_argument(
        "--clear-telegram-dates-limit",
        type=int,
        default=0,
        help=(
            "Тестовый режим: очистить telegram_message_date у N связанных товаров "
            "перед backfill. Меняет DB."
        ),
    )
    parser.add_argument(
        "--telegram-id",
        "--channel-id",
        dest="telegram_id",
        type=int,
        help="Telegram channel/chat id for one exact product.",
    )
    parser.add_argument(
        "--message-id",
        type=int,
        help="Telegram message id for one exact product.",
    )
    parser.add_argument(
        "--products-type",
        action="append",
        default=None,
        help=(
            "Тип товаров в Shafa feed. По умолчанию: INACTIVE. "
            "Можно указать несколько раз. DEACTIVATED принимается как alias INACTIVE."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Не спрашивать подтверждение",
    )
    parser.add_argument(
        "--account-id",
        help="ID или точное имя аккаунта из папки accounts/",
    )
    parser.add_argument(
        "--exclude-account-id",
        action="append",
        default=None,
        help=(
            "Исключить аккаунт при --all-accounts. Можно указать несколько раз. "
            "Принимает ID, префикс ID или точное имя аккаунта."
        ),
    )
    parser.add_argument(
        "--all-accounts",
        action="store_true",
        help="Обработать все найденные аккаунты Shafa.",
    )
    parser.add_argument(
        "--parallel-accounts",
        action="store_true",
        help="Обрабатывать несколько аккаунтов параллельно. Только с --all-accounts.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_ACCOUNT_WORKERS,
        help="Максимум аккаунтов, обрабатываемых одновременно.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Печатать прогресс активации каждые N товаров.",
    )
    parser.add_argument(
        "--verify-activation-flow",
        action="store_true",
        help="Проверить parallel/progress flow без реальной активации.",
    )
    parser.add_argument(
        "--accounts-search-root",
        action="append",
        default=None,
        help="Корень для рекурсивного поиска папок accounts/. Можно указать несколько раз.",
    )
    parser.add_argument(
        "--accounts-dir",
        action="append",
        default=None,
        help="Явная папка accounts/. Можно указать несколько раз.",
    )
    parser.add_argument(
        "--debug-auth",
        action="store_true",
        help="Печатать диагностику auth.json/cookies для Shafa-запросов.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    try:
        if args.all_accounts and args.account_id:
            raise RuntimeError("--all-accounts и --account-id нельзя использовать вместе")
        direct_telegram_mode = (
            args.telegram_id is not None or args.message_id is not None
        )
        if direct_telegram_mode and (
            args.telegram_id is None or args.message_id is None
        ):
            raise RuntimeError("--telegram-id и --message-id нужно указывать вместе")
        if direct_telegram_mode and args.all_accounts:
            raise RuntimeError("--telegram-id/--message-id работает только с одним аккаунтом")
        if args.parallel_accounts and not args.all_accounts:
            raise RuntimeError(
                "--parallel-accounts можно использовать только вместе с --all-accounts"
            )
        if args.sleep_min > args.sleep_max:
            raise RuntimeError("--sleep-min не может быть больше --sleep-max")
        if args.max_age_days < 1:
            raise RuntimeError("--max-age-days должен быть >= 1")
        if args.telegram_date_backfill_limit < 0:
            raise RuntimeError("--telegram-date-backfill-limit должен быть >= 0")
        if args.telegram_date_backfill_batch_size < 1:
            raise RuntimeError("--telegram-date-backfill-batch-size должен быть >= 1")
        if args.telegram_date_backfill_sleep_min < 0:
            raise RuntimeError("--telegram-date-backfill-sleep-min должен быть >= 0")
        if args.telegram_date_backfill_sleep_min > args.telegram_date_backfill_sleep_max:
            raise RuntimeError(
                "--telegram-date-backfill-sleep-min не может быть больше "
                "--telegram-date-backfill-sleep-max"
            )
        if args.clear_telegram_dates_limit < 0:
            raise RuntimeError("--clear-telegram-dates-limit должен быть >= 0")
        if args.debug_auth:
            os.environ["SHAFA_DEBUG_AUTH"] = "1"

        progress_every = max(int(args.progress_every), 1)
        product_types = [
            normalize_products_type(item)
            for item in (args.products_type or list(DEFAULT_PRODUCT_TYPES))
            if normalize_products_type(item)
        ]
        product_types = list(dict.fromkeys(product_types))
        if not product_types:
            raise RuntimeError("Укажите хотя бы один --products-type")

        if args.all_accounts:
            accounts_folders = find_all_accounts_dirs(
                accounts_dirs=args.accounts_dir,
                accounts_search_roots=args.accounts_search_root,
            )
            sessions = list_account_sessions(accounts_dirs=accounts_folders)
            sessions = filter_excluded_sessions(sessions, args.exclude_account_id)
            if not sessions:
                raise RuntimeError(
                    "Не нашёл сохранённые cookies Shafa. Войди в аккаунт через "
                    "desktop UI или через `./venv/bin/python shafa_logic/main.py`."
                )

            process_all_accounts(
                accounts_folders_count=len(accounts_folders),
                sessions=sessions,
                page_size=args.page_size,
                sleep_min_seconds=args.sleep_min,
                sleep_max_seconds=args.sleep_max,
                dry_run=args.dry_run,
                yes=args.yes,
                parallel_accounts=args.parallel_accounts,
                max_workers=args.max_workers,
                progress_every=progress_every,
                verify_activation_flow=args.verify_activation_flow,
                product_types=product_types,
                max_age_days=args.max_age_days,
                telegram_date_backfill_limit=args.telegram_date_backfill_limit,
                telegram_date_backfill_batch_size=args.telegram_date_backfill_batch_size,
                telegram_date_backfill_sleep_min_seconds=args.telegram_date_backfill_sleep_min,
                telegram_date_backfill_sleep_max_seconds=args.telegram_date_backfill_sleep_max,
                clear_telegram_dates_limit=args.clear_telegram_dates_limit,
            )
            return

        selected_account = configure_account_environment(
            args.account_id,
            accounts_dirs=args.accounts_dir,
            accounts_search_roots=args.accounts_search_root,
        )
        if selected_account is not None:
            _apply_account_environment(selected_account)
            print(
                "Аккаунт Shafa: "
                f"{selected_account.name} | {selected_account.account_id}"
            )

        candidates = None
        if direct_telegram_mode:
            candidate = select_product_for_activation_by_telegram_identity(
                telegram_id=args.telegram_id,
                message_id=args.message_id,
                max_age_days=args.max_age_days,
                telegram_date_backfill_batch_size=args.telegram_date_backfill_batch_size,
                telegram_date_backfill_sleep_min_seconds=args.telegram_date_backfill_sleep_min,
                telegram_date_backfill_sleep_max_seconds=args.telegram_date_backfill_sleep_max,
            )
            candidates = [] if candidate is None else [candidate]

        process_current_account(
            page_size=args.page_size,
            sleep_min_seconds=args.sleep_min,
            sleep_max_seconds=args.sleep_max,
            dry_run=args.dry_run,
            yes=args.yes,
            account_name=selected_account.name if selected_account is not None else "",
            progress_every=progress_every,
            verify_activation_flow=args.verify_activation_flow,
            product_types=product_types,
            max_age_days=args.max_age_days,
            telegram_date_backfill_limit=args.telegram_date_backfill_limit,
            telegram_date_backfill_batch_size=args.telegram_date_backfill_batch_size,
            telegram_date_backfill_sleep_min_seconds=args.telegram_date_backfill_sleep_min,
            telegram_date_backfill_sleep_max_seconds=args.telegram_date_backfill_sleep_max,
            clear_telegram_dates_limit=args.clear_telegram_dates_limit,
            candidates=candidates,
        )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
