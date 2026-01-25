import asyncio
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.types import (
    DocumentAttributeAnimated,
    DocumentAttributeSticker,
    MessageMediaDocument,
    MessageMediaPhoto,
)
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.utils import get_peer_id
from data.const import (
    BRAND_NAME_TO_ID,
    COLOR_NAME_TO_ENUM,
    MAX_UPLOAD_BYTES,
    TELEGRAM_CHANNELS,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
)
from data.db import (
    get_brand_id_by_name,
    get_next_uncreated_telegram_product,
    get_size_id_by_name,
    list_brand_names,
    load_telegram_channels,
    mark_telegram_product_created,
    save_telegram_channels,
    save_telegram_product,
    size_id_exists,
)
from utils.logging import log

api_id = TELEGRAM_API_ID
api_hash = TELEGRAM_API_HASH
DEFAULT_CHANNELS = TELEGRAM_CHANNELS
DEFAULT_CHANNEL_IDS = [channel_id for channel_id, _, _ in DEFAULT_CHANNELS]

DEFAULT_DESCRIPTION = """36 (23.0см)
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
MAX_DOWNLOAD_PHOTOS = 10

_PRICE_HINTS = (
    "цена",
    "ціна",
    "price",
    "грн",
    "uah",
    "₴",
    "дроп",
    "drop",
    "опт",
    "оптов",
    "рознич",
    "роздріб",
    "sale",
)
_SIZE_HINTS = (
    "розмір",
    "размер",
    "size",
    "розміри",
    "размеры",
    "сітка",
    "сетк",
    "sizes",
)
_NAME_LABELS = ("назва", "name", "модель", "model")
_BRAND_LABELS = ("бренд", "brand")
_COLOR_LABELS = ("колір", "цвет", "color")
_GENERIC_NAME_TOKENS = {
    "чоловічі",
    "чоловічий",
    "жіночі",
    "жіночий",
    "мужские",
    "мужской",
    "женские",
    "женский",
    "дитячі",
    "дитячий",
    "детские",
    "детский",
    "підліткові",
    "подростковые",
    "unisex",
    "унісекс",
    "унисекс",
    "kids",
    "kid",
    "junior",
    "youth",
    "boy",
    "boys",
    "girl",
    "girls",
    "кросівки",
    "кросівка",
    "кросівок",
    "кроси",
    "кросовки",
    "кроссовки",
    "кеди",
    "кеды",
    "кед",
    "ботинки",
    "ботінки",
    "ботінок",
    "черевики",
    "boots",
    "boot",
    "sneaker",
    "sneakers",
    "trainer",
    "trainers",
    "shoe",
    "shoes",
    "running",
    "взуття",
    "обувь",
}
_CONTACT_HINTS = (
    "тел",
    "телефон",
    "viber",
    "вайбер",
    "whatsapp",
    "instagram",
    "inst",
    "tg",
    "телеграм",
    "доставка",
    "оплата",
    "налож",
    "передоплата",
    "самовывоз",
    "самовивіз",
    "заказ",
    "замовлення",
    "в наличии",
    "в наявності",
)
_NON_NAME_HINTS = (
    _PRICE_HINTS
    + _SIZE_HINTS
    + _CONTACT_HINTS
    + (
        "артикул",
        "код",
        "barcode",
        "штрихкод",
        "опис",
        "характеристики",
    )
)
_NAME_EXCLUDE_HINTS = (
    "виробник",
    "made in",
    "сезон",
    "матеріал",
    "матеріали",
    "упакован",
    "упаков",
    "каталог",
    "розділ",
    "раздел",
    "коментар",
    "фото",
    "відео",
    "додатков",
    "црм",
    "crm",
    "розмірна",
    "сітка",
    "опис",
    "характеристик",
)
_PRICE_EXCLUDE_HINTS = (
    "артикул",
    "код",
    "barcode",
    "штрихкод",
    "каталог",
    "catalog",
)
_BRAND_PATTERNS: Optional[list[tuple[str, re.Pattern]]] = None
_SIZE_EXCLUDE_HINTS = (
    "артикул",
    "код",
    "barcode",
    "штрихкод",
    "каталог",
    "catalog",
    "виробник",
    "сезон",
    "матеріал",
    "матеріали",
    "упакован",
    "коментар",
    "фото",
    "відео",
    "опис",
    "характеристик",
)
_ALPHA_SIZES = {
    "XXXS",
    "XXS",
    "XS",
    "S",
    "M",
    "L",
    "XL",
    "XXL",
    "XXXL",
    "XXXXL",
    "OS",
    "ONE SIZE",
}
_COLOR_SYNONYMS = {
    "black": "black",
    "white": "white",
    "gray": "gray",
    "grey": "gray",
    "brown": "brown",
    "orange": "orange",
    "red": "red",
    "blue": "blue",
    "green": "green",
    "pink": "pink",
    "purple": "purple",
    "beige": "beige",
    "cream": "cream",
    "navy": "navy",
    "tan": "tan",
    "silver": "silver",
    "gold": "gold",
    "yellow": "yellow",
    "olive": "olive",
    "khaki": "khaki",
    "чорний": "black",
    "черный": "black",
    "білий": "white",
    "белый": "white",
    "сірий": "gray",
    "серый": "gray",
    "коричневий": "brown",
    "коричневый": "brown",
    "помаранчевий": "orange",
    "оранжевый": "orange",
    "червоний": "red",
    "красный": "red",
    "синій": "blue",
    "синий": "blue",
    "зелений": "green",
    "зеленый": "green",
    "рожевий": "pink",
    "розовый": "pink",
    "фіолетовий": "purple",
    "фиолетовый": "purple",
    "бежевий": "beige",
    "бежевый": "beige",
    "кремовий": "cream",
    "кремовый": "cream",
    "темно-синій": "navy",
    "темно-синий": "navy",
    "оливковий": "olive",
    "оливковый": "olive",
    "хаки": "khaki",
    "жовтий": "yellow",
    "желтый": "yellow",
    "золотий": "gold",
    "золотой": "gold",
    "срібний": "silver",
    "серебряный": "silver",
    "молочный": "cream",
    "молочний": "cream",
}
_COLOR_MODIFIERS = {
    "dark": "dark",
    "light": "light",
    "темний": "dark",
    "темный": "dark",
    "темна": "dark",
    "темное": "dark",
    "світлий": "light",
    "светлый": "light",
    "світла": "light",
    "светлая": "light",
    "светлое": "light",
}


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _line_has_url(line: str) -> bool:
    lower = line.casefold()
    return "http://" in lower or "https://" in lower or "www." in lower


def _debug_fetch_enabled() -> bool:
    value = os.getenv("SHAFA_DEBUG_FETCH", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _debug_fetch_verbose() -> bool:
    value = os.getenv("SHAFA_DEBUG_FETCH_VERBOSE", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _require_telegram_credentials() -> tuple[int, str]:
    if api_id is None or not api_hash:
        raise RuntimeError(
            "Missing Telegram credentials. "
            "Set SHAFA_TELEGRAM_API_ID and SHAFA_TELEGRAM_API_HASH."
        )
    return int(api_id), api_hash


def _extra_photos_aggressive_limit() -> int:
    raw = os.getenv("SHAFA_EXTRA_PHOTOS_AGGRESSIVE_LIMIT", "").strip()
    parsed = _parse_int(raw) if raw else None
    if parsed is None or parsed <= 0:
        return 50
    return min(parsed, 2000)


def _extra_photos_window_minutes() -> int:
    raw = os.getenv("SHAFA_EXTRA_PHOTOS_WINDOW_MINUTES", "").strip()
    parsed = _parse_int(raw) if raw else None
    if parsed is None or parsed <= 0:
        return 180
    return min(parsed, 24 * 60)


def _discussion_fallback_limit() -> int:
    raw = os.getenv("SHAFA_DISCUSSION_FALLBACK_LIMIT", "").strip()
    parsed = _parse_int(raw) if raw else None
    if parsed is None or parsed <= 0:
        return 200
    return min(parsed, 2000)


def _is_image_document(document) -> bool:
    if not document:
        return False
    mime_type = getattr(document, "mime_type", "") or ""
    if not mime_type.startswith("image/"):
        return False
    attributes = getattr(document, "attributes", None) or []
    for attr in attributes:
        if isinstance(attr, (DocumentAttributeSticker, DocumentAttributeAnimated)):
            return False
    return True


def _is_photo_message(message) -> bool:
    if not message or not getattr(message, "media", None):
        return False
    if isinstance(message.media, MessageMediaPhoto):
        return True
    if isinstance(message.media, MessageMediaDocument):
        return _is_image_document(getattr(message, "document", None))
    return False


def _format_size_mb(size_bytes: Optional[int]) -> str:
    if not size_bytes or size_bytes <= 0:
        return "?"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _get_message_media_size_bytes(message) -> Optional[int]:
    if not message or not getattr(message, "media", None):
        return None
    if isinstance(message.media, MessageMediaDocument):
        document = getattr(message, "document", None) or getattr(
            message.media, "document", None
        )
        size = getattr(document, "size", None)
        if isinstance(size, int):
            return size
    if isinstance(message.media, MessageMediaPhoto):
        photo = getattr(message, "photo", None) or getattr(message.media, "photo", None)
        sizes = getattr(photo, "sizes", None) or []
        values: list[int] = []
        for size in sizes:
            size_value = getattr(size, "size", None)
            if isinstance(size_value, int):
                values.append(size_value)
                continue
            progressive = getattr(size, "sizes", None)
            if isinstance(progressive, list):
                values.extend([item for item in progressive if isinstance(item, int)])
                continue
            raw_bytes = getattr(size, "bytes", None)
            if isinstance(raw_bytes, (bytes, bytearray)):
                values.append(len(raw_bytes))
        if values:
            return max(values)
    file_obj = getattr(message, "file", None)
    size = getattr(file_obj, "size", None)
    if isinstance(size, int):
        return size
    return None


def _get_channel_ids() -> list[int]:
    raw = os.getenv("SHAFA_CHANNEL_IDS", "").strip()
    if not raw:
        rows = load_telegram_channels()
        if DEFAULT_CHANNELS:
            save_telegram_channels(DEFAULT_CHANNELS)
            if not rows:
                rows = load_telegram_channels()
        if rows:
            return [row["channel_id"] for row in rows]
        return DEFAULT_CHANNEL_IDS
    ids: list[int] = []
    for part in re.split(r"[,\s]+", raw):
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids or DEFAULT_CHANNEL_IDS


def _get_channel_alias(channel_id: int) -> str:
    for row in load_telegram_channels():
        if row["channel_id"] == channel_id:
            return row.get("alias") or ""
    return ""


async def _sync_channel_titles(client: TelegramClient, channel_ids: list[int]) -> None:
    rows = {row["channel_id"]: row for row in load_telegram_channels()}
    updates: list[tuple[int, str, Optional[str]]] = []
    for channel_id in channel_ids:
        current = rows.get(channel_id) or {}
        name = str(current.get("name") or "").strip()
        alias = current.get("alias")
        if name and name != str(channel_id):
            continue
        try:
            entity = await client.get_entity(channel_id)
        except (ValueError, RPCError):
            continue
        title = getattr(entity, "title", None) or getattr(entity, "username", None)
        if title and title != name:
            updates.append((channel_id, title, alias))
    if updates:
        save_telegram_channels(updates)


def normalize_message(message: str) -> str:
    if not message:
        return ""
    text = unicodedata.normalize("NFKC", message)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("–", "-").replace("—", "-")
    cleaned: list[str] = []
    for ch in text:
        if ch == "\n":
            cleaned.append("\n")
            continue
        if ch == "\t":
            cleaned.append(" ")
            continue
        if ch in {"\u200d", "\ufe0f", "\ufe0e"}:
            continue
        cat = unicodedata.category(ch)
        if cat in {"Cc", "Cf"}:
            continue
        if cat in {"So", "Sk"}:
            continue
        cleaned.append(ch)
    text = "".join(cleaned)
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[•*#>\-–—\s]+", "", line)
        line = re.sub(r"\s{2,}", " ", line)
        lines.append(line)
    return "\n".join(lines)


def _clean_name(value: str) -> str:
    text = value.strip(" \t-–—|:;")
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(
        r"\s*[-–—:]?\s*\d{2,6}\s*(?:грн|uah|₴)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    stripped = _strip_name_prefix(text)
    if stripped:
        text = stripped
    return text.strip()


def _normalize_token(token: str) -> str:
    return re.sub(r"[^\w]+", "", token, flags=re.UNICODE).casefold()


def _strip_name_prefix(text: str) -> str:
    tokens = text.split()
    if not tokens:
        return text
    idx = 0
    for token in tokens:
        normalized = _normalize_token(token)
        if not normalized:
            idx += 1
            continue
        if normalized in _GENERIC_NAME_TOKENS:
            idx += 1
            continue
        break
    if idx > 0 and idx < len(tokens):
        return " ".join(tokens[idx:])
    return text


def _looks_like_name(line: str) -> bool:
    if len(line) < 3 or len(line) > 120:
        return False
    lower = line.casefold()
    if _contains_any(lower, _NON_NAME_HINTS) or _contains_any(
        lower, _NAME_EXCLUDE_HINTS
    ):
        return False
    if _line_has_url(line) or "@" in line:
        return False
    letters = sum(ch.isalpha() for ch in line)
    if letters < 2:
        return False
    digits = sum(ch.isdigit() for ch in line)
    if letters < 3 and digits == 0:
        return False
    if digits > letters * 2:
        return False
    return True


def _score_name_line(line: str) -> float:
    letters = sum(ch.isalpha() for ch in line)
    words = len(line.split())
    score = min(letters / max(len(line), 1), 1.0) * 0.6
    if 2 <= words <= 8:
        score += 0.25
    if any(ch.isdigit() for ch in line):
        score += 0.05
    return score


def extract_name(lines: list[str]) -> str:
    for line in lines:
        match = re.search(rf"(?i)^(?:{'|'.join(_NAME_LABELS)})\s*[:\-]\s*(.+)$", line)
        if match:
            candidate = _clean_name(match.group(1))
            if candidate:
                return candidate
    for line in lines:
        match = re.search(
            r"(?i)^(?:отримали|получили|поступили|поступление|завезли)\s+(?:новинк\w*\s+)?(.+)$",
            line,
        )
        if match:
            candidate = _clean_name(match.group(1))
            if candidate:
                return candidate
    for line in lines:
        match = re.search(
            r"(?i)\b(?:анонс(?:уємо)?|анонсуємо|новинк\w*|new)\b[:\-]?\s*(.+)", line
        )
        if match:
            candidate = _clean_name(match.group(1))
            if candidate:
                return candidate
    for line in lines[:3]:
        if not _looks_like_name(line):
            continue
        candidate = _clean_name(line)
        if candidate and (
            len(candidate.split()) >= 2 or any(ch.isdigit() for ch in candidate)
        ):
            return candidate
    best = ""
    best_score = 0.0
    for idx, line in enumerate(lines):
        if not _looks_like_name(line):
            continue
        candidate = _clean_name(line)
        if not candidate:
            continue
        score = _score_name_line(candidate) - min(idx, 10) * 0.02
        if candidate.endswith(".") and len(candidate.split()) > 4:
            score -= 0.2
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _normalize_number(value: str) -> str:
    text = value.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _to_number(value: str) -> Optional[float]:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _extract_last_price_token(text: str, *, allow_small: bool) -> str:
    for token in reversed(
        re.findall(
            r"(?<!\d)\d{1,3}(?:[ \u00A0]\d{3})+(?:[.,]\d{1,2})?(?!\d)",
            text,
        )
    ):
        normalized = _normalize_number(token)
        numeric = _to_number(normalized)
        if numeric is None:
            continue
        if allow_small or numeric >= 100:
            return normalized
    for token in reversed(re.findall(r"(?<!\d)\d{2,6}(?:[.,]\d{1,2})?(?!\d)", text)):
        numeric = _to_number(token)
        if numeric is None:
            continue
        if allow_small or numeric >= 100:
            return _normalize_number(token)
    return ""


def _price_from_line(
    line: str, *, allow_small: bool, require_currency: bool = False
) -> str:
    currency_match = None
    for match in re.finditer(r"(?:грн|uah|₴|usd|eur|руб)\b", line, flags=re.IGNORECASE):
        currency_match = match
    if currency_match:
        token = _extract_last_price_token(
            line[: currency_match.start()], allow_small=allow_small
        )
        if token:
            return token
        if require_currency:
            return ""
    if require_currency:
        return ""
    return _extract_last_price_token(line, allow_small=allow_small)


def extract_price(lines: list[str]) -> str:
    for line in lines:
        lower = line.casefold()
        if _line_has_url(line) or _contains_any(lower, _PRICE_EXCLUDE_HINTS):
            continue
        if not _contains_any(lower, _PRICE_HINTS):
            continue
        price = _price_from_line(line, allow_small=True)
        if price:
            return price
    for line in lines:
        lower = line.casefold()
        if _line_has_url(line) or _contains_any(lower, _PRICE_EXCLUDE_HINTS):
            continue
        price = _price_from_line(line, allow_small=False, require_currency=True)
        if price:
            return price
    candidates: list[tuple[float, str]] = []
    for line in lines:
        lower = line.casefold()
        if (
            _line_has_url(line)
            or _contains_any(lower, _PRICE_EXCLUDE_HINTS)
            or _contains_any(lower, _CONTACT_HINTS)
        ):
            continue
        if _contains_any(lower, _SIZE_HINTS):
            continue
        compact = line.replace("\u00a0", " ")
        for token in re.findall(r"\d{2,6}(?:[.,]\d{1,2})?", compact):
            numeric = _to_number(token)
            if numeric is None or numeric < 100:
                continue
            candidates.append((numeric, token))
    if candidates:
        return _normalize_number(max(candidates, key=lambda item: item[0])[1])
    return ""


def _normalize_size_token(token: str) -> str:
    text = token.strip().upper()
    if text in _ALPHA_SIZES:
        return text
    if text.replace(",", ".").replace(".", "", 1).isdigit():
        value = text.replace(",", ".")
        if value.endswith(".0"):
            value = value[:-2]
        return value
    return ""


def _extract_size_tokens_from_line(line: str) -> list[str]:
    tokens: list[str] = []
    lower = line.casefold()
    if re.search(r"\bone\s*size\b", lower):
        tokens.append("ONE SIZE")
    for size in re.findall(
        r"\b(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|XXXXL|OS)\b", line.upper()
    ):
        tokens.append(size)
    for match in re.finditer(r"\b(\d{2})\s*[-–]\s*(\d{2})\b", line):
        after = line[match.end() : match.end() + 4].casefold()
        if "см" in after or "cm" in after:
            continue
        start = int(match.group(1))
        end = int(match.group(2))
        if not (15 <= start <= 60 and 15 <= end <= 60):
            continue
        if end < start or end - start > 20:
            continue
        for value in range(start, end + 1):
            tokens.append(str(value))
    cleaned = re.sub(
        r"\b\d{2,3}(?:[.,]\d+)?\s*(?:см|cm)\b", "", line, flags=re.IGNORECASE
    )
    for match in re.finditer(r"\d{2,3}(?:[.,]\d+)?", cleaned):
        if match.start() > 0 and cleaned[match.start() - 1].isdigit():
            continue
        if match.end() < len(cleaned) and cleaned[match.end()].isdigit():
            continue
        numeric = _to_number(match.group(0))
        if numeric is None or not (15 <= numeric <= 60):
            continue
        normalized = _normalize_size_token(match.group(0))
        if normalized:
            tokens.append(normalized)
    return tokens


def extract_sizes(lines: list[str]) -> tuple[str, list[str]]:
    sizes: list[str] = []
    hinted_lines: list[str] = []
    fallback_lines: list[str] = []
    for line in lines:
        lower = line.casefold()
        if _contains_any(lower, _PRICE_HINTS) and not _contains_any(lower, _SIZE_HINTS):
            continue
        if not _contains_any(lower, _SIZE_HINTS) and _contains_any(
            lower, _SIZE_EXCLUDE_HINTS
        ):
            continue
        if _contains_any(lower, _SIZE_HINTS):
            hinted_lines.append(line)
        else:
            fallback_lines.append(line)

    candidates = hinted_lines or fallback_lines
    for line in candidates:
        for token in _extract_size_tokens_from_line(line):
            if token not in sizes:
                sizes.append(token)
    size = sizes[0] if sizes else ""
    additional_sizes = sizes[1:] if len(sizes) > 1 else []
    return size, additional_sizes


def _load_brand_patterns() -> list[tuple[str, re.Pattern]]:
    global _BRAND_PATTERNS
    if _BRAND_PATTERNS is not None:
        return _BRAND_PATTERNS
    names = [name.strip() for name in list_brand_names() if str(name).strip()]
    names.sort(key=len, reverse=True)
    patterns: list[tuple[str, re.Pattern]] = []
    for name in names:
        escaped = re.escape(name)
        patterns.append((name, re.compile(rf"(?i)(?<!\w){escaped}(?!\w)")))
    _BRAND_PATTERNS = patterns
    return patterns


def _find_brand_in_text(text: str) -> str:
    if not text:
        return ""
    for name, pattern in _load_brand_patterns():
        if pattern.search(text):
            return name
    return ""


def _fallback_brand_from_name(name: str) -> str:
    if not name:
        return ""
    for token in name.split():
        normalized = _normalize_token(token)
        if not normalized or normalized in _GENERIC_NAME_TOKENS:
            continue
        return token.strip(".,;:()[]{}")
    return name.split()[0] if name else ""


def extract_brand(lines: list[str], name: str) -> str:
    for line in lines:
        if not _contains_any(line.casefold(), _BRAND_LABELS):
            continue
        match = re.search(
            rf"(?i)\b(?:{'|'.join(_BRAND_LABELS)})\b\s*[:\-]?\s*(.+)$", line
        )
        if match:
            value = match.group(1)
            value = re.split(r"[|,/]", value)[0].strip()
            if value:
                normalized = _normalize_token(value)
                if normalized and normalized not in _GENERIC_NAME_TOKENS:
                    return value
    cleaned_name = _strip_name_prefix(name)
    brand = _find_brand_in_text(cleaned_name)
    if brand:
        return brand
    for line in lines:
        brand = _find_brand_in_text(line)
        if brand:
            return brand
    return _fallback_brand_from_name(cleaned_name or name)


def extract_colors(lines: list[str], name: str) -> str:
    color_lines = [
        line for line in lines if _contains_any(line.casefold(), _COLOR_LABELS)
    ]
    candidates = (
        [name] + (color_lines if color_lines else lines)
        if name
        else (color_lines or list(lines))
    )
    text = " ".join(candidates)
    tokens = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]+", text)
    colors: list[str] = []
    pending_modifier = ""
    for token in tokens:
        key = token.casefold()
        modifier = _COLOR_MODIFIERS.get(key)
        if modifier:
            pending_modifier = modifier
            continue
        base = _COLOR_SYNONYMS.get(key)
        if base:
            if pending_modifier:
                color = f"{pending_modifier} {base}"
                pending_modifier = ""
            else:
                color = base
            if color not in colors:
                colors.append(color)
        else:
            pending_modifier = ""
    return " ".join(colors)


def _calculate_confidence(
    name: str,
    price: str,
    size: str,
    brand: str,
    color: str,
) -> float:
    score = 0.0
    if name:
        score += 0.4
    if price:
        score += 0.25
    if size:
        score += 0.25
    if brand:
        score += 0.05
    if color:
        score += 0.05
    return round(score, 2)


def parse_message(message: str) -> dict:
    normalized = normalize_message(message)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]

    name = extract_name(lines)
    brand = extract_brand(lines, name)
    size, additional_sizes = extract_sizes(lines)
    color = extract_colors(lines, name)
    price = extract_price(lines)
    confidence = _calculate_confidence(name, price, size, brand, color)

    return {
        "name": name,
        "brand": brand,
        "size": size,
        "additional_sizes": additional_sizes,
        "color": color,
        "price": price,
        "confidence": confidence,
    }


async def _fetch_messages(message_amount: int = 75) -> int:
    inserted = 0
    debug_fetch = _debug_fetch_enabled()
    debug_verbose = _debug_fetch_verbose()
    stats = {
        "total": 0,
        "no_media": 0,
        "non_photo_media": 0,
        "no_text": 0,
        "missing_name": 0,
        "missing_price": 0,
        "missing_size": 0,
        "parsed_ok": 0,
        "saved": 0,
        "duplicate": 0,
    }
    verbose_limit = 5
    verbose_count = 0

    def log_skip(reason: str, text: str, message_id: int, channel_id: int) -> None:
        nonlocal verbose_count
        if not debug_verbose or verbose_count >= verbose_limit:
            return
        preview_lines = normalize_message(text).splitlines() if text else []
        preview = preview_lines[0] if preview_lines else ""
        print(
            f"[DEBUG] skip channel_id={channel_id} message_id={message_id} "
            f"reason={reason} text={preview}"
        )
        verbose_count += 1

    api_id_value, api_hash_value = _require_telegram_credentials()
    async with TelegramClient("session", api_id_value, api_hash_value) as client:
        channel_ids = _get_channel_ids()
        await _sync_channel_titles(client, channel_ids)
        for channel_id in channel_ids:
            async for msg in client.iter_messages(channel_id, limit=message_amount):
                if debug_fetch:
                    stats["total"] += 1
                if not msg.media:
                    if debug_fetch:
                        stats["no_media"] += 1
                    log_skip("no_media", msg.message or "", msg.id, channel_id)
                    continue
                if not _is_photo_message(msg):
                    if debug_fetch:
                        stats["non_photo_media"] += 1
                    log_skip("non_photo_media", msg.message or "", msg.id, channel_id)
                    continue
                if not msg.message:
                    if debug_fetch:
                        stats["no_text"] += 1
                    log_skip("no_text", "", msg.id, channel_id)
                    continue
                parsed = parse_message(msg.message)
                if not parsed.get("name"):
                    if debug_fetch:
                        stats["missing_name"] += 1
                    log_skip("missing_name", msg.message, msg.id, channel_id)
                    continue
                if not parsed.get("price"):
                    if debug_fetch:
                        stats["missing_price"] += 1
                    log_skip("missing_price", msg.message, msg.id, channel_id)
                    continue
                if not parsed.get("size"):
                    if debug_fetch:
                        stats["missing_size"] += 1
                    log_skip("missing_size", msg.message, msg.id, channel_id)
                    continue
                if debug_fetch:
                    stats["parsed_ok"] += 1
                if save_telegram_product(channel_id, msg.id, msg.message, parsed):
                    inserted += 1
                    if debug_fetch:
                        stats["saved"] += 1
                elif debug_fetch:
                    stats["duplicate"] += 1
    if debug_fetch:
        print(
            "[DEBUG] fetch stats: "
            f"total={stats['total']} "
            f"no_media={stats['no_media']} "
            f"non_photo_media={stats['non_photo_media']} "
            f"no_text={stats['no_text']} "
            f"missing_name={stats['missing_name']} "
            f"missing_price={stats['missing_price']} "
            f"missing_size={stats['missing_size']} "
            f"parsed_ok={stats['parsed_ok']} "
            f"saved={stats['saved']} "
            f"duplicate={stats['duplicate']}"
        )
    return inserted


async def _collect_group_messages(
    client: TelegramClient,
    channel_id: int,
    message_id: int,
    grouped_id: int,
) -> list:
    min_id = max(1, message_id - 50)
    max_id = message_id + 50
    messages: list = []
    async for msg in client.iter_messages(channel_id, min_id=min_id, max_id=max_id):
        if msg.grouped_id == grouped_id and _is_photo_message(msg):
            messages.append(msg)
    return messages


async def _collect_discussion_photos(
    client: TelegramClient,
    channel_id: int,
    message_id: int,
    message_ids: Optional[list[int]] = None,
) -> list:
    alias = _get_channel_alias(channel_id)
    if "extra_photos" not in alias:
        return []
    candidate_ids = [message_id]
    if message_ids:
        seen_ids: set[int] = set()
        candidate_ids = []
        for item in message_ids:
            if item and item not in seen_ids:
                candidate_ids.append(item)
                seen_ids.add(item)
        if not candidate_ids:
            candidate_ids = [message_id]
    result = None
    last_exc: Optional[Exception] = None
    for candidate_id in candidate_ids:
        try:
            result = await client(
                GetDiscussionMessageRequest(peer=channel_id, msg_id=candidate_id)
            )
        except RPCError as exc:
            last_exc = exc
            result = None
            continue
        if result.messages:
            break
        result = None
    if not result or not result.messages:
        if last_exc:
            preview = ", ".join(str(value) for value in candidate_ids[:5])
            suffix = "..." if len(candidate_ids) > 5 else ""
            log(
                "WARN",
                "Не удалось получить обсуждение для сообщения: "
                f"channel_id={channel_id} message_ids=[{preview}{suffix}] error={last_exc}.",
            )
        return []
    discussion_chat_id: Optional[int] = None
    for msg in result.messages:
        chat_id = getattr(msg, "chat_id", None)
        if chat_id and chat_id != channel_id:
            discussion_chat_id = chat_id
            break
    if discussion_chat_id is None:
        for chat in result.chats:
            chat_id = get_peer_id(chat)
            if chat_id != channel_id:
                discussion_chat_id = chat_id
                break
    if not discussion_chat_id:
        return []
    root = next(
        (
            msg
            for msg in result.messages
            if getattr(msg, "chat_id", None) == discussion_chat_id
        ),
        None,
    )
    if not root:
        return []
    messages: list = []
    grouped_seen: set[int] = set()

    async def add_reply(reply) -> None:
        if not _is_photo_message(reply):
            return
        if reply.grouped_id:
            if reply.grouped_id in grouped_seen:
                return
            grouped_seen.add(reply.grouped_id)
            grouped = await _collect_group_messages(
                client,
                discussion_chat_id,
                reply.id,
                reply.grouped_id,
            )
            if grouped:
                messages.extend(grouped)
                return
        messages.append(reply)

    root_id = getattr(root, "id", None)
    if not root_id:
        return []
    root_date = getattr(root, "date", None)
    try:
        async for reply in client.iter_messages(discussion_chat_id, reply_to=root_id):
            await add_reply(reply)
    except RPCError as exc:
        log(
            "WARN",
            "Не удалось получить ответы из обсуждения: "
            f"chat_id={discussion_chat_id} root_id={root_id} error={exc}.",
        )
    if messages:
        return messages

    fallback_limit = _discussion_fallback_limit()
    window_minutes = _extra_photos_window_minutes()
    window_seconds = window_minutes * 60 if window_minutes > 0 else 0
    try:
        async for reply in client.iter_messages(
            discussion_chat_id, limit=fallback_limit
        ):
            header = getattr(reply, "reply_to", None)
            if header:
                top_id = getattr(header, "reply_to_top_id", None)
                msg_id = getattr(header, "reply_to_msg_id", None)
                if top_id != root_id and msg_id != root_id:
                    continue
                await add_reply(reply)
                continue
            if window_seconds <= 0:
                continue
            reply_id = getattr(reply, "id", None)
            if reply_id is not None and reply_id <= root_id:
                continue
            if root_date is not None:
                reply_date = getattr(reply, "date", None)
                if reply_date is not None:
                    delta = (reply_date - root_date).total_seconds()
                    if delta < 0 or delta > window_seconds:
                        continue
            await add_reply(reply)
    except RPCError as exc:
        log(
            "WARN",
            "Не удалось прочитать обсуждение: "
            f"chat_id={discussion_chat_id} root_id={root_id} error={exc}.",
        )
        return []
    if messages:
        return messages

    aggressive_limit = _extra_photos_aggressive_limit()
    try:
        async for reply in client.iter_messages(
            discussion_chat_id,
            min_id=root_id,
            limit=aggressive_limit,
            reverse=True,
        ):
            reply_id = getattr(reply, "id", None)
            if reply_id is not None and reply_id <= root_id:
                continue
            await add_reply(reply)
            if len(messages) >= aggressive_limit:
                break
    except RPCError as exc:
        log(
            "WARN",
            "Не удалось получить фото из обсуждения (aggressive): "
            f"chat_id={discussion_chat_id} root_id={root_id} error={exc}.",
        )
        return []
    return messages


async def _download_message_photos(
    channel_id: int,
    message_id: int,
    target_dir: Path,
    max_photos: int,
) -> int:
    api_id_value, api_hash_value = _require_telegram_credentials()
    async with TelegramClient("session", api_id_value, api_hash_value) as client:
        await _sync_channel_titles(client, _get_channel_ids())
        log(
            "INFO",
            f"Скачиваю фото из Telegram: channel_id={channel_id} message_id={message_id}.",
        )
        message = await client.get_messages(channel_id, ids=message_id)
        if not message or not _is_photo_message(message):
            return 0
        messages = [message]
        if message.grouped_id:
            grouped = await _collect_group_messages(
                client,
                channel_id,
                message_id,
                message.grouped_id,
            )
            messages = grouped or [message]
            if not messages:
                messages = [message]
        discussion_message_ids = [message_id]
        for msg in sorted(messages, key=lambda item: item.id):
            if msg.id != message_id:
                discussion_message_ids.append(msg.id)
        extra = await _collect_discussion_photos(
            client,
            channel_id,
            message_id,
            discussion_message_ids,
        )
        if extra:
            messages.extend(extra)
        target_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        seen: set[tuple[int, int]] = set()
        queue: list[tuple] = []
        skipped_large = 0
        max_mb = MAX_UPLOAD_BYTES / (1024 * 1024)
        for msg in messages:
            chat_id = getattr(msg, "chat_id", channel_id)
            key = (int(chat_id), msg.id)
            if key in seen:
                continue
            seen.add(key)
            size_bytes = _get_message_media_size_bytes(msg)
            if size_bytes is not None and size_bytes > MAX_UPLOAD_BYTES:
                skipped_large += 1
                size_mb = size_bytes / (1024 * 1024)
                log(
                    "WARN",
                    "Пропускаю фото из Telegram: "
                    f"message_id={msg.id} chat_id={chat_id} "
                    f"{size_mb:.2f} MB > лимита {max_mb:.2f} MB.",
                )
                continue
            queue.append((msg, chat_id, size_bytes))
        if max_photos > 0 and len(queue) > max_photos:
            log("INFO", f"Ограничение на фото: {max_photos}.")
            queue = queue[:max_photos]
        if skipped_large:
            log(
                "INFO",
                f"Пропущено крупных файлов: {skipped_large}. К скачиванию: {len(queue)}.",
            )
        if not queue:
            log("WARN", "Нет подходящих фото для скачивания.")
            return 0
        for idx, (msg, chat_id, size_bytes) in enumerate(queue, start=1):
            size_label = _format_size_mb(size_bytes)
            log(
                "INFO",
                f"Скачивание фото {idx}/{len(queue)}: "
                f"message_id={msg.id} chat_id={chat_id} size={size_label}.",
            )
            result = await client.download_media(msg, file=str(target_dir))
            if result:
                downloaded += 1
                log("OK", f"Скачано фото {idx}/{len(queue)}: message_id={msg.id}.")
            else:
                log(
                    "WARN",
                    f"Не удалось скачать фото {idx}/{len(queue)}: message_id={msg.id}.",
                )
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
        return value if size_id_exists(value) else None
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
    parsed = _parse_int(text)
    if parsed is None:
        return None
    return parsed if size_id_exists(parsed) else None


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


def build_product_raw_data(parsed: dict) -> dict:
    return _build_product_raw_data(parsed)


def get_next_product_for_upload(message_amount: int = 75) -> Optional[dict]:
    asyncio.run(_fetch_messages(message_amount=message_amount))
    rows = [
        row
        for channel_id in _get_channel_ids()
        for row in [get_next_uncreated_telegram_product(channel_id)]
        if row
    ]
    if not rows:
        return None
    row = max(rows, key=lambda item: item["created_at"])
    parsed = json.loads(row["parsed_data"]) if row["parsed_data"] else {}
    raw_message = row["raw_message"] or ""
    reparsed = parse_message(raw_message) if raw_message else {}
    if reparsed.get("price") and reparsed.get("size"):
        parsed = reparsed
    return {
        "channel_id": row["channel_id"],
        "message_id": row["message_id"],
        "parsed_data": parsed,
        "product_raw_data": _build_product_raw_data(parsed),
    }


def download_product_photos(
    message_id: int,
    target_dir: Path,
    channel_id: Optional[int] = None,
    max_photos: int = MAX_DOWNLOAD_PHOTOS,
) -> int:
    resolved_channel_id = (
        channel_id if channel_id is not None else _get_channel_ids()[0]
    )
    return asyncio.run(
        _download_message_photos(
            resolved_channel_id,
            message_id,
            target_dir,
            max_photos,
        )
    )


def mark_product_created(
    message_id: int,
    created_product_id: Optional[str] = None,
    channel_id: Optional[int] = None,
) -> None:
    resolved_channel_id = (
        channel_id if channel_id is not None else _get_channel_ids()[0]
    )
    mark_telegram_product_created(resolved_channel_id, message_id, created_product_id)


if __name__ == "__main__":
    product = get_next_product_for_upload(message_amount=75)
    print(product)
