from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol
from urllib.parse import urlparse

DEFAULT_CHANNEL_ALIAS = "main"

_ID_PATTERNS = (
    re.compile(r"(?im)^\s*(?:chat\s*)?id\s*:\s*(-?\d+)\s*$"),
    re.compile(r"(?im)^\s*(?:channel\s*)?id\s*:\s*(-?\d+)\s*$"),
)
_TITLE_PATTERNS = (
    re.compile(r"(?im)^\s*title\s*:\s*(.+?)\s*$"),
    re.compile(r"(?im)^\s*chat\s*title\s*:\s*(.+?)\s*$"),
)


class TelegramIdBotClient(Protocol):
    def fetch_response(self, link: str) -> str:
        """Send a Telegram channel link to @ID_Bot and return the text response."""


@dataclass(frozen=True)
class TelegramLinkRuntimeConfig:
    account_name: str
    account_path: str
    links: list[str]


def normalize_channel_link(link: str) -> str:
    value = link.strip()
    if not value:
        raise ValueError("Channel link is empty.")
    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https Telegram links are supported.")
    if not parsed.netloc:
        raise ValueError("Telegram link must include a host.")
    return parsed.geturl()


def sanitize_channel_links(links: Iterable[str]) -> list[str]:
    unique_links: list[str] = []
    seen: set[str] = set()
    for raw_link in links:
        if not raw_link or not raw_link.strip():
            continue
        normalized = normalize_channel_link(raw_link)
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_links.append(normalized)
    return unique_links


def export_runtime_config(
    account_name: str,
    account_path: str,
    links: Iterable[str],
    output_dir: Path,
) -> Path:
    config = TelegramLinkRuntimeConfig(
        account_name=account_name,
        account_path=account_path,
        links=sanitize_channel_links(links),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{_slugify(account_name)}_telegram_channels.json"
    target.write_text(
        json.dumps(
            {
                "account_name": config.account_name,
                "account_path": config.account_path,
                "links": config.links,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def load_runtime_config(path: Path) -> TelegramLinkRuntimeConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return TelegramLinkRuntimeConfig(
        account_name=str(raw.get("account_name") or ""),
        account_path=str(raw.get("account_path") or ""),
        links=sanitize_channel_links(raw.get("links") or []),
    )


def parse_id_bot_response(response_text: str) -> tuple[int, str]:
    channel_id: int | None = None
    title: str | None = None

    for pattern in _ID_PATTERNS:
        match = pattern.search(response_text)
        if match:
            channel_id = int(match.group(1))
            break

    for pattern in _TITLE_PATTERNS:
        match = pattern.search(response_text)
        if match:
            title = match.group(1).strip()
            break

    if channel_id is None:
        raise ValueError("Could not extract channel id from @ID_Bot response.")
    if not title:
        raise ValueError("Could not extract channel title from @ID_Bot response.")
    return channel_id, title


def resolve_channel_tuples(
    links: Iterable[str],
    client: TelegramIdBotClient,
) -> list[tuple[int, str, str]]:
    channels: list[tuple[int, str, str]] = []
    for link in sanitize_channel_links(links):
        response_text = client.fetch_response(link)
        channel_id, title = parse_id_bot_response(response_text)
        channels.append((channel_id, title, DEFAULT_CHANNEL_ALIAS))
    return channels


def resolve_runtime_config(
    path: Path,
    client: TelegramIdBotClient,
) -> list[tuple[int, str, str]]:
    config = load_runtime_config(path)
    return resolve_channel_tuples(config.links, client)


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_")
    return cleaned.lower() or "account"
