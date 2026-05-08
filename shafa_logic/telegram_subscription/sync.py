from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Iterable
from urllib.parse import urlparse

from .telegram_channels import (
    extract_telegram_invite_hash,
    normalize_channel_link,
    parse_id_bot_response,
)

from .client import create_telegram_client

if TYPE_CHECKING:
    from telethon import TelegramClient

ID_BOT_USERNAME = "id_bot"
RUNTIME_CONFIG_ENV = "SHAFA_TELEGRAM_CHANNEL_LINKS_FILE"
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,}$")
DEFAULT_CHANNEL_ALIAS = "main extra_photos"


def _normalize_channel_alias(alias: object) -> str:
    raw_alias = str(alias).strip()
    tokens = [token for token in re.split(r"\s+", raw_alias) if token]
    if not tokens:
        tokens = ["main"]
    if "main" not in tokens:
        tokens.insert(0, "main")
    if "extra_photos" not in tokens:
        tokens.append("extra_photos")
    return " ".join(tokens)


def sync_channels_from_runtime_config() -> list[tuple[int, str, str]]:
    config_path = os.getenv(RUNTIME_CONFIG_ENV, "").strip()
    if not config_path:
        return []

    links = load_channel_links(Path(config_path))
    if not links:
        return []

    existing_records = get_telegram_channel_records()
    existing_by_source_link = {
        _channel_link_key(record.get("source_link")): record
        for record in existing_records
        if _channel_link_key(record.get("source_link"))
    }
    missing_links = [
        link for link in links if _channel_link_key(link) not in existing_by_source_link
    ]

    try:
        resolved_records = (
            asyncio.run(_resolve_channel_records(missing_links)) if missing_links else []
        )
    except RuntimeError as exc:
        fallback_records = _select_records_for_links(links, existing_records)
        if not fallback_records and not _has_source_linked_records(existing_records):
            fallback_records = list(existing_records)
        fallback_channels = _records_to_channel_tuples(fallback_records)
        if fallback_channels:
            _log(
                "channel sync skipped because Telegram session is unavailable; "
                f"reusing {len(fallback_channels)} saved channel(s): {exc}"
            )
            return fallback_channels
        raise
    merged_records = {int(record["channel_id"]): record for record in existing_records}
    for record in resolved_records:
        merged_records[int(record["channel_id"])] = record

    selected_records = _select_records_for_links(links, merged_records.values())
    if selected_records:
        set_telegram_channels(selected_records)
    elif existing_records and _has_source_linked_records(existing_records):
        set_telegram_channels([])

    unresolved_links = max(len(links) - len(selected_records), 0)
    if resolved_records:
        _log(
            f"synced {len(resolved_records)} new channel(s); "
            f"configured existing channels: {len(selected_records)}"
        )
    elif missing_links and not selected_records:
        _log("no channels resolved from runtime config")

    if unresolved_links:
        _log(
            "some configured links were skipped because they are not resolved locally: "
            f"{unresolved_links}"
        )

    return _records_to_channel_tuples(selected_records)


def get_telegram_channel_records(path: Path | None = None) -> list[dict]:
    if path is None:
        path = _runtime_channels_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    records: list[dict] = []
    for item in payload:
        record = _normalize_channel_record(item)
        if record is None:
            continue
        records.append(record)
    return records


def get_telegram_channels(path: Path | None = None) -> list[tuple[int, str, str]]:
    return [
        (
            int(record["channel_id"]),
            str(record["name"]),
            str(record["alias"]),
        )
        for record in get_telegram_channel_records(path=path)
    ]


def get_configured_telegram_channel_records(path: Path | None = None) -> list[dict]:
    links = _load_runtime_channel_links()
    records = get_telegram_channel_records(path=path)
    if not links:
        return records
    if not _has_source_linked_records(records):
        return records
    return _select_records_for_links(links, records)


def get_configured_telegram_channels(
    path: Path | None = None,
) -> list[tuple[int, str, str]]:
    return _records_to_channel_tuples(get_configured_telegram_channel_records(path=path))


def set_telegram_channels(
    channels: Iterable[tuple[int, str, str] | tuple[int, str, str, str] | dict],
    path: Path | None = None,
) -> None:
    if path is None:
        path = _runtime_channels_path()
    normalized: list[dict[str, object]] = []
    db_rows: list[tuple[int, str, str]] = []
    for item in channels:
        record = _normalize_channel_record(item)
        if record is None:
            continue
        normalized.append(record)
        db_rows.append(
            (
                int(record["channel_id"]),
                str(record["name"]),
                str(record["alias"]),
            )
        )

    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    _mirror_channels_to_db(db_rows)


