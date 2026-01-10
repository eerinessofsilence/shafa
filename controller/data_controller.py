import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from telethon import TelegramClient
from telethon.types import MessageMediaPhoto
from data.const import (
    BRAND_NAME_TO_ID,
    COLOR_NAME_TO_ENUM,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
)
from data.db import (
    get_brand_id_by_name,
    get_next_uncreated_telegram_product,
    get_size_id_by_name,
    mark_telegram_product_created,
    save_telegram_product,
)

api_id = TELEGRAM_API_ID
api_hash = TELEGRAM_API_HASH
channel_id = -1001184429834

DEFAULT_DESCRIPTION = (
    """36 (23.0см)
       37 (23.5см)
       38 (24.0см)
       39 (25.0см)
       40 (25.5см)
       41 (26.5см)
       41 (26.0 см)
       42 (26.5 см)
       43 (27.5 см)
       44 (28.0 см)
       45 (29. 0 см)
       Представляємо втілення комфорту, стилю та універсальності: наші чудові кросівки. Це взуття є втіленням сучасного взуття, яке підходить для будь-якого випадку, одягу та способу життя. Створені з прискіпливою увагою до деталей, наші кросівки розроблені, щоб забезпечити виняткове поєднання моди та функціональності."""
)

def parse_message(message: str) -> dict:
    lines = [line.strip() for line in message.splitlines() if line.strip()]

    color_base = {
        "black",
        "white",
        "gray",
        "grey",
        "brown",
        "orange",
        "red",
        "blue",
        "green",
        "pink",
        "purple",
        "beige",
        "cream",
        "navy",
        "tan",
        "silver",
        "gold",
        "yellow",
        "olive",
        "khaki",
    }
    color_modifiers = {"dark", "light"}

    def normalize_size(size: str) -> str:
        match = re.match(r"^\s*(\d+(?:[.,]\d+)?)", size)
        if match:
            return match.group(1).replace(",", ".")
        return size.strip()

    def extract_color(product_name: str) -> str:
        tokens = re.findall(r"[A-Za-z]+", product_name)
        colors = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            lower = token.lower()
            if lower in color_modifiers and i + 1 < len(tokens):
                next_token = tokens[i + 1]
                if next_token.lower() in color_base:
                    colors.append(f"{token} {next_token}")
                    i += 2
                    continue
            if lower in color_base:
                colors.append(token)
            i += 1
        return " ".join(colors)

    name = ""
    for line in lines:
        if line.startswith("❇️"):
            name = line.replace("❇️", "", 1).strip()
            break

    if not name:
        for line in lines:
            if "Анонсуємо" in line:
                name = line.split("Анонсуємо", 1)[1].strip()
                break

    brand = ""
    if name:
        brand = name.split()[0]
    else:
        for line in lines:
            match = re.search(r"розділ\s+([A-Za-zА-Яа-я0-9-]+)", line, re.IGNORECASE)
            if match:
                brand = match.group(1)
                break

    sizes = []
    for line in lines:
        if "Розмірна сітка" in line:
            sizes_part = line.split(":", 1)[1] if ":" in line else ""
            sizes_part = sizes_part.split("(", 1)[0]
            sizes = [normalize_size(size) for size in sizes_part.split("/") if size.strip()]
            break

    size = sizes[0] if sizes else ""
    additional_sizes = sizes[1:] if len(sizes) > 1 else []

    color = extract_color(name) if name else ""

    price = ""
    for line in lines:
        if "Дроп ціна" in line:
            numbers = re.findall(r"\d+(?:[.,]\d+)?", line)
            if numbers:
                price = numbers[-1].replace(",", ".")
            break

    return {
        "name": name,
        "brand": brand,
        "size": size,
        "additional_sizes": additional_sizes,
        "color": color,
        "price": price,
    }


async def _fetch_messages(message_amount: int = 10) -> int:
    inserted = 0
    async with TelegramClient("session", api_id, api_hash) as client:
        async for msg in client.iter_messages(channel_id, limit=message_amount):
            if (
                isinstance(msg.media, MessageMediaPhoto)
                and msg.message
                and "Дроп ціна:" in msg.message
            ):
                parsed = parse_message(msg.message)
                if not parsed.get("name"):
                    continue
                if save_telegram_product(channel_id, msg.id, msg.message, parsed):
                    inserted += 1
    return inserted


