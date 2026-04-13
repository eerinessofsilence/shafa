from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Iterable
from urllib.parse import urlparse

if TYPE_CHECKING:
    from telethon import TelegramClient

ID_BOT_USERNAME = "id_bot"
RUNTIME_CONFIG_ENV = "SHAFA_TELEGRAM_CHANNEL_LINKS_FILE"
ID_PATTERN = re.compile(r"(?im)(?:^|\n)\s*.*?\b(?:chat\s+)?id\b\s*:\s*(-?\d+)")
TITLE_PATTERN = re.compile(r"(?im)(?:^|\n)\s*.*?\btitle\b\s*:\s*(.+)")
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,}$")


def sync_channels_from_runtime_config() -> list[tuple[int, str, str]]:
    config_path = os.getenv(RUNTIME_CONFIG_ENV, "").strip()
    if not config_path:
        return []

    links = load_channel_links(Path(config_path))
    if not links:
        return []

    channels = asyncio.run(_resolve_channel_tuples(links))
    if not channels:
        _log("no channels resolved, runtime storage was not updated")
        return []
    set_telegram_channels(channels)
    _log(f"synced {len(channels)} channel(s)")
    return channels


def get_telegram_channels(path: Path | None = None) -> list[tuple[int, str, str]]:
    if path is None:
        path = _runtime_channels_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    channels: list[tuple[int, str, str]] = []
    for item in payload:
        if not isinstance(item, list) or len(item) != 3:
            continue
        channel_id, title, alias = item
        try:
            normalized_id = int(channel_id)
        except (TypeError, ValueError):
            continue
        title_text = str(title).strip()
        alias_text = str(alias).strip() or "main"
        if not title_text:
            continue
        channels.append((normalized_id, title_text, alias_text))
    return channels


def set_telegram_channels(
    channels: Iterable[tuple[int, str, str]],
    path: Path | None = None,
) -> None:
    if path is None:
        path = _runtime_channels_path()
    normalized: list[list[object]] = []
    db_rows: list[tuple[int, str, str]] = []
    for channel_id, title, alias in channels:
        try:
            normalized_id = int(channel_id)
        except (TypeError, ValueError):
            continue
        title_text = str(title).strip()
        alias_text = str(alias).strip() or "main"
        if not title_text:
            continue
        normalized.append([normalized_id, title_text, alias_text])
        db_rows.append((normalized_id, title_text, alias_text))

    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    _mirror_channels_to_db(db_rows)


def load_channel_links(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    links = raw.get("links") or []
    return [str(link).strip() for link in links if str(link).strip()]


async def _resolve_channel_tuples(links: list[str]) -> list[tuple[int, str, str]]:
    api_id, api_hash = _require_telegram_credentials()
    telegram_client_cls = _get_telegram_client_cls()
    async with telegram_client_cls(str(_telegram_session_path()), api_id, api_hash) as client:
        channels: list[tuple[int, str, str]] = []
        for link in links:
            resolved = await _resolve_single_channel(client, link)
            if resolved is None:
                continue
            channels.append(resolved)
        return channels


async def _resolve_single_channel(
    client: "TelegramClient",
    link: str,
) -> tuple[int, str, str] | None:
    try:
        _log(f"resolving channel: {link}")
        await _ensure_channel_membership(client, link)
        response_text = await _fetch_id_bot_response(client, link)
        _log(f"bot response for {link}: {response_text!r}")
        channel_id, title = parse_id_bot_response(response_text)
        return (channel_id, title, "main")
    except Exception as exc:
        _log(f"failed to resolve {link}: {exc}")
        return None


async def _fetch_id_bot_response(client: "TelegramClient", link: str) -> str:
    async with client.conversation(ID_BOT_USERNAME) as conversation:
        await conversation.send_message(link)
        response = await conversation.get_response()
    return response.raw_text


def parse_id_bot_response(response_text: str) -> tuple[int, str]:
    channel_id_match = ID_PATTERN.search(response_text)
    title_match = TITLE_PATTERN.search(response_text)
    if channel_id_match is None:
        raise ValueError(
            "Could not extract channel ID from @id_bot response. "
            f"Raw response: {response_text!r}"
        )
    if title_match is None:
        raise ValueError(
            "Could not extract channel title from @id_bot response. "
            f"Raw response: {response_text!r}"
        )
    title = title_match.group(1).strip().splitlines()[0].strip()
    if not title:
        raise ValueError(
            "Could not extract channel title from @id_bot response. "
            f"Raw response: {response_text!r}"
        )
    return int(channel_id_match.group(1)), title


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
        return

    try:
        await client(JoinChannelRequest(entity))
        _log(f"joined/subscribed to {link}")
    except RPCError as exc:
        message = str(exc).upper()
        if "USER_ALREADY_PARTICIPANT" in message:
            _log(f"already joined {link}")
            return
        _log(f"join failed for {link}: {exc}")


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
    if not channels:
        return
    try:
        from data.db import save_telegram_channels

        save_telegram_channels(channels)
    except Exception as exc:
        _log(f"db mirror skipped: {exc}")


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


def _runtime_channels_path() -> Path:
    from data.const import TELEGRAM_CHANNELS_RUNTIME_PATH

    return TELEGRAM_CHANNELS_RUNTIME_PATH


def _telegram_session_path() -> Path:
    from data.const import TELEGRAM_SESSION_PATH

    return TELEGRAM_SESSION_PATH


def _log(message: str) -> None:
    print(f"[telegram_subscription] {message}")