def load_channel_links(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    links = raw.get("links") or []
    return [str(link).strip() for link in links if str(link).strip()]


async def _resolve_channel_tuples(links: list[str]) -> list[tuple[int, str, str]]:
    records = await _resolve_channel_records(links)
    return [
        (
            int(record["channel_id"]),
            str(record["name"]),
            str(record["alias"]),
        )
        for record in records
    ]


async def _resolve_channel_records(links: list[str]) -> list[dict[str, object]]:
    api_id, api_hash = _require_telegram_credentials()
    telegram_client_cls = _get_telegram_client_cls()
    async with _connected_client(
        create_telegram_client(
            _telegram_session_path(),
            api_id,
            api_hash,
            save_entities=False,
            telegram_client_cls=telegram_client_cls,
        )
    ) as client:
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Сессия Telegram отсутствует или не авторизована. Переподключи аккаунт в интерфейсе."
            )
        channels: list[dict[str, object]] = []
        for link in links:
            resolved = await _resolve_single_channel(client, link)
            if resolved is None:
                continue
            source_link = _normalize_source_link(link)
            channels.append(
                {
                    "channel_id": int(resolved[0]),
                    "name": str(resolved[1]),
                    "alias": str(resolved[2]),
                    "source_link": source_link,
                }
            )
        return channels


async def _resolve_single_channel(
    client: "TelegramClient",
    link: str,
) -> tuple[int, str, str] | None:
    try:
        _log(f"resolving channel: {link}")
        entity = await _resolve_channel_entity(client, link)
        resolved_from_entity = _channel_tuple_from_entity(entity)
        if resolved_from_entity is not None:
            _log(f"resolved {link} directly via entity: id={resolved_from_entity[0]}, title={resolved_from_entity[1]!r}")
            return resolved_from_entity
        response_text = await _fetch_id_bot_response(client, link)
        _log(f"bot response for {link}: {response_text!r}")
        channel_id, title = parse_id_bot_response(response_text)
        return (channel_id, title, DEFAULT_CHANNEL_ALIAS)
    except Exception as exc:
        _log(f"failed to resolve {link}: {exc}")
        return None


async def _fetch_id_bot_response(client: "TelegramClient", link: str) -> str:
    async with client.conversation(ID_BOT_USERNAME) as conversation:
        await conversation.send_message(link)
        response = await conversation.get_response()
    return response.raw_text


async def _resolve_channel_entity(client: "TelegramClient", link: str) -> object | None:
    invite_hash = extract_telegram_invite_hash(link)
    if invite_hash:
        entity = await _resolve_invite_entity(client, invite_hash, link)
        if entity is not None:
            return entity
    return await _ensure_channel_membership(client, link)


async def _resolve_invite_entity(
    client: "TelegramClient",
    invite_hash: str,
    link: str,
) -> object | None:
    from telethon.errors import RPCError
    from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest

    try:
        invite_info = await client(CheckChatInviteRequest(invite_hash))
    except RPCError as exc:
        _log(f"invite check failed for {link}: {exc}")
    else:
        entity = getattr(invite_info, "chat", None)
        if entity is not None:
            _log(f"invite resolved without import for {link}")
            return entity

    try:
        result = await client(ImportChatInviteRequest(invite_hash))
    except RPCError as exc:
        message = str(exc).upper()
        if "USER_ALREADY_PARTICIPANT" not in message:
            _log(f"invite import failed for {link}: {exc}")
            return None
        try:
            invite_info = await client(CheckChatInviteRequest(invite_hash))
        except RPCError as nested_exc:
            _log(f"invite re-check failed for {link}: {nested_exc}")
            return None
        entity = getattr(invite_info, "chat", None)
        if entity is not None:
            _log(f"invite already joined for {link}")
        return entity

    chats = getattr(result, "chats", None) or []
    if chats:
        _log(f"joined invite channel for {link}")
        return chats[0]
    entity = getattr(result, "chat", None)
    if entity is not None:
        _log(f"joined invite channel for {link}")
    return entity


async def _ensure_channel_membership(client: "TelegramClient", link: str) -> None:
    from telethon.errors import RPCError
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.functions.contacts import SearchRequest

    query = _extract_search_query(link)
    if not query:
        return

    candidates = [query]
    normalized_query = query.lstrip("@")
    if normalized_query != query:
        candidates.append(normalized_query)

    entity = None
    for candidate in candidates:
        try:
            result = await client(SearchRequest(q=candidate, limit=10))
        except RPCError as exc:
            _log(f"search failed for {link}: {exc}")
            continue

        chats = getattr(result, "chats", None) or []
        if chats:
            entity = chats[0]
            _log(f"search matched {link} -> {getattr(entity, 'title', None) or getattr(entity, 'username', None) or 'unknown'}")
            break

    if entity is None:
        _log(f"no search results for {link}")
        return None

    try:
        await client(JoinChannelRequest(entity))
        _log(f"joined/subscribed to {link}")
    except RPCError as exc:
        message = str(exc).upper()
        if "USER_ALREADY_PARTICIPANT" in message:
            _log(f"already joined {link}")
            return entity
        _log(f"join failed for {link}: {exc}")
    return entity