async def _download_message_photos(message_id: int, target_dir: Path) -> int:
    async with TelegramClient("session", api_id, api_hash) as client:
        message = await client.get_messages(channel_id, ids=message_id)
        if not message or not isinstance(message.media, MessageMediaPhoto):
            return 0
        messages = [message]
        if message.grouped_id:
            group_id = message.grouped_id
            min_id = max(1, message_id - 50)
            max_id = message_id + 50
            messages = []
            async for msg in client.iter_messages(channel_id, min_id=min_id, max_id=max_id):
                if msg.grouped_id == group_id and isinstance(msg.media, MessageMediaPhoto):
                    messages.append(msg)
            if not messages:
                messages = [message]
        target_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        seen: set[int] = set()
        for msg in messages:
            if msg.id in seen:
                continue
            seen.add(msg.id)
            result = await client.download_media(msg, file=str(target_dir))
            if result:
                downloaded += 1
        return downloaded


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+", text):
        return int(text)
    return None


def _parse_price(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", ".")
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return int(float(text))
    return None


def _resolve_brand_id(brand: Optional[str]) -> Optional[int]:
    if brand is None:
        return None
    if isinstance(brand, int):
        return brand
    text = str(brand).strip()
    if not text:
        return None
    brand_id = get_brand_id_by_name(text)
    if brand_id is not None:
        return brand_id
    brand_id = _parse_int(text)
    if brand_id is not None:
        return brand_id
    return BRAND_NAME_TO_ID.get(text.lower())


def _resolve_size_id(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    size_id = get_size_id_by_name(text)
    if size_id is None and "," in text:
        size_id = get_size_id_by_name(text.replace(",", "."))
    if size_id is None and "." in text:
        size_id = get_size_id_by_name(text.replace(".", ","))
    if size_id is not None:
        return size_id
    return _parse_int(text)


def _normalize_colors(color_raw: Optional[str]) -> list[str]:
    if not color_raw:
        return ["WHITE"]
    tokens = re.findall(r"[A-Za-z]+", color_raw.lower())
    colors: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in {"light", "dark"} and i + 1 < len(tokens):
            base = tokens[i + 1]
            i += 2
        else:
            base = token
            i += 1
        mapped = COLOR_NAME_TO_ENUM.get(base)
        if mapped and mapped not in colors:
            colors.append(mapped)
    return colors or ["WHITE"]


def _parse_additional_sizes(values: list[str]) -> list[int]:
    sizes: list[int] = []
    for value in values:
        size = _resolve_size_id(value)
        if size is not None:
            sizes.append(size)
    return sizes


def _build_product_raw_data(parsed: dict) -> dict:
    product_raw_data: dict = {
        "name": parsed.get("name", ""),
        "description": DEFAULT_DESCRIPTION,
        "category": "obuv/krossovki",
        "brand": _resolve_brand_id(parsed.get("brand")),
        "size": _resolve_size_id(parsed.get("size")),
        "price": _parse_price(parsed.get("price")),
    }
    product_raw_data["colors"] = _normalize_colors(parsed.get("color"))
    additional_sizes = _parse_additional_sizes(parsed.get("additional_sizes", []))
    if additional_sizes:
        product_raw_data["additional_sizes"] = additional_sizes
    return product_raw_data


def get_next_product_for_upload(message_amount: int = 30) -> Optional[dict]:
    asyncio.run(_fetch_messages(message_amount=message_amount))
    row = get_next_uncreated_telegram_product(channel_id)
    if not row:
        return None
    parsed = json.loads(row["parsed_data"]) if row["parsed_data"] else {}
    return {
        "message_id": row["message_id"],
        "product_raw_data": _build_product_raw_data(parsed),
    }


def download_product_photos(message_id: int, target_dir: Path) -> int:
    return asyncio.run(_download_message_photos(message_id, target_dir))

def mark_product_created(message_id: int, created_product_id: Optional[str] = None) -> None:
    mark_telegram_product_created(channel_id, message_id, created_product_id)


if __name__ == "__main__":
    product = get_next_product_for_upload(message_amount=10)
    print(product)