def _channel_tuple_from_entity(entity: object | None) -> tuple[int, str, str] | None:
    if entity is None:
        return None
    raw_title = getattr(entity, "title", None)
    if not isinstance(raw_title, str) or not raw_title.strip():
        raw_title = getattr(entity, "username", None)
    if not isinstance(raw_title, str):
        return None
    title = raw_title.strip()
    if not title:
        return None
    try:
        channel_id = int(_get_peer_id(entity))
    except Exception:
        raw_id = getattr(entity, "id", None)
        if not isinstance(raw_id, int):
            return None
        channel_id = int(raw_id)
    return (channel_id, title, DEFAULT_CHANNEL_ALIAS)


def _get_peer_id(entity: object) -> int:
    from telethon.utils import get_peer_id

    return int(get_peer_id(entity))


def _extract_search_query(link: str) -> str:
    value = link.strip()
    if not value:
        return ""
    if "://" not in value:
        if USERNAME_PATTERN.fullmatch(value.lstrip("@")):
            return value if value.startswith("@") else f"@{value}"
        value = f"https://{value}"

    parsed = urlparse(value)
    path = (parsed.path or "").strip("/")
    if not path:
        return parsed.netloc
    first_part = path.split("/", 1)[0]
    if first_part in {"joinchat", "c", "s"} and "/" in path:
        return path.split("/", 1)[1]
    return first_part if first_part.startswith("@") else f"@{first_part}"


def _mirror_channels_to_db(channels: list[tuple[int, str, str]]) -> None:
    if channels:
        _log("legacy telegram_channels DB mirror skipped")


def _require_telegram_credentials() -> tuple[int, str]:
    from data.const import TELEGRAM_API_HASH, TELEGRAM_API_ID

    if TELEGRAM_API_ID is None or not TELEGRAM_API_HASH:
        raise RuntimeError(
            "Missing Telegram credentials. "
            "Set SHAFA_TELEGRAM_API_ID and SHAFA_TELEGRAM_API_HASH."
        )
    return int(TELEGRAM_API_ID), TELEGRAM_API_HASH


def _get_telegram_client_cls():
    from telethon import TelegramClient

    return TelegramClient


class _connected_client:
    def __init__(self, client) -> None:
        self.client = client

    async def __aenter__(self):
        await self.client.connect()
        return self.client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.client.disconnect()


def _runtime_channels_path() -> Path:
    from data.const import TELEGRAM_CHANNELS_RUNTIME_PATH

    return TELEGRAM_CHANNELS_RUNTIME_PATH


def _telegram_session_path() -> Path:
    from data.const import TELEGRAM_SESSION_PATH

    return TELEGRAM_SESSION_PATH


def _log(message: str) -> None:
    line = f"[telegram_subscription] {message}"
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"

    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _normalize_source_link(source_link: object) -> str | None:
    text = str(source_link or "").strip()
    if not text:
        return None
    try:
        return normalize_channel_link(text)
    except ValueError:
        return text


def _channel_link_key(source_link: object) -> str:
    normalized = _normalize_source_link(source_link)
    return normalized.casefold() if normalized else ""


def _load_runtime_channel_links() -> list[str]:
    config_path = os.getenv(RUNTIME_CONFIG_ENV, "").strip()
    if not config_path:
        return []
    path = Path(config_path)
    if not path.exists():
        return []
    try:
        return load_channel_links(path)
    except (OSError, json.JSONDecodeError):
        return []


def _records_to_channel_tuples(records: Iterable[dict]) -> list[tuple[int, str, str]]:
    return [
        (
            int(record["channel_id"]),
            str(record["name"]),
            str(record["alias"]),
        )
        for record in records
    ]


def _select_records_for_links(
    links: Iterable[str],
    records: Iterable[dict],
) -> list[dict[str, object]]:
    records_by_link = {
        _channel_link_key(record.get("source_link")): record
        for record in records
        if _channel_link_key(record.get("source_link"))
    }
    selected: list[dict[str, object]] = []
    seen_channel_ids: set[int] = set()
    for link in links:
        key = _channel_link_key(link)
        if not key:
            continue
        record = records_by_link.get(key)
        if record is None:
            continue
        channel_id = int(record["channel_id"])
        if channel_id in seen_channel_ids:
            continue
        seen_channel_ids.add(channel_id)
        selected.append(record)
    return selected


def _has_source_linked_records(records: Iterable[dict]) -> bool:
    for record in records:
        if _channel_link_key(record.get("source_link")):
            return True
    return False


def _normalize_channel_record(
    item: tuple[int, str, str] | tuple[int, str, str, str] | dict | object,
) -> dict[str, object] | None:
    if isinstance(item, dict):
        channel_id = item.get("channel_id")
        name = item.get("name", item.get("title"))
        alias = item.get("alias")
        source_link = item.get("source_link")
    elif isinstance(item, (list, tuple)) and len(item) in {3, 4}:
        channel_id, name, alias = item[:3]
        source_link = item[3] if len(item) == 4 else None
    else:
        return None

    try:
        normalized_id = int(channel_id)
    except (TypeError, ValueError):
        return None
    name_text = str(name or "").strip()
    if not name_text:
        return None
    return {
        "channel_id": normalized_id,
        "name": name_text,
        "alias": _normalize_channel_alias(alias),
        "source_link": _normalize_source_link(source_link),
    }
