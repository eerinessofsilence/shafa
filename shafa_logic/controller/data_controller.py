import asyncio
import json
import os
import random
import re
import sqlite3
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from telethon import TelegramClient
    from telethon.errors import RPCError
    from telethon.tl.functions.messages import GetDiscussionMessageRequest
    from telethon.types import (
        DocumentAttributeAnimated,
        DocumentAttributeFilename,
        DocumentAttributeSticker,
        MessageMediaDocument,
        MessageMediaPhoto,
    )
    from telethon.utils import get_peer_id
except ModuleNotFoundError:  # pragma: no cover - optional at import time for tests
    TelegramClient = object
    RPCError = Exception
    GetDiscussionMessageRequest = object
    DocumentAttributeAnimated = object
    DocumentAttributeFilename = object
    DocumentAttributeSticker = object
    MessageMediaDocument = object
    MessageMediaPhoto = object

    def get_peer_id(*args, **kwargs):
        raise RuntimeError("telethon is required for Telegram operations")

from controller.catalog_filter import find_slug_by_word, find_word
from data.const import (
    ACCOUNT_ID,
    BRAND_NAME_TO_ID,
    COLOR_NAME_TO_ENUM,
    DB_PATH,
    DEFAULT_MESSAGE_PARSE_LIMIT,
    MAX_PRODUCT_CREATE_ATTEMPTS,
    MAX_UPLOAD_BYTES,
    TELEGRAM_PRODUCTS_DB_PATH,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SESSION_PATH,
)
from data.db import (
    backfill_telegram_product_message_dates_from_existing_db,
    claim_telegram_product_deactivation,
    claim_shared_deactivation_task_for_account,
    claim_telegram_fetch,
    complete_shared_deactivation_task_for_account,
    enqueue_expired_telegram_products_for_deactivation,
    enqueue_telegram_product_deactivation,
    fail_shared_deactivation_task_for_account,
    find_size_mapping_candidates,
    finish_telegram_fetch,
    finish_telegram_product_deactivation,
    get_brand_id_by_name,
    get_max_telegram_product_message_id,
    get_next_uncreated_telegram_product,
    get_telegram_scan_cursor,
    list_telegram_product_deactivation_queue,
    get_size_id_by_name,
    increment_telegram_product_attempt,
    list_created_telegram_products_for_age_check,
    list_created_telegram_products_missing_date,
    list_brand_names,
    list_uploaded_products_for_age_check,
    load_telegram_channels,
    mark_uploaded_product_inactive,
    mark_telegram_product_deactivated_on_shafa,
    mark_telegram_backfill_started,
    mark_telegram_scan_started,
    finish_telegram_backfill,
    finish_telegram_scan,
    mark_telegram_product_created,
    record_telegram_product_shafa_deactivate_failure,
    plan_shared_deactivation_tasks,
    reconcile_shared_telegram_products,
    save_telegram_channels,
    save_telegram_product,
    set_telegram_product_message_date,
    skip_shared_deactivation_task_not_found_for_account,
    size_id_exists,
    telegram_products_exist,
)
from data.size_mapping import (
    SIZE_SYSTEM_EU,
    SIZE_SYSTEM_INTERNATIONAL,
    SIZE_SYSTEM_UA,
    normalize_size_text,
)
from telegram_channels import extract_telegram_invite_hash
from utils.logging import log
from utils.progress import ProgressBar, verbose_photo_logs_enabled
from telegram_subscription import get_telegram_channels, set_telegram_channels
from telegram_subscription.sync import get_telegram_channel_records
from telegram_subscription.client import create_telegram_client
from utils.pipeline_activity import enter_product_pipeline, exit_product_pipeline

APP_MODE_ENV = "SHAFA_APP_MODE"
MODE_CLOTHES = "clothes"
MODE_SNEAKERS = "sneakers"
DEFAULT_TELEGRAM_FETCH_COOLDOWN_SECONDS = 90
DEFAULT_TELEGRAM_FETCH_LEASE_SECONDS = 180
DEFAULT_TELEGRAM_FETCH_WAIT_SECONDS = 3.0
DEFAULT_TELEGRAM_SCAN_BATCH_SIZE = 150
DEFAULT_TELEGRAM_CHANNEL_SCAN_INTERVAL_SECONDS = 180
DEFAULT_TELEGRAM_CHANNEL_SCAN_LEASE_SECONDS = 360
DEFAULT_TELEGRAM_PRODUCT_MAX_AGE_DAYS = 183
DEFAULT_OLD_PRODUCT_DEACTIVATE_BATCH_SIZE = 1
DEFAULT_OLD_PRODUCT_DEACTIVATE_SLEEP_SECONDS = 3.0
DEFAULT_SHARED_DEACTIVATION_SCAN_SECONDS = 10.0
DEFAULT_SHARED_DEACTIVATION_COOLDOWN_MIN_SECONDS = 10.0
DEFAULT_SHARED_DEACTIVATION_COOLDOWN_MAX_SECONDS = 30.0
DEFAULT_SHARED_DEACTIVATION_LEASE_SECONDS = 900.0
DEFAULT_SHARED_DEACTIVATION_RETRY_DELAY_SECONDS = 300.0
DEFAULT_AUTO_DEACTIVATE_TELEGRAM_MATCH_SCORE = 0.85
MIN_PRODUCT_PRICE_DIGITS = 3
MAX_PRODUCT_PRICE_DIGITS = 4
_OLD_PRODUCT_AGE_CHECK_CURSOR: dict[tuple[str, str], int] = {}

api_id = TELEGRAM_API_ID
api_hash = TELEGRAM_API_HASH
SKIPPED_CREATE_RETRY_LIMIT = "SKIPPED_CREATE_RETRY_LIMIT"

DEFAULT_DESCRIPTION = (
    "36 (23.0 см)\n"
    "37 (23.5 см)\n"
    "38 (24.0 см)\n"
    "39 (25.0 см)\n"
    "40 (25.5 см)\n"
    "41 (26.0 см)\n"
    "42 (26.5 см)\n"
    "43 (27.5 см)\n"
    "44 (28.0 см)\n"
    "45 (29.0 см)\n"
    "\n"
    "Представляємо втілення комфорту, стилю та універсальності: "
    "наші чудові кросівки. Це взуття є втіленням сучасного взуття, "
    "яке підходить для будь-якого випадку, одягу та способу життя. "
    "Створені з прискіпливою увагою до деталей, наші кросівки "
    "розроблені, щоб забезпечити виняткове поєднання моди та "
    "функціональності."
)


DEFAULT_CLOTHES_DESCRIPTION = (
    "Розмірна сітка:\n"
    "S - 42\n"
    "M - 44\n"
    "L - 46\n"
    "\n"

    "Параметри та доступні розміри уточнюйте в повідомленнях. Якщо виникнуть додаткові запитання — пишіть у чат, із радістю відповім.\n"
    
    "Стильна річ для створення сучасного та впевненого образу. Добре поєднується з різними елементами гардеробу та підходить як для повсякденного носіння, так і для особливих випадків. Приємний матеріал забезпечує комфорт протягом усього дня, а універсальний дизайн легко вписується у будь-який стиль — від класичного до casual. Вдалий вибір для тих, хто цінує поєднання комфорту, практичності та актуального вигляду."
)
MAX_DOWNLOAD_PHOTOS = 10
DEFAULT_SHOES_CATEGORY = "obuv/krossovki"
WOMEN_SNEAKERS_CATEGORY = "zhenskaya-obuv/krossovki"
DEFAULT_CLOTHES_CATEGORY = "mayki-i-futbolki/futbolki"
CLOTHES_CATEGORIES = {
    "verhnyaya-odezhda/plashi": ["плащ", "плащі", "плащи", "плащь"],
    "verhnyaya-odezhda/kurtki": ["куртка", "куртки", "бомбер", "парка", "ветровка"],
    "verhnyaya-odezhda/shuby": ["шуба", "шубы", "шуби", "шубка", "шубки", "полушубок", "полушубки", "полушуба"],

}
WOMEN_SNEAKERS_MIN_SIZE = 36.0
WOMEN_SNEAKERS_MAX_SIZE = 41.0
UNSUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/heic", "image/heif"})
UNSUPPORTED_IMAGE_EXTENSIONS = frozenset({".heic", ".heif"})

CLOTHES_SIZE_MAPPING = {
    "XS": range(32, 37),  # 32-36
    "S": range(36, 41),   # 36-40
    "M": range(40, 45),   # 40-44
    "L": range(44, 49),   # 44-48
    "XL": range(48, 53),  # 48-52
    "XXL": range(52, 57), # 52-56
}

CLOTHES_SLUGS = [
    "verhnyaya-odezhda/palto",
    "verhnyaya-odezhda/plashi",
    "verhnyaya-odezhda/kurtki",
    "verhnyaya-odezhda/shuby",
    "verhnyaya-odezhda/zhiletki",
    "verhnyaya-odezhda/pidzhaki-i-zhakety",
    "verhnyaya-odezhda/puhoviki",
    "verhnyaya-odezhda/parki",
    "verhnyaya-odezhda/dublenki",
    "verhnyaya-odezhda/dozhdeviki",
    "verhnyaya-odezhda/vetrovki",

    "platya/mini",
    "platya/midi",
    "platya/maksi",
    "platya/vechernie",
    "platya/svadebnye",
    "platya/sarafany",
    "platya/tuniki",

    "yubki/mini",
    "yubki/midi",
    "yubki/maksi",

    "mayki-i-futbolki/futbolki",
    "mayki-i-futbolki/mayki",
    "mayki-i-futbolki/polo",
    "mayki-i-futbolki/topy",

    "rubashki-i-bluzy/rubashki",
    "rubashki-i-bluzy/bluzy",
    "rubashki-i-bluzy/vyshivanki",

    "kofty/dzhempery",
    "kofty/svitery",
    "kofty/kardigany",
    "kofty/vodolazki",
    "kofty/svitshoty",
    "kofty/hudi",
    "kofty/pulovery",
    "kofty/tolstovky",
    "kofty/nakidki",
    "kofty/bolero",
    "kofty/poncho",
    "kofty/reglan",
    "kofty/longslivy",
    "kofty/zhilety",

    "nizhnee-bele-i-kupalniki/lifchiki",
    "nizhnee-bele-i-kupalniki/trusiki",
    "nizhnee-bele-i-kupalniki/komplekty",
    "nizhnee-bele-i-kupalniki/kupalniki",
    "nizhnee-bele-i-kupalniki/noski",
    "nizhnee-bele-i-kupalniki/bodi",
    "nizhnee-bele-i-kupalniki/korsety",
    "nizhnee-bele-i-kupalniki/chulki",
    "nizhnee-bele-i-kupalniki/kolgotki",
    "nizhnee-bele-i-kupalniki/penyuary",
    "nizhnee-bele-i-kupalniki/termobelye",
    "nizhnee-bele-i-kupalniki/portupei",
    "nizhnee-bele-i-kupalniki/eroticheskoye",
    "nizhnee-bele-i-kupalniki/eroticheskiye-kostyumy",
    "nizhnee-bele-i-kupalniki/belyevyye-mayki",
    "nizhnee-bele-i-kupalniki/aksessuary",

    "sport-otdyh/sportivnyye-kostyumy",
    "sport-otdyh/sportivnyye-shtany",
    "sport-otdyh/losiny",
    "sport-otdyh/shorty",
    "sport-otdyh/topy",
    "sport-otdyh/kofty",
    "sport-otdyh/mayki",
    "sport-otdyh/kapri",
    "sport-otdyh/kombinezony",
    "sport-otdyh/belye",

    "sport-otdyh/gornolyzhnyye/kurtki",
    "sport-otdyh/gornolyzhnyye/kostyumy",
    "sport-otdyh/gornolyzhnyye/shtany",
    "sport-otdyh/gornolyzhnyye/kombinezony",

    "zhenskie-kostyumy/kostyumy-s-platem",
    "zhenskie-kostyumy/kostyumy-s-shortami",
    "zhenskie-kostyumy/kostyumy-s-yubkoj",
    "zhenskie-kostyumy/bryuchnye-kostyumy",

    "zhenskie-kombinezony/dzhinsovye-kombinezony",
    "zhenskie-kombinezony/bryuchnye-kombinezony",
    "zhenskie-kombinezony/kombinezony-s-shortami",

    "odezhda-dlya-doma-i-sna/domashnyaya-odezhda",
    "odezhda-dlya-doma-i-sna/pizhamy",
    "odezhda-dlya-doma-i-sna/nochnushki",
    "odezhda-dlya-doma-i-sna/halaty",
    "odezhda-dlya-doma-i-sna/masky-dlya-sna",
    "odezhda-dlya-doma-i-sna/kigurumi",
]

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
SIZE_NAME_MAPPING = {
    "XS": "34",
    "S": "36",
    "M": "38",
    "L": "40",
    "XL": "42",
    "XXL": "44",
}
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
        "в наявності",
        "топ",
        "продажів",
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
    "cpm",
    "easydrop",
    "посилання на запрошення",
    "ссылка на приглашение",
    "invite link",
    "invitation link",
    "розмірна",
    "сітка",
    "опис",
    "характеристик",
)
_FORBIDDEN_NAME_HINTS = (
    "пакування",
    "коробка",
    "папір",
    "папир",
    "шнурки",
    "смаколики",
    "розмір",
    "розміри",
    "размер",
    "размеры",
    "матеріал",
    "материал",
    "виробник",
    "производитель",
    "дроп ціна",
    "дроп цена",
)
_SERVICE_MESSAGE_HINTS = (
    "security error while unpacking a received message",
    "server replied with a wrong session id",
    "see faq for details",
    "не удалось получить обсуждение",
    "не удалось прочитать обсуждение",
    "не удалось получить ответы из обсуждения",
    "не удалось восстановить peer",
    "discussion_chat_id=",
    "channel_id=",
    "message_ids=",
    "root_id=",
    "error=",
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
_MASKED_BRAND_INDEX: Optional[dict[int, list[tuple[str, str]]]] = None
_MULTIWORD_MASKED_BRAND_INDEX: Optional[
    dict[int, list[tuple[str, tuple[str, ...]]]]
] = None
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
_COLOR_NAME_TOKENS = frozenset(
    set(_COLOR_SYNONYMS)
    | {
        "blacks",
        "whites",
        "greys",
        "grays",
        "чорні",
        "чорна",
        "чорне",
        "черные",
        "чёрные",
        "черная",
        "чёрная",
        "черное",
        "чёрное",
        "білі",
        "біла",
        "біле",
        "белые",
        "белая",
        "белое",
        "сірі",
        "сіра",
        "сіре",
        "серые",
        "серая",
        "серое",
        "рожеві",
        "рожева",
        "рожеве",
        "розовые",
        "розовая",
        "розовое",
        "бежеві",
        "бежева",
        "бежеве",
        "бежевые",
        "бежевая",
        "бежевое",
        "кремові",
        "кремова",
        "кремове",
        "кремовые",
        "кремовая",
        "кремовое",
        "молочні",
        "молочна",
        "молочное",
        "молочные",
        "сині",
        "синя",
        "синє",
        "синие",
        "синяя",
        "синее",
        "зелені",
        "зелена",
        "зелене",
        "зеленые",
        "зеленая",
        "зеленое",
        "червоні",
        "червона",
        "червоне",
        "красные",
        "красная",
        "красное",
        "коричневі",
        "коричнева",
        "коричневе",
        "коричневые",
        "коричневая",
        "коричневое",
        "жовті",
        "жовта",
        "жовте",
        "желтые",
        "желтая",
        "желтое",
    }
)
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
sizes_dict = {
    # 94 размера
    "nizhnee-bele-i-kupalniki/lifchiki": [
        "nizhnee-bele-i-kupalniki/lifchiki",
        "nizhnee-bele-i-kupalniki/komplekty",
        "dlya-beremennyh/bele/byustgaltery"
    ],
    # 76 размеров
    "verhnyaya-odezhda/palto": [
        "verhnyaya-odezhda/palto",
        "verhnyaya-odezhda/plashi",
        "verhnyaya-odezhda/kurtki",
        "verhnyaya-odezhda/shuby",
        "verhnyaya-odezhda/zhiletki",
        "verhnyaya-odezhda/pidzhaki-i-zhakety",
        "verhnyaya-odezhda/puhoviki",
        "verhnyaya-odezhda/parki",
        "verhnyaya-odezhda/dublenki",
        "verhnyaya-odezhda/dozhdeviki",
        "verhnyaya-odezhda/vetrovki",
        "platya/mini",
        "platya/midi",
        "platya/maksi",
        "platya/vechernie",
        "platya/svadebnye",
        "platya/sarafany",
        "platya/tuniki",
        "yubki/mini",
        "yubki/midi",
        "yubki/maksi",
        "mayki-i-futbolki/futbolki",
        "mayki-i-futbolki/mayki",
        "mayki-i-futbolki/polo",
        "mayki-i-futbolki/topy",
        "rubashki-i-bluzy/rubashki",
        "rubashki-i-bluzy/bluzy",
        "rubashki-i-bluzy/vyshivanki",
        "kofty/dzhempery",
        "kofty/svitery",
        "kofty/kardigany",
        "kofty/vodolazki",
        "kofty/svitshoty",
        "kofty/hudi",
        "kofty/pulovery",
        "kofty/tolstovky",
        "kofty/nakidki",
        "kofty/bolero",
        "kofty/poncho",
        "kofty/reglan",
        "kofty/longslivy",
        "kofty/zhilety",
        "nizhnee-bele-i-kupalniki/trusiki",
        "nizhnee-bele-i-kupalniki/kupalniki",
        "nizhnee-bele-i-kupalniki/bodi",
        "nizhnee-bele-i-kupalniki/korsety",
        "nizhnee-bele-i-kupalniki/chulki",
        "nizhnee-bele-i-kupalniki/kolgotki",
        "nizhnee-bele-i-kupalniki/penyuary",
        "nizhnee-bele-i-kupalniki/termobelye",
        "nizhnee-bele-i-kupalniki/portupei",
        "nizhnee-bele-i-kupalniki/eroticheskoye",
        "nizhnee-bele-i-kupalniki/eroticheskiye-kostyumy",
        "nizhnee-bele-i-kupalniki/belyevyye-mayki",
        "nizhnee-bele-i-kupalniki/aksessuary",
        "sport-otdyh/sportivnyye-kostyumy",
        "sport-otdyh/sportivnyye-shtany",
        "sport-otdyh/losiny",
        "sport-otdyh/shorty",
        "sport-otdyh/topy",
        "sport-otdyh/kofty",
        "sport-otdyh/mayki",
        "sport-otdyh/kapri",
        "sport-otdyh/kombinezony",
        "sport-otdyh/belye",
        "sport-otdyh/gornolyzhnyye/kurtki",
        "sport-otdyh/gornolyzhnyye/kostyumy",
        "sport-otdyh/gornolyzhnyye/shtany",
        "sport-otdyh/gornolyzhnyye/kombinezony",
        "zhenskie-kostyumy/kostyumy-s-platem",
        "zhenskie-kostyumy/kostyumy-s-shortami",
        "zhenskie-kostyumy/kostyumy-s-yubkoj",
        "zhenskie-kostyumy/bryuchnye-kostyumy",
        "zhenskie-kombinezony/dzhinsovye-kombinezony",
        "zhenskie-kombinezony/bryuchnye-kombinezony",
        "zhenskie-kombinezony/kombinezony-s-shortami",
        "odezhda-dlya-doma-i-sna/domashnyaya-odezhda",
        "odezhda-dlya-doma-i-sna/pizhamy",
        "odezhda-dlya-doma-i-sna/nochnushki",
        "odezhda-dlya-doma-i-sna/halaty",
        "odezhda-dlya-doma-i-sna/masky-dlya-sna",
        "odezhda-dlya-doma-i-sna/kigurumi",
        "dlya-beremennyh/verhnyaya-odezhda",
        "dlya-beremennyh/platya",
        "dlya-beremennyh/sarafany",
        "dlya-beremennyh/futbolki",
        "dlya-beremennyh/shtany",
        "dlya-beremennyh/bele/kolgoty",
        "dlya-beremennyh/bele/bandazhi",
        "dlya-beremennyh/bele/trusy",
        "dlya-beremennyh/bele/komplekty",
        "dlya-beremennyh/bele/kupalnyky",
        "dlya-beremennyh/bele/halaty",
        "dlya-beremennyh/bele/pizhamy",
        "dlya-beremennyh/bele/sorochki",
        "dlya-beremennyh/drugoe",
        "dlya-beremennyh/losiny",
        "dlya-beremennyh/kombinezony",
        "dlya-beremennyh/kofty",
        "dlya-beremennyh/longslivy",
        "dlya-beremennyh/yubki",
        "dlya-beremennyh/rubashki",
        "shtany/bryuki",
        "shtany/losiny-i-legginsy",
        "shtany/shorty",
        "shtany/bridzhi",
        "dlya-beremennyh/platya"
    ],
    # 95 размеров — спецодежда
    "specodezhda/sfera-obsluzhivaniya": [
        "specodezhda/sfera-obsluzhivaniya",
        "specodezhda/medicinskaya",
        "specodezhda/rabochaya",
        "specodezhda/zashchitnaya",
        "specodezhda/akademicheskaya",
        "specodezhda/formennaya"
    ],
    # 65 размеров
    "dlya-beremennyh/dzhinsy": [
        "dlya-beremennyh/dzhinsy",
        "shtany/dzhinsy"
    ]
}

_TOP_TOKENS = (

# RU
"бомбер",
"майка","майки",
"футболка","футболки",
"кофта","кофты",
"свитер","свитера",
"толстовка",
"джемпер",
"рубашка",
"блузка",
"жакет",
"пиджак",
"кардиган",
"жилетка",
"жилет",

# UA
"майка",
"футболка",
"кофта",
"светр",
"светрик",
"сорочка",
"блуза",
"жакет",
"кардиган",
"жилетка",

# EN
"t-shirt",
"tshirt",
"tee",
"tank top",
"top",
"shirt",
"blouse",
"sweater",
"jumper",
"cardigan",
"hoodie",
"sweatshirt"
)
_OUTERWEAR_TOKENS = (

# RU
"куртка","куртки",
"пальто",
"плащ",
"ветровка",
"парка",

# UA
"куртка",
"пальто",
"плащ",
"вітровка",
"парка",

# EN
"jacket",
"coat",
"trench",
"windbreaker",
"parka"
)
_BOTTOM_TOKENS = (

# RU
"штаны",
"брюки",
"джинсы",
"шорты",
"юбка",
"лосины",
"леггинсы",

# UA
"штани",
"брюки",
"джинси",
"шорти",
"спідниця",
"лосини",
"легінси",

# EN
"pants",
"trousers",
"jeans",
"shorts",
"skirt",
"leggings"
)
_DRESS_TOKENS = (

# RU
"платье",
"сарафан",

# UA
"сукня",
"сарафан",

# EN
"dress",
"sundress"
)
_JUMPSUIT_TOKENS = (

# RU
"комбинезон",
"комбез",

# UA
"комбінезон",

# EN
"jumpsuit",
"romper",
"playsuit"
)
_SET_TOKENS = (

# RU
"костюм",
"комплект",
"набор",
"двойка",
"тройка",

# UA
"костюм",
"комплект",
"набір",
"двійка",
"трійка",

# EN
"set",
"outfit",
"matching set",
"two piece",
"two-piece"
)
_CLOTHES_NAME_HINTS = (
    _TOP_TOKENS
    + _BOTTOM_TOKENS
    + _OUTERWEAR_TOKENS
    + _DRESS_TOKENS
    + _JUMPSUIT_TOKENS
    + _SET_TOKENS
)
_PROMOTIONAL_NAME_WORDS = frozenset(
    {
        "new",
        "collection",
        "новинка",
        "новинки",
        "огляди",
        "обзоры",
        "огляд",
        "обзор",
        "реальні",
        "реальные",
        "real",
        "reviews",
        "review",
    }
)



def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _contains_hint_phrase(text: str, keywords: tuple[str, ...]) -> bool:
    normalized_text = text.casefold()
    for keyword in keywords:
        pattern = rf"(?<!\w){re.escape(keyword.casefold())}(?!\w)"
        if re.search(pattern, normalized_text):
            return True
    return False


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


def _get_document_filename(document) -> str:
    attributes = getattr(document, "attributes", None) or []
    for attr in attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return getattr(attr, "file_name", "") or ""
    return ""


def _is_image_document(document) -> bool:
    if not document:
        return False
    mime_type = (getattr(document, "mime_type", "") or "").strip().casefold()
    if not mime_type.startswith("image/"):
        return False
    if mime_type in UNSUPPORTED_IMAGE_MIME_TYPES:
        return False
    file_name = _get_document_filename(document).strip().casefold()
    if file_name and Path(file_name).suffix in UNSUPPORTED_IMAGE_EXTENSIONS:
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
        runtime_channels = get_telegram_channels()
        if runtime_channels:
            return [channel_id for channel_id, _, _ in runtime_channels]
        rows = load_telegram_channels()
        if rows:
            mirrored = [
                (int(row["channel_id"]), str(row["name"]), str(row.get("alias") or "main"))
                for row in rows
            ]
            set_telegram_channels(mirrored)
            return [row["channel_id"] for row in rows]
        return []
    ids: list[int] = []
    for part in re.split(r"[,\s]+", raw):
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


def _get_channel_alias(channel_id: int) -> str:
    for record in get_telegram_channel_records():
        if int(record["channel_id"]) == channel_id:
            return str(record.get("alias") or "")
    for row in load_telegram_channels():
        if row["channel_id"] == channel_id:
            return row.get("alias") or ""
    return ""


def _get_channel_record(channel_id: int) -> dict | None:
    for record in get_telegram_channel_records():
        if int(record["channel_id"]) == channel_id:
            return record
    for row in load_telegram_channels():
        if row["channel_id"] == channel_id:
            return row
    return None


async def _resolve_invite_entity(client: TelegramClient, link: str) -> object | None:
    invite_hash = extract_telegram_invite_hash(link)
    if not invite_hash:
        return None

    from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest

    try:
        invite_info = await client(CheckChatInviteRequest(invite_hash))
    except RPCError:
        invite_info = None
    else:
        entity = getattr(invite_info, "chat", None)
        if entity is not None:
            return entity

    try:
        result = await client(ImportChatInviteRequest(invite_hash))
    except RPCError as exc:
        if "USER_ALREADY_PARTICIPANT" not in str(exc).upper():
            return None
        try:
            invite_info = await client(CheckChatInviteRequest(invite_hash))
        except RPCError:
            return None
        return getattr(invite_info, "chat", None)

    chats = getattr(result, "chats", None) or []
    if chats:
        return chats[0]
    return getattr(result, "chat", None)


async def _resolve_channel_peer(client: TelegramClient, channel_id: int):
    record = _get_channel_record(channel_id) or {}
    source_link = str(record.get("source_link") or "").strip()
    if source_link:
        invite_entity = await _resolve_invite_entity(client, source_link)
        if invite_entity is not None:
            return invite_entity
        try:
            return await client.get_entity(source_link)
        except (ValueError, RPCError):
            pass
    dialog_entity = await _find_channel_peer_in_dialogs(client, channel_id)
    if dialog_entity is not None:
        return dialog_entity
    return channel_id


async def _find_channel_peer_in_dialogs(
    client: TelegramClient,
    channel_id: int,
) -> object | None:
    try:
        async for dialog in client.iter_dialogs():
            entity = getattr(dialog, "entity", None)
            if entity is not None and _peer_matches_channel_id(entity, channel_id):
                return entity
    except Exception:
        return None
    return None


def _peer_matches_channel_id(entity: object, channel_id: int) -> bool:
    try:
        return int(get_peer_id(entity)) == int(channel_id)
    except Exception:
        raw_id = getattr(entity, "id", None)
        if not isinstance(raw_id, int):
            return False
        return raw_id in _channel_id_variants(channel_id)


def _channel_id_variants(channel_id: int) -> set[int]:
    normalized = int(channel_id)
    variants = {normalized}
    if normalized > 0:
        variants.add(int(f"-100{normalized}"))
        return variants

    raw_text = str(abs(normalized))
    if raw_text.startswith("100") and len(raw_text) > 3:
        variants.add(int(raw_text[3:]))
    return variants


def _chat_entity_from_result(chats: list[object], channel_id: int) -> object | None:
    for chat in chats:
        if _peer_matches_channel_id(chat, channel_id):
            return chat
    return None


async def _sync_channel_titles(client: TelegramClient, channel_ids: list[int]) -> None:
    runtime_rows = {
        int(record["channel_id"]): record
        for record in get_telegram_channel_records()
    }
    db_rows = {row["channel_id"]: row for row in load_telegram_channels()}
    rows = runtime_rows or db_rows
    updates: list[dict[str, object]] = []
    for channel_id in channel_ids:
        current = rows.get(channel_id) or {}
        name = str(current.get("name") or "").strip()
        alias = current.get("alias")
        if name and name != str(channel_id):
            continue
        try:
            entity = await _resolve_channel_peer(client, channel_id)
            if isinstance(entity, int):
                entity = await client.get_entity(entity)
        except (ValueError, RPCError):
            continue
        title = getattr(entity, "title", None) or getattr(entity, "username", None)
        if title and title != name:
            updates.append(
                {
                    "channel_id": channel_id,
                    "name": title,
                    "alias": alias,
                    "source_link": current.get("source_link"),
                }
            )
    if updates:
        merged = {
            int(record["channel_id"]): record
            for record in get_telegram_channel_records()
        }
        for record in updates:
            merged[int(record["channel_id"])] = record
        set_telegram_channels(merged.values())
        save_telegram_channels(
            [
                (
                    int(record["channel_id"]),
                    str(record["name"]),
                    record.get("alias"),
                )
                for record in updates
            ]
        )


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
        if ch == "👕":
            cleaned.append(ch)
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
        if _is_service_message_line(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _is_service_message_line(line: str) -> bool:
    lowered = line.casefold()
    return any(hint in lowered for hint in _SERVICE_MESSAGE_HINTS)


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


def _looks_like_article_line(line: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?i)арт(?:\.|икул)?\s*[:№#-]?\s*[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9/_-]*",
            line.strip(),
        )
    )


def _looks_like_model_code_line(line: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?i)(?:модель|мод(?:\.|ель)?|арт(?:\.|икул)?|mod|mdl)"
            r"\s*[:№#-]?\s*[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9/_-]*",
            line.strip(),
        )
    )


def _is_garbage_name_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    if _looks_like_model_code_line(text):
        return True
    if _looks_like_size_details_line(text):
        return True
    lower = text.casefold()
    compact = re.sub(r"[\s()]+", "", lower)
    if re.fullmatch(r"\d+", compact):
        return True
    if re.fullmatch(r"\d{2}(?:[.,]\d+)?[-–]\d{2}(?:[.,]\d+)?", compact):
        return True
    if re.search(
        r"(?<![A-Za-zА-Яа-яІіЇїЄєҐґ])пар(?:и)?(?![A-Za-zА-Яа-яІіЇїЄєҐґ])",
        lower,
    ):
        return True
    return False


def _looks_like_size_details_line(line: str) -> bool:
    normalized = unicodedata.normalize("NFKC", line)
    compact = normalized.casefold()
    if not re.search(r"\b\d{2,3}\s*[йыі]?\s*\(\s*\d{1,2}(?:[.,]\d+)?\s*(?:см|cm)\s*\)", compact):
        return False
    return len(
        re.findall(
            r"\b\d{2,3}\s*[йыі]?\s*\(\s*\d{1,2}(?:[.,]\d+)?\s*(?:см|cm)\s*\)",
            compact,
        )
    ) >= 2


def _format_model_name(text: str) -> str:
    parts: list[str] = []
    for token in text.split():
        if token.islower() and any(ch.isalpha() for ch in token):
            parts.append(token[:1].upper() + token[1:])
        else:
            parts.append(token)
    return " ".join(parts)


def _clean_model_name(value: str) -> str:
    text = _clean_name(value)
    text = re.sub(
        r"\([^)]*\b(?:унісекс|унисекс|unisex)\b[^)]*\)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[^\w\s.\-/]+", " ", text, flags=re.UNICODE)
    tokens: list[str] = []
    for raw_token in text.split():
        normalized = _normalize_token(raw_token)
        if not normalized:
            continue
        if normalized in _GENERIC_NAME_TOKENS:
            continue
        if normalized in _COLOR_NAME_TOKENS:
            continue
        if normalized in _COLOR_MODIFIERS:
            continue
        tokens.append(raw_token.strip(".,;:()[]{}"))
    cleaned = " ".join(token for token in tokens if token)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" \t-–—|:;")
    return _format_model_name(cleaned)


def _is_valid_model_name(name: str, *, strict: bool = False) -> bool:
    if _is_garbage_name_line(name):
        return False
    words = [word for word in name.split() if word]
    if strict and len(words) < 2:
        return False
    if not any(any(ch.isalpha() for ch in word) for word in words):
        return False
    return True


def _clean_selected_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    cleaned: list[str] = []
    for ch in text:
        if ch == "\t":
            cleaned.append(" ")
            continue
        if ch in {"\u200d", "\ufe0f", "\ufe0e"}:
            continue
        cat = unicodedata.category(ch)
        if cat in {"Cc", "Cf", "So", "Sk"}:
            continue
        cleaned.append(ch)
    text = "".join(cleaned)
    text = re.sub(r"^[•*#>\-–—\s]+", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" \t-–—|:;")


def _has_forbidden_name_hint(name: str) -> bool:
    return _contains_hint_phrase(name, _FORBIDDEN_NAME_HINTS)


def _is_valid_selected_name(name: str) -> bool:
    text = name.strip()
    if not text:
        return False
    if _is_garbage_name_line(text):
        return False
    lower = text.casefold()
    if _contains_hint_phrase(lower, _NON_NAME_HINTS) or _contains_hint_phrase(
        lower, _NAME_EXCLUDE_HINTS
    ):
        return False
    if _has_forbidden_name_hint(text):
        return False
    if _line_has_url(text) or "@" in text:
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    return True


def _extract_shirt_name(lines: list[str]) -> str:
    for line in lines:
        if not line.lstrip().startswith("👕"):
            continue
        candidate = _clean_selected_name(line)
        if _is_valid_selected_name(candidate):
            return candidate
    return ""


def _extract_article_name(lines: list[str]) -> str:
    for idx, line in enumerate(lines[:-1]):
        if not _looks_like_article_line(line):
            continue
        candidate = _clean_selected_name(lines[idx + 1])
        if _is_valid_selected_name(candidate):
            return candidate
    return ""


def _normalize_token(token: str) -> str:
    return re.sub(r"[^\w]+", "", token, flags=re.UNICODE).casefold()


def _normalize_masked_brand_token(token: str) -> str:
    return unicodedata.normalize("NFKC", token).casefold()


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
        elif normalized in _GENERIC_NAME_TOKENS:
            idx += 1
            continue
        elif normalized in _OUTERWEAR_TOKENS:
            idx += 1
            continue
        elif normalized in _BOTTOM_TOKENS:
            idx += 1
            continue
        elif normalized in _DRESS_TOKENS:
            idx += 1
            continue
        elif normalized in _JUMPSUIT_TOKENS:
            idx += 1
            continue
        elif normalized in _SET_TOKENS:
            idx += 1
            continue
        elif normalized in _TOP_TOKENS:
            idx += 1
            continue
        else:
            break
    if idx > 0 and idx < len(tokens):
        return " ".join(tokens[idx:])
    return text


def _looks_like_name(line: str) -> bool:
    if _is_garbage_name_line(line):
        return False
    if _looks_like_article_line(line):
        return False
    if len(line) < 3 or len(line) > 120:
        return False
    lower = line.casefold()
    if (
        _contains_hint_phrase(lower, _NON_NAME_HINTS)
        or _contains_hint_phrase(lower, _NAME_EXCLUDE_HINTS)
        or _contains_hint_phrase(lower, _FORBIDDEN_NAME_HINTS)
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

def _looks_like_article(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9\-]{3,}", text))

def extract_description(lines: list[str]) -> str:

    material_line = ""
    color_line = ""
    size_line = ""
    mod_line = ""

    capture = False
    sizes_lines = []

    for line in lines:
        clean_line = re.sub(r"^[^\wА-Яа-яA-Za-z]+", "", line.lstrip("▫️•- ")).strip()
        if not material_line:
            match_material = re.search(
                r"(?i)тканина[:\s]*([\w\s\(\)%\-\u2013;/]+)", clean_line
            )

            if match_material:
                material_line = match_material.group(1)

        if not color_line:
            match_color = re.search(
                r"(?i)(?:колір|кольори)[:\s]*([\w\s\(\)%\-\u2013;/]+)", clean_line
            )
            if match_color:
                color_line = match_color.group(1)

        if not size_line:
            match_size = re.search(
                r"(?i)(?:розмірна\s*сітка|розміри|розмір|size)[:\s]*([\w\s\(\)%\-\u2013;/]+)", 
                clean_line
            )
            if match_size:
                size_line = match_size.group(1)

        if not mod_line:
            match_mod = re.search(
                r"(?i)\b(?:модель|мод(?:\.|ель)?|арт(?:\.|икул)?|mod|mdl)\b[\s:№.-]*([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9\-_/]*)",
                clean_line
            )
            if match_mod:
                mod_line = match_mod.group(1)

        if not capture and re.search(r"(?i)замір|заміри|виміри", clean_line):
            capture = True
            continue

        if capture:
            if re.match(r"(?i)по всім питанням", clean_line):
                capture = False
                continue
            clean_line = re.sub(r"^[▫️•\-]\s*", "", clean_line)
            if clean_line:
                sizes_lines.append(clean_line)

    sizes_text = "\n".join(sizes_lines)
    sizes_block = f"Заміри:\n{sizes_text}\n" if sizes_lines else ""
    mod_block = f"Модель: {mod_line}\n" if mod_line else ""        
    size_block = f"Розмір: {size_line}\n" if size_line else ""
    color_block = f"Колір: {color_line}\n" if color_line else ""
    material_block = f"Тканина: {material_line}\n" if material_line else ""

    description = (
        "\n"
        "Параметри та доступні розміри уточнюйте в повідомленнях. Якщо виникнуть додаткові запитання — пишіть у чат, із радістю відповім.\n"
        "Стильна річ для створення сучасного та впевненого образу. Добре поєднується з різними елементами гардеробу та підходить як для повсякденного носіння, так і для особливих випадків. Приємний матеріал забезпечує комфорт протягом усього дня, а універсальний дизайн легко вписується у будь-який стиль — від класичного до casual.\n"
        f"{material_block}\n"
        f"{color_block}\n"
        f"{size_block}\n"
        f"{mod_block}\n"
        f"{sizes_block}\n"
        "Виробництво: Україна"
    )
    return description


def clean_line_name(line: str) -> str:
    cleaned = re.sub(r"[^\w\s\.\-,]", "", line)
    cleaned = cleaned.strip()
    return cleaned

def capitalise_first_word(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s[0].upper() + s[1:]

def _extract_word_for_slack(lines: list[str], name: str = "") -> str:
    sources = ([name] if name else []) + list(lines)
    for source in sources:
        lower_words = source.casefold().split()
        if any(bad in lower_words for bad in _NON_NAME_HINTS + _NAME_EXCLUDE_HINTS):
            continue
        for word in lower_words:
            word_found = find_word(word)
            if word_found:
                return word_found
    return ""


def _is_strong_name_candidate(candidate: str, word_for_slack: str) -> bool:
    if not candidate:
        return False
    if _contains_catalog_word(candidate):
        return True
    if _has_brand_signal_in_text(candidate):
        return True
    return False


def _is_clothing_catalog_slug(catalog_slug: Optional[str]) -> bool:
    return bool(catalog_slug) and catalog_slug not in {
        DEFAULT_SHOES_CATEGORY,
        WOMEN_SNEAKERS_CATEGORY,
    }


def _is_promotional_name_line(line: str) -> bool:
    cleaned = _clean_selected_name(line)
    if not cleaned:
        return False
    normalized_words = [
        _normalize_token(token)
        for token in cleaned.split()
        if _normalize_token(token)
    ]
    if not normalized_words:
        return False
    return all(word in _PROMOTIONAL_NAME_WORDS for word in normalized_words)


def _contains_catalog_word(text: str) -> bool:
    for token in re.findall(
        r"[A-Za-zА-Яа-яІіЇїЄєҐґ]+(?:-[A-Za-zА-Яа-яІіЇїЄєҐґ]+)?",
        text,
    ):
        if find_word(token.casefold()):
            return True
    return False


def _clean_clothing_name_candidate(value: str) -> str:
    candidate = capitalise_first_word(_clean_selected_name(value))
    candidate = re.split(r"\s*[!?\.]+\s*", candidate, maxsplit=1)[0]
    candidate = re.sub(r"\s{2,}", " ", candidate)
    return candidate.strip(" \t-–—|:;,")


def _is_valid_clothing_name_candidate(candidate: str, word_for_slack: str) -> bool:
    if not candidate or not _is_valid_selected_name(candidate):
        return False
    lower = candidate.casefold()
    if word_for_slack and _contains_hint_phrase(lower, (word_for_slack,)):
        return True
    if _contains_hint_phrase(lower, _CLOTHES_NAME_HINTS):
        return True
    return _contains_catalog_word(candidate)


_GENERIC_BRAND_TOKENS = frozenset(
    {
        "new",
        "sale",
        "hit",
        "look",
        "style",
        "season",
        "collection",
        "oversize",
        "premium",
        "original",
        "lux",
        "fashion",
        "trend",
        "trendy",
        "best",
        "top",
        "brand",
        "made",
    }
)

_CLOTHING_BRAND_LINE_SKIP_HINTS = (
    "тканина",
    "ткань",
    "матеріал",
    "материал",
    "розмір",
    "розміри",
    "размер",
    "размеры",
    "size",
    "сітка",
    "сетк",
    "колір",
    "кольори",
    "цвет",
    "цвета",
    "ціна",
    "цена",
    "грн",
    "uah",
    "₴",
    "made in",
)


def _has_clothing_brand_context(lines: list[str], name: str, word_for_slack: str) -> bool:
    catalog_slug = find_slug_by_word(word_for_slack) if word_for_slack else None
    if _is_clothing_catalog_slug(catalog_slug):
        return True
    if _contains_catalog_word(name):
        return True
    return any(_contains_catalog_word(line) for line in lines)


def _clean_brand_candidate_token(token: str) -> str:
    return token.strip(".,;:()[]{}<>\"'`|/\\!?+-")


def _is_probable_brand_candidate_token(token: str) -> bool:
    cleaned = _clean_brand_candidate_token(token)
    if not cleaned or not re.search(r"[A-Za-z]", cleaned):
        return False
    normalized = re.sub(r"[^A-Za-z0-9]+", "", cleaned).casefold()
    if len(normalized) < 2:
        return False
    if normalized in _GENERIC_BRAND_TOKENS:
        return False
    if cleaned.islower():
        return False
    letters = sum(ch.isalpha() for ch in cleaned)
    return letters >= 2 or "&" in cleaned


def _score_brand_candidate_token(token: str) -> float:
    cleaned = _clean_brand_candidate_token(token)
    score = 0.0
    if any(ch.isupper() for ch in cleaned):
        score += 0.5
    if cleaned.isupper():
        score += 0.35
    if any(ch in "&.'-" for ch in cleaned):
        score += 0.2
    if cleaned[:1].isupper():
        score += 0.15
    if any(ch.isdigit() for ch in cleaned):
        score += 0.05
    return score


def _extract_probable_clothing_brand(line: str) -> str:
    cleaned_line = _clean_selected_name(line)
    if not cleaned_line:
        return ""
    tokens = re.findall(r"[A-Za-z0-9&.'-]+", cleaned_line)
    best_candidate = ""
    best_score = float("-inf")
    current_tokens: list[str] = []

    def flush_current() -> None:
        nonlocal best_candidate, best_score, current_tokens
        if not current_tokens:
            return
        candidate = " ".join(_clean_brand_candidate_token(token) for token in current_tokens)
        candidate = re.sub(r"\s{2,}", " ", candidate).strip()
        if not candidate:
            current_tokens = []
            return
        score = sum(_score_brand_candidate_token(token) for token in current_tokens)
        if len(current_tokens) > 1:
            score += 0.2
        if score > best_score:
            best_score = score
            best_candidate = candidate
        current_tokens = []

    for token in tokens:
        if _is_probable_brand_candidate_token(token):
            current_tokens.append(token)
            continue
        flush_current()
    flush_current()

    return best_candidate if best_score >= 0.5 else ""


def _has_brand_signal_in_text(text: str) -> bool:
    if _find_best_brand_in_text(text):
        return True
    return bool(_extract_probable_clothing_brand(text))


def _should_skip_clothing_brand_line(line: str) -> bool:
    lower = line.casefold()
    if _looks_like_model_code_line(line):
        return True
    return _contains_any(lower, _CLOTHING_BRAND_LINE_SKIP_HINTS)


def _score_clothing_name_candidate(candidate: str, word_for_slack: str, index: int) -> float:
    score = _score_name_line(candidate)
    lower = candidate.casefold()
    words = len(candidate.split())
    if _contains_hint_phrase(lower, _CLOTHES_NAME_HINTS):
        score += 0.45
    if word_for_slack and _contains_hint_phrase(lower, (word_for_slack,)):
        score += 0.35
    if 2 <= words <= 12:
        score += 0.15
    elif words == 1:
        score -= 0.2
    score += max(0, 0.08 - (index * 0.01))
    return score


def _extract_clothing_name(lines: list[str], word_for_slack: str) -> str:
    best_name = ""
    best_score = float("-inf")
    for idx, line in enumerate(lines):
        if _is_promotional_name_line(line):
            continue
        if len(line) < 3 or len(line) > 220:
            continue
        if not _looks_like_name(line) and not _contains_catalog_word(line):
            continue
        candidate = _clean_clothing_name_candidate(line)
        if not _is_valid_clothing_name_candidate(candidate, word_for_slack):
            continue
        score = _score_clothing_name_candidate(candidate, word_for_slack, idx)
        if score > best_score:
            best_score = score
            best_name = candidate
    return best_name


def extract_name(lines: list[str]) -> tuple[str, str]:
    shirt_name = _extract_shirt_name(lines)
    if shirt_name:
        return shirt_name, _extract_word_for_slack(lines, shirt_name)

    word_for_slack = _extract_word_for_slack(lines)
    catalog_slug = find_slug_by_word(word_for_slack) if word_for_slack else None
    if _is_clothing_catalog_slug(catalog_slug):
        clothing_name = _extract_clothing_name(lines, word_for_slack)
        if clothing_name:
            return clothing_name, word_for_slack or ""
        return "", word_for_slack or ""

    article_name = _extract_article_name(lines)
    if article_name:
        return article_name, _extract_word_for_slack(lines, article_name)

    for line in lines:
        match = re.search(rf"(?i)^(?:{'|'.join(_NAME_LABELS)})\s*[:\-]\s*(.+)$", line)
        if match:
            candidate = _clean_name(match.group(1))
            if candidate and not _looks_like_article(candidate):
                return candidate, word_for_slack or ""
    for line in lines:
        match = re.search(
            r"(?i)^(?:отримали|получили|поступили|поступление|завезли)\s+(?:новинк\w*\s+)?(.+)$",
            line,
        )
        if match:
            candidate = _clean_name(match.group(1))
            if candidate and _is_strong_name_candidate(candidate, word_for_slack):
                return candidate, word_for_slack or ""
    for line in lines:
        match = re.search(
            r"(?i)\b(?:анонс(?:уємо)?|анонсуємо|новинк\w*|new)\b[:\-]?\s*(.+)", line
        )
        if match:
            candidate = _clean_name(match.group(1))
            if candidate and _is_strong_name_candidate(candidate, word_for_slack):
                return candidate, word_for_slack or ""
    for line in lines[:3]:
        if not _looks_like_name(line):
            continue
        candidate = capitalise_first_word(clean_line_name(line))
        if _is_strong_name_candidate(candidate, word_for_slack):
            return candidate, word_for_slack or ""
    for line in lines:
        if not _looks_like_name(line):
            continue
        candidate = capitalise_first_word(clean_line_name(line))
        if _is_strong_name_candidate(candidate, word_for_slack):
            return candidate, word_for_slack or ""
    return "", word_for_slack or ""


def _infer_word_for_slack(lines: list[str], name: str) -> str:
    return _extract_word_for_slack(lines, name)


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


def _looks_like_standalone_price_line(line: str) -> bool:
    # Fallback price parsing should work only for mostly numeric lines
    # to avoid treating model numbers in product names as prices.
    cleaned = re.sub(r"[\d\s.,:/()+\-–—$€£₴]", "", line)
    return cleaned == ""


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
        if not _looks_like_standalone_price_line(line):
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
    normalized = normalize_size_text(token)
    if normalized in _ALPHA_SIZES or (
        normalized and re.fullmatch(r"(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|XXXXL)-(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|XXXXL)", normalized)
    ):
        return normalized
    text = token.strip().upper()
    if text.replace(",", ".").replace(".", "", 1).isdigit():
        value = text.replace(",", ".")
        if value.endswith(".0"):
            value = value[:-2]
        return value
    return ""


def _extract_size_tokens_from_line(
    line: str,
    even_range_step: bool = False,
) -> list[str]:
    tokens: list[str] = []
    alpha_range_spans: list[tuple[int, int]] = []
    lower = line.casefold()
    if re.search(r"\bone\s*size\b", lower):
        tokens.append("ONE SIZE")
    for match in re.finditer(
        r"\b(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|XXXXL)\s*[/\-]\s*"
        r"(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|XXXXL)\b",
        line.upper(),
    ):
        normalized = _normalize_size_token(match.group(0))
        if normalized:
            tokens.append(normalized)
            alpha_range_spans.append(match.span())
    for match in re.finditer(
        r"\b(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|XXXXL|OS)\b",
        line.upper(),
    ):
        if any(
            span_start <= match.start() and match.end() <= span_end
            for span_start, span_end in alpha_range_spans
        ):
            continue
        tokens.append(match.group(0))
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
        step = 2 if even_range_step and (end - start) >= 2 and start % 2 == end % 2 else 1
        for value in range(start, end + 1, step):
            tokens.append(str(value))
    cleaned = re.sub(
        r"\b\d{2,3}(?:[.,]\d+)?\s*(?:см|cm)\b", "", line, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"(?<=\b\d{2})\s*,\s*(?=\d{2}\b)", " ", cleaned)
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


def extract_sizes(
    lines: list[str],
    even_range_step: bool = False,
) -> tuple[str, list[str]]:
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

    if hinted_lines:
        for line in hinted_lines:
            for token in _extract_size_tokens_from_line(
                line,
                even_range_step=even_range_step,
            ):
                if token not in sizes:
                    sizes.append(token)
    else:
        for line in fallback_lines:
            tokens = _extract_size_tokens_from_line(
                line,
                even_range_step=even_range_step,
            )
            if not tokens:
                continue
            if len(tokens) < 2:
                cleaned = re.sub(r"[\d\s.,:/()+\-–—]", "", line)
                if cleaned:
                    continue
            for token in tokens:
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


def _load_masked_brand_index() -> dict[int, list[tuple[str, str]]]:
    global _MASKED_BRAND_INDEX
    if _MASKED_BRAND_INDEX is not None:
        return _MASKED_BRAND_INDEX
    index: dict[int, list[tuple[str, str]]] = {}
    seen: set[str] = set()
    for raw_name in list_brand_names():
        name = str(raw_name).strip()
        if not name:
            continue
        normalized = _normalize_masked_brand_token(name)
        if not normalized or not normalized.isalnum():
            continue
        if " " in normalized or normalized in seen:
            continue
        seen.add(normalized)
        index.setdefault(len(normalized), []).append((name, normalized))
    _MASKED_BRAND_INDEX = index
    return index


def _load_multiword_masked_brand_index() -> dict[int, list[tuple[str, tuple[str, ...]]]]:
    global _MULTIWORD_MASKED_BRAND_INDEX
    if _MULTIWORD_MASKED_BRAND_INDEX is not None:
        return _MULTIWORD_MASKED_BRAND_INDEX
    index: dict[int, list[tuple[str, tuple[str, ...]]]] = {}
    seen: set[tuple[str, ...]] = set()
    for raw_name in list_brand_names():
        name = str(raw_name).strip()
        if not name:
            continue
        parts = tuple(
            normalized
            for normalized in (_normalize_masked_brand_token(part) for part in name.split())
            if normalized and normalized.isalnum()
        )
        if len(parts) < 2 or parts in seen:
            continue
        seen.add(parts)
        index.setdefault(len(parts), []).append((name, parts))
    _MULTIWORD_MASKED_BRAND_INDEX = index
    return index


def _find_exact_brand_match_in_text(
    text: str,
) -> tuple[int, int, int, str] | None:
    best_match: tuple[int, int, int, str] | None = None
    for name, pattern in _load_brand_patterns():
        match = pattern.search(text)
        if not match:
            continue
        candidate = (match.start(), 0, -len(name), name)
        if best_match is None or candidate < best_match:
            best_match = candidate
    return best_match


def _find_brand_in_text(text: str) -> str:
    if not text:
        return ""
    match = _find_exact_brand_match_in_text(text)
    return match[3] if match else ""


def _trim_masked_brand_token(raw_token: str) -> tuple[str, int]:
    strip_chars = ".,;:()[]{}<>\"'"
    leading = len(raw_token) - len(raw_token.lstrip(strip_chars))
    return raw_token.strip(strip_chars), leading


_LEET_BRAND_CHAR_SUBSTITUTIONS = {
    "0": frozenset({"o"}),
    "1": frozenset({"i", "l", "e"}),
    "2": frozenset({"z"}),
    "3": frozenset({"e"}),
    "4": frozenset({"a"}),
    "5": frozenset({"s"}),
    "6": frozenset({"g"}),
    "7": frozenset({"t"}),
    "8": frozenset({"b"}),
    "9": frozenset({"g", "q"}),
    "y": frozenset({"u"}),
}


def _split_masked_brand_token(raw_token: str) -> tuple[str, str, str]:
    strip_chars = ".,;:()[]{}<>\"'"
    leading_len = len(raw_token) - len(raw_token.lstrip(strip_chars))
    trailing_len = len(raw_token) - len(raw_token.rstrip(strip_chars))
    leading = raw_token[:leading_len]
    trailing = raw_token[len(raw_token) - trailing_len :] if trailing_len else ""
    core = raw_token[leading_len : len(raw_token) - trailing_len if trailing_len else len(raw_token)]
    return leading, core, trailing


def _is_masked_brand_token(token: str) -> bool:
    if len(token) < 3:
        return False
    alpha_count = sum(ch.isalpha() for ch in token)
    wildcard_like_count = sum(
        1
        for ch in token
        if not ch.isalnum() or ch in _LEET_BRAND_CHAR_SUBSTITUTIONS
    )
    if alpha_count < 2 or wildcard_like_count == 0 or wildcard_like_count > 2:
        return False
    if any(ch in _LEET_BRAND_CHAR_SUBSTITUTIONS for ch in token) and len(token) < 4:
        return False
    return True


def _matches_masked_brand_token(masked_token: str, candidate: str) -> bool:
    if len(masked_token) != len(candidate):
        return False
    for masked_char, candidate_char in zip(masked_token, candidate):
        if masked_char == candidate_char:
            continue
        if not masked_char.isalnum():
            continue
        if candidate_char in _LEET_BRAND_CHAR_SUBSTITUTIONS.get(masked_char, ()):
            continue
        if masked_char.isalnum():
            return False
    return True


def _find_masked_brand_match_in_text(
    text: str,
) -> tuple[int, int, int, str] | None:
    if not text:
        return None
    best_match: tuple[int, int, int, str] | None = None
    masked_brand_index = _load_masked_brand_index()
    for token_match in re.finditer(r"[^\s|,/]+", text):
        raw_token = token_match.group(0)
        token, leading_trim = _trim_masked_brand_token(raw_token)
        if not _is_masked_brand_token(token):
            continue
        normalized_token = _normalize_masked_brand_token(token)
        candidates = [
            display_name
            for display_name, normalized_brand in masked_brand_index.get(
                len(normalized_token),
                [],
            )
            if _matches_masked_brand_token(normalized_token, normalized_brand)
        ]
        unique_candidates = list(dict.fromkeys(candidates))
        if len(unique_candidates) != 1:
            continue
        display_name = unique_candidates[0]
        candidate = (
            token_match.start() + leading_trim,
            1,
            -len(display_name),
            display_name,
        )
        if best_match is None or candidate < best_match:
            best_match = candidate
    return best_match


def _token_matches_brand_part(token: str, brand_part: str) -> bool:
    normalized_token = _normalize_masked_brand_token(token)
    if not normalized_token or not brand_part:
        return False
    if normalized_token == brand_part:
        return True
    if _is_masked_brand_token(token):
        return _matches_masked_brand_token(normalized_token, brand_part)
    return False


def _find_multiword_masked_brand_match_in_text(
    text: str,
) -> tuple[int, int, int, str] | None:
    if not text:
        return None
    best_match: tuple[int, int, int, str] | None = None
    token_matches = list(re.finditer(r"[^\s|,/]+", text))
    if len(token_matches) < 2:
        return None
    multiword_brand_index = _load_multiword_masked_brand_index()
    for part_count, brands in multiword_brand_index.items():
        if len(token_matches) < part_count:
            continue
        for start in range(len(token_matches) - part_count + 1):
            window = token_matches[start : start + part_count]
            cleaned_tokens = []
            for match in window:
                token, _ = _trim_masked_brand_token(match.group(0))
                if not token:
                    break
                cleaned_tokens.append(token)
            if len(cleaned_tokens) != part_count:
                continue
            candidates = [
                display_name
                for display_name, brand_parts in brands
                if all(
                    _token_matches_brand_part(token, brand_part)
                    for token, brand_part in zip(cleaned_tokens, brand_parts)
                )
            ]
            unique_candidates = list(dict.fromkeys(candidates))
            if len(unique_candidates) != 1:
                continue
            display_name = unique_candidates[0]
            candidate = (
                window[0].start(),
                1,
                -len(display_name),
                display_name,
            )
            if best_match is None or candidate < best_match:
                best_match = candidate
    return best_match


def _find_best_brand_in_text(text: str) -> str:
    if not text:
        return ""
    candidates = [
        candidate
        for candidate in (
            _find_exact_brand_match_in_text(text),
            _find_masked_brand_match_in_text(text),
            _find_multiword_masked_brand_match_in_text(text),
        )
        if candidate is not None
    ]
    if not candidates:
        return ""
    return min(candidates)[3]


def _canonicalize_name_brand(name: object, brand: object) -> str:
    text = str(name or "")
    brand_text = str(brand or "").strip()
    if not text or not brand_text:
        return text
    brand_tokens = [token for token in brand_text.split() if token]
    if len(brand_tokens) > 1:
        name_tokens = [token for token in text.split() if token]
        max_overlap = min(len(brand_tokens), len(name_tokens))
        for overlap in range(max_overlap, 0, -1):
            brand_suffix = brand_tokens[-overlap:]
            name_prefix = name_tokens[:overlap]
            if not all(
                _brand_token_matches_name_token(brand_token, name_token)
                for brand_token, name_token in zip(brand_suffix, name_prefix)
            ):
                continue
            remaining_tokens = name_tokens[overlap:]
            return " ".join([brand_text, *remaining_tokens]).strip()
        return text
    normalized_brand = _normalize_masked_brand_token(brand_text)
    if not normalized_brand or not normalized_brand.isalnum():
        return text

    parts: list[str] = []
    last_end = 0
    replaced = False
    for token_match in re.finditer(r"[^\s|,/]+", text):
        raw_token = token_match.group(0)
        leading, core, trailing = _split_masked_brand_token(raw_token)
        if (
            not replaced
            and _is_masked_brand_token(core)
            and _matches_masked_brand_token(
                _normalize_masked_brand_token(core),
                normalized_brand,
            )
        ):
            replacement = f"{leading}{brand_text}{trailing}"
            parts.append(text[last_end : token_match.start()])
            parts.append(replacement)
            last_end = token_match.end()
            replaced = True
    if not replaced:
        return text
    parts.append(text[last_end:])
    return "".join(parts)


def _brand_token_matches_name_token(brand_token: str, name_token: str) -> bool:
    _, brand_core, _ = _split_masked_brand_token(brand_token)
    _, name_core, _ = _split_masked_brand_token(name_token)
    normalized_brand = _normalize_masked_brand_token(brand_core)
    normalized_name = _normalize_masked_brand_token(name_core)
    if not normalized_brand or not normalized_name:
        return False
    if normalized_brand == normalized_name:
        return True
    if _is_masked_brand_token(name_core):
        return _matches_masked_brand_token(normalized_name, normalized_brand)
    return False


def _fallback_brand_from_name(name: str) -> str:
    if not name:
        return ""
    best_token = ""
    best_score = float("-inf")
    for index, token in enumerate(name.split()):
        normalized = _normalize_token(token)
        if not normalized or normalized in _GENERIC_NAME_TOKENS:
            continue
        if not normalized or normalized in _OUTERWEAR_TOKENS:
            continue
        if not normalized or normalized in _TOP_TOKENS:
            continue
        if not normalized or normalized in _BOTTOM_TOKENS:
            continue
        if not normalized or normalized in _JUMPSUIT_TOKENS:
            continue
        if not normalized or normalized in _SET_TOKENS:
            continue
        if not normalized or normalized in _DRESS_TOKENS:
            continue
        if normalized in _COLOR_NAME_TOKENS or normalized in _COLOR_MODIFIERS:
            continue
        if normalized in _PROMOTIONAL_NAME_WORDS:
            continue

        cleaned = token.strip(".,;:()[]{}")
        if not cleaned:
            continue

        score = index * 0.05
        has_latin = bool(re.search(r"[A-Za-z]", cleaned))
        has_cyrillic = bool(re.search(r"[А-Яа-яІіЇїЄєҐґ]", cleaned))
        if has_latin:
            score += 1.0
            if not has_cyrillic:
                score += 0.3
        if cleaned[:1].isupper():
            score += 0.2
        if any(ch.isdigit() for ch in cleaned):
            score += 0.2
        if any(ch in "&+-" for ch in cleaned):
            score += 0.2
        if len(normalized) <= 10:
            score += 0.1

        if score > best_score:
            best_score = score
            best_token = cleaned
    if best_token and best_score >= 0.8:
        return best_token
    return ""


def extract_brand(lines: list[str], name: str, word_for_slack: str = "") -> str:
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
                brand = _find_best_brand_in_text(value)
                if brand:
                    return brand
                normalized = _normalize_token(value)
                if normalized and normalized not in _GENERIC_NAME_TOKENS:
                    return value
    cleaned_name = _strip_name_prefix(name)
    brand = _find_best_brand_in_text(cleaned_name)
    if brand:
        return brand
    for line in lines:
        brand = _find_best_brand_in_text(line)
        if brand:
            return brand
    if _has_clothing_brand_context(lines, name, word_for_slack):
        for line in lines:
            if _should_skip_clothing_brand_line(line):
                continue
            brand = _extract_probable_clothing_brand(line)
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
    name, word_for_slack = extract_name(lines)
    slug = find_slug_by_word(word_for_slack)
    description = extract_description(lines)
    brand = extract_brand(lines, name, word_for_slack)
    normalized_name = _canonicalize_name_brand(name, brand)
    size, additional_sizes = extract_sizes(
        lines,
        even_range_step=_should_use_even_clothing_size_ranges(slug),
    )
    color = extract_colors(lines, name)
    price = extract_price(lines)
    confidence = _calculate_confidence(name, price, size, brand, color)



    return {
        "description": description,
        "name": normalized_name,
        "word_for_slack": word_for_slack,
        "brand": brand,
        "size": size,
        "additional_sizes": additional_sizes,
        "color": color,
        "price": price,
        "confidence": confidence,
    }


def get_runtime_mode() -> str:
    raw = os.getenv(APP_MODE_ENV, MODE_CLOTHES).strip().lower()
    if raw not in {MODE_CLOTHES, MODE_SNEAKERS}:
        return MODE_CLOTHES
    return raw


def _current_account_id() -> str:
    raw = str(os.getenv("SHAFA_ACCOUNT_ID") or ACCOUNT_ID).strip()
    return raw or "default"


def is_valid_product_price(price: object) -> bool:
    parsed_price = _parse_price(price)
    if parsed_price is None or parsed_price <= 0:
        return False
    digits_count = len(str(abs(int(parsed_price))))
    return MIN_PRODUCT_PRICE_DIGITS <= digits_count <= MAX_PRODUCT_PRICE_DIGITS


def should_run_first_fetch() -> bool:
    return get_runtime_mode() == MODE_CLOTHES and not telegram_products_exist(
        account_id=_current_account_id()
    )


def _telegram_fetch_scope() -> str:
    return f"telegram_feed:{_current_account_id()}:{get_runtime_mode()}"


def _telegram_fetch_cooldown_seconds() -> int:
    raw = os.getenv("SHAFA_TELEGRAM_FETCH_COOLDOWN_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TELEGRAM_FETCH_COOLDOWN_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TELEGRAM_FETCH_COOLDOWN_SECONDS
    return min(max(value, 0), 3600)


def _telegram_fetch_lease_seconds(cooldown_seconds: Optional[int] = None) -> int:
    raw = os.getenv("SHAFA_TELEGRAM_FETCH_LEASE_SECONDS", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = DEFAULT_TELEGRAM_FETCH_LEASE_SECONDS
        return min(max(value, 10), 7200)
    if cooldown_seconds is None:
        cooldown_seconds = _telegram_fetch_cooldown_seconds()
    return max(DEFAULT_TELEGRAM_FETCH_LEASE_SECONDS, cooldown_seconds * 2 or 10)


def _telegram_fetch_wait_seconds() -> float:
    raw = os.getenv("SHAFA_TELEGRAM_FETCH_WAIT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TELEGRAM_FETCH_WAIT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TELEGRAM_FETCH_WAIT_SECONDS
    return min(max(value, 0.0), 30.0)


def _claim_shared_telegram_fetch() -> tuple[str, Optional[str]]:
    cooldown_seconds = _telegram_fetch_cooldown_seconds()
    return claim_telegram_fetch(
        _telegram_fetch_scope(),
        min_interval_seconds=cooldown_seconds,
        lease_seconds=_telegram_fetch_lease_seconds(cooldown_seconds),
    )


def _finish_shared_telegram_fetch(lease_token: Optional[str], *, success: bool) -> None:
    if not lease_token:
        return
    finish_telegram_fetch(
        _telegram_fetch_scope(),
        lease_token,
        success=success,
    )


def _telegram_channel_scan_interval_seconds() -> int:
    raw = os.getenv("SHAFA_TELEGRAM_CHANNEL_SCAN_INTERVAL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TELEGRAM_CHANNEL_SCAN_INTERVAL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TELEGRAM_CHANNEL_SCAN_INTERVAL_SECONDS
    return min(max(value, 30), 7200)


def _telegram_channel_scan_lease_seconds(interval_seconds: Optional[int] = None) -> int:
    raw = os.getenv("SHAFA_TELEGRAM_CHANNEL_SCAN_LEASE_SECONDS", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = DEFAULT_TELEGRAM_CHANNEL_SCAN_LEASE_SECONDS
        return min(max(value, 30), 7200)
    if interval_seconds is None:
        interval_seconds = _telegram_channel_scan_interval_seconds()
    return max(DEFAULT_TELEGRAM_CHANNEL_SCAN_LEASE_SECONDS, interval_seconds * 2)


def _telegram_channel_scan_scope(channel_id: int) -> str:
    return f"telegram_channel_scan:{_current_account_id()}:{int(channel_id)}"


def _claim_due_telegram_channel(channel_ids: list[int]) -> tuple[Optional[int], Optional[str], str]:
    if not channel_ids:
        return None, None, "no_channels"
    interval_seconds = _telegram_channel_scan_interval_seconds()
    lease_seconds = _telegram_channel_scan_lease_seconds(interval_seconds)
    saw_in_progress = False
    for channel_id in channel_ids:
        status, lease_token = claim_telegram_fetch(
            _telegram_channel_scan_scope(channel_id),
            min_interval_seconds=interval_seconds,
            lease_seconds=lease_seconds,
        )
        if status == "acquired":
            return channel_id, lease_token, status
        if status == "in_progress":
            saw_in_progress = True
    return None, None, "in_progress" if saw_in_progress else "not_due"


def _finish_due_telegram_channel(
    channel_id: int,
    lease_token: Optional[str],
    *,
    success: bool,
) -> None:
    if not lease_token:
        return
    finish_telegram_fetch(
        _telegram_channel_scan_scope(channel_id),
        lease_token,
        success=success,
    )


def is_mode_allowed_parsed(parsed: dict) -> bool:
    if get_runtime_mode() != MODE_SNEAKERS:
        return True
    word_for_slack = str(parsed.get("word_for_slack") or "").strip().lower()
    if word_for_slack in {"sneakers", "slack"}:
        return True
    additional_sizes = parsed.get("additional_sizes", [])
    if not isinstance(additional_sizes, list):
        additional_sizes = []
    size_value = parsed.get("size")
    numeric_sizes = [
        numeric_size
        for value in [size_value, *additional_sizes]
        for numeric_size in _extract_numeric_sizes(value)
    ]
    if not numeric_sizes:
        return False
    category = _resolve_catalog_slug(parsed.get("size"), additional_sizes, word_for_slack)
    return category in {DEFAULT_SHOES_CATEGORY, WOMEN_SNEAKERS_CATEGORY}


def catalog_supports_brand(catalog_slug: Optional[str]) -> bool:
    return bool(catalog_slug) and (
        catalog_slug in {DEFAULT_SHOES_CATEGORY, WOMEN_SNEAKERS_CATEGORY}
        or _is_clothing_catalog_slug(catalog_slug)
    )


async def first_fetch() -> int:
    result = await scan_account_telegram_channels_async(
        batch_size=DEFAULT_TELEGRAM_SCAN_BATCH_SIZE
    )
    return int(result["inserted"])

async def _fetch_messages(message_amount: int = 200) -> int:
    batch_size = min(
        max(int(message_amount or DEFAULT_TELEGRAM_SCAN_BATCH_SIZE), 1),
        DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
    )
    result = await scan_account_telegram_channels_async(batch_size=batch_size)
    return int(result["inserted"])


def _new_scan_stats() -> dict[str, int]:
    return {
        "fetched": 0,
        "processed": 0,
        "saved": 0,
        "duplicate": 0,
        "no_media": 0,
        "non_photo_media": 0,
        "no_text": 0,
        "mode_filtered": 0,
        "missing_name": 0,
        "missing_price": 0,
        "invalid_price": 0,
        "missing_size": 0,
        "parsed_ok": 0,
    }


def _classify_product_message(msg) -> tuple[Optional[dict], Optional[str]]:
    if not getattr(msg, "media", None):
        return None, "no_media"
    if not _is_photo_message(msg):
        return None, "non_photo_media"
    raw_message = getattr(msg, "message", None)
    if not raw_message:
        return None, "no_text"
    parsed = parse_message(raw_message)
    if not is_mode_allowed_parsed(parsed):
        return None, "mode_filtered"
    if not parsed.get("name"):
        return None, "missing_name"
    if not parsed.get("price"):
        return None, "missing_price"
    if not is_valid_product_price(parsed.get("price")):
        return None, "invalid_price"
    if not parsed.get("size"):
        return None, "missing_size"
    return parsed, None


def _scan_batch_result() -> dict[str, Optional[int] | str]:
    return {
        "inserted": 0,
        "duplicates": 0,
        "last_processed_message_id": None,
        "error_message": None,
    }


def _telegram_product_max_age_days() -> int:
    raw = os.getenv("SHAFA_TELEGRAM_PRODUCT_MAX_AGE_DAYS", "").strip()
    if not raw:
        return DEFAULT_TELEGRAM_PRODUCT_MAX_AGE_DAYS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TELEGRAM_PRODUCT_MAX_AGE_DAYS
    return max(value, 1)


def _telegram_backfill_cutoff_utc() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=_telegram_product_max_age_days())


def _old_product_deactivate_batch_size() -> int:
    raw = os.getenv("SHAFA_OLD_PRODUCT_DEACTIVATE_BATCH_SIZE", "").strip()
    if not raw:
        return DEFAULT_OLD_PRODUCT_DEACTIVATE_BATCH_SIZE
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_OLD_PRODUCT_DEACTIVATE_BATCH_SIZE
    return min(max(value, 1), 100)


def _old_product_deactivate_sleep_seconds() -> float:
    raw = os.getenv("SHAFA_OLD_PRODUCT_DEACTIVATE_SLEEP_SECONDS", "").strip()
    if not raw:
        return DEFAULT_OLD_PRODUCT_DEACTIVATE_SLEEP_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_OLD_PRODUCT_DEACTIVATE_SLEEP_SECONDS
    return min(max(value, 0.0), 60.0)


def _shared_deactivation_dry_run() -> bool:
    raw = os.getenv("SHAFA_SHARED_DEACTIVATION_DRY_RUN", "").strip()
    if not raw:
        auto_run = os.getenv("SHAFA_SHARED_DEACTIVATION_AUTO_RUN", "").strip()
        return auto_run not in {"1", "true", "TRUE", "yes", "YES", "on", "ON"}
    return raw in {"1", "true", "TRUE", "yes", "YES", "on", "ON"}


def _shared_deactivation_scan_seconds() -> float:
    raw = os.getenv("SHAFA_SHARED_DEACTIVATION_SCAN_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SHARED_DEACTIVATION_SCAN_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_SHARED_DEACTIVATION_SCAN_SECONDS
    return min(max(value, 1.0), 300.0)


def _shared_deactivation_cooldown_range_seconds() -> tuple[float, float]:
    def _read(name: str, default: float) -> float:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    min_seconds = min(
        max(
            _read(
                "SHAFA_DEACTIVATION_COOLDOWN_MIN_SECONDS",
                DEFAULT_SHARED_DEACTIVATION_COOLDOWN_MIN_SECONDS,
            ),
            0.0,
        ),
        300.0,
    )
    max_seconds = min(
        max(
            _read(
                "SHAFA_DEACTIVATION_COOLDOWN_MAX_SECONDS",
                DEFAULT_SHARED_DEACTIVATION_COOLDOWN_MAX_SECONDS,
            ),
            min_seconds,
        ),
        300.0,
    )
    return min_seconds, max_seconds


def _is_shafa_product_not_found_error(exc: BaseException) -> bool:
    message = " ".join(str(exc or "").split()).lower()
    if not message:
        return False
    if any(
        marker in message
        for marker in (
            "csrftoken",
            "cookie",
            "authenticated",
            "authentication",
            "session",
        )
    ):
        return False
    product_markers = ("product", "products", "includeids", "include_ids", "товар")
    if any(
        marker in message
        for marker in (
            "product_not_found",
            "product not found",
            "product not_found",
            "товар не найден",
            "товар не знайден",
        )
    ):
        return True
    has_product_context = any(marker in message for marker in product_markers)
    if not has_product_context:
        return False
    return any(
        marker in message
        for marker in (
            "not_found",
            "notfound",
            "not found",
            "does not exist",
            "doesn't exist",
            "не найден",
            "не знайден",
        )
    )


def _message_datetime_utc(message) -> Optional[datetime]:
    value = getattr(message, "date", None)
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime_text_utc(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_age_duration(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"


def _next_old_product_age_check_batch(
    products: list[dict],
    *,
    limit: int,
    account_id: str,
    source_label: str,
) -> list[dict]:
    if not products:
        return []
    batch_size = min(max(int(limit), 1), len(products))
    if batch_size >= len(products):
        _OLD_PRODUCT_AGE_CHECK_CURSOR[(account_id, source_label)] = 0
        return products[:batch_size]

    cursor_key = (account_id, source_label)
    start_index = _OLD_PRODUCT_AGE_CHECK_CURSOR.get(cursor_key, 0) % len(products)
    selected = [
        products[(start_index + offset) % len(products)]
        for offset in range(batch_size)
    ]
    _OLD_PRODUCT_AGE_CHECK_CURSOR[cursor_key] = (
        start_index + batch_size
    ) % len(products)
    return selected


def _normalize_product_lookup_text(text: object) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(part for part in value.split() if part)


def _product_lookup_tokens(text: object) -> list[str]:
    return [
        token
        for token in _normalize_product_lookup_text(text).split()
        if len(token) >= 2 or token.isdigit()
    ]


def _build_telegram_product_name_search_queries(product_name: str) -> list[str]:
    raw_name = str(product_name or "").strip()
    if not raw_name:
        return []
    queries = [raw_name]
    seen = {_normalize_product_lookup_text(raw_name)}
    for token in sorted(
        re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ0-9]+", raw_name),
        key=len,
        reverse=True,
    ):
        if len(token) < 4 and not token.isdigit():
            continue
        normalized = _normalize_product_lookup_text(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        queries.append(token)
        if len(queries) >= 4:
            break
    return queries


def _score_product_name_match(expected_name: object, candidate_name: object) -> float:
    normalized_expected = _normalize_product_lookup_text(expected_name)
    normalized_candidate = _normalize_product_lookup_text(candidate_name)
    if not normalized_expected or not normalized_candidate:
        return 0.0
    if normalized_expected == normalized_candidate:
        return 1.0
    if (
        normalized_expected in normalized_candidate
        or normalized_candidate in normalized_expected
    ):
        return 0.95
    expected_tokens = set(_product_lookup_tokens(expected_name))
    candidate_tokens = set(_product_lookup_tokens(candidate_name))
    if not expected_tokens or not candidate_tokens:
        return 0.0
    overlap = expected_tokens & candidate_tokens
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(expected_tokens)
    precision = len(overlap) / len(candidate_tokens)
    return round((coverage * 0.75) + (precision * 0.25), 4)


def _message_preview_text(raw_message: object, *, max_length: int = 120) -> str:
    preview = " ".join(str(raw_message or "").split())
    if len(preview) <= max_length:
        return preview
    return preview[: max_length - 3].rstrip() + "..."


def _old_product_cleanup_account_label(account_id: object) -> str:
    account_name = str(os.getenv("SHAFA_ACCOUNT_NAME") or "").strip()
    normalized_account_id = str(account_id or "").strip() or "default"
    return account_name or normalized_account_id


def _safe_old_product_log(level: str, message: str) -> None:
    try:
        log(level, message)
    except Exception:
        pass


def _log_value(value: object) -> str:
    return str(value or "").replace('"', '\\"')


def _old_product_channel_label(channel_id: object) -> str:
    try:
        normalized_channel_id = int(channel_id)
    except (TypeError, ValueError):
        return "unknown"
    channel_record = _get_channel_record(normalized_channel_id) or {}
    channel_name = str(channel_record.get("name") or "").strip()
    if channel_name:
        return f"{channel_name}({normalized_channel_id})"
    return str(normalized_channel_id)


def _old_product_int(value: object) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _select_telegram_product_by_message_id(
    message_id: Optional[int],
    product_name: str,
    telegram_by_message_id: dict[int, list[dict]],
) -> Optional[dict]:
    if message_id is None:
        return None
    candidates = telegram_by_message_id.get(int(message_id)) or []
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    scored = sorted(
        (
            (_score_product_name_match(product_name, item.get("product_name")), item)
            for item in candidates
        ),
        key=lambda pair: (
            -float(pair[0]),
            str(pair[1].get("telegram_message_date") or ""),
            int(pair[1].get("message_id") or 0),
        ),
    )
    return scored[0][1]


def _select_telegram_product_by_title(
    product_name: str,
    telegram_products: list[dict],
    *,
    min_match_score: float = 0.95,
) -> tuple[Optional[dict], bool]:
    normalized_name = str(product_name or "").strip()
    if not normalized_name:
        return None, False
    scored = sorted(
        (
            (_score_product_name_match(normalized_name, item.get("product_name")), item)
            for item in telegram_products
        ),
        key=lambda pair: (
            -float(pair[0]),
            str(pair[1].get("telegram_message_date") or ""),
            int(pair[1].get("message_id") or 0),
        ),
    )
    confident = [
        (score, item)
        for score, item in scored
        if float(score) >= float(min_match_score)
    ]
    if not confident:
        return None, False
    if len(confident) > 1 and float(confident[0][0]) == float(confident[1][0]):
        return None, True
    return confident[0][1], False


def _log_old_product_check(
    *,
    level: str,
    account_label: str,
    product_name: str,
    product_id: Optional[str],
    message_id: Optional[int],
    telegram_found: bool,
    channel_id: Optional[int],
    message_date: object,
    age_days: Optional[int],
    action: str,
    reason: Optional[str] = None,
) -> None:
    parts = [
        f'{account_label} Product="{_log_value(product_name)}"',
        f"product_id={product_id or 'unknown'}",
        f"message_id={message_id if message_id is not None else 'unknown'}",
        f"telegram_found={str(bool(telegram_found)).lower()}",
        f'telegram_channel="{_log_value(_old_product_channel_label(channel_id))}"',
        f"message_date={message_date or 'unknown'}",
        f"age={age_days if age_days is not None else 'unknown'}",
        "operation=deactivate",
        f"action={action}",
    ]
    if reason:
        parts.append(f'reason="{_log_value(reason)}"')
    _safe_old_product_log(level, " ".join(parts))


async def _find_telegram_name_matches_in_channel(
    client: TelegramClient,
    channel_id: int,
    product_name: str,
    *,
    per_channel_limit: int,
) -> list[dict]:
    channel_peer = await _resolve_channel_peer(client, channel_id)
    unique_messages: dict[int, Any] = {}
    search_limit = max(per_channel_limit * 4, per_channel_limit)
    for search_query in _build_telegram_product_name_search_queries(product_name):
        async for msg in client.iter_messages(
            channel_peer,
            search=search_query,
            limit=search_limit,
        ):
            message_id = getattr(msg, "id", None)
            if not isinstance(message_id, int) or message_id in unique_messages:
                continue
            unique_messages[message_id] = msg

    channel_record = _get_channel_record(channel_id) or {}
    matches: list[dict] = []
    for message_id, msg in unique_messages.items():
        raw_message = str(getattr(msg, "message", "") or "")
        if not raw_message.strip():
            continue
        try:
            parsed = parse_message(raw_message)
        except Exception:
            parsed = {}
        parsed_name = _canonicalize_name_brand(parsed.get("name"), parsed.get("brand"))
        score = _score_product_name_match(product_name, parsed_name)
        if score <= 0.0:
            score = _score_product_name_match(product_name, raw_message)
        if score < 0.55:
            continue
        message_date = _message_datetime_utc(msg)
        matches.append(
            {
                "channel_id": channel_id,
                "channel_name": (
                    str(channel_record.get("name") or "").strip() or str(channel_id)
                ),
                "message_id": message_id,
                "parsed_name": parsed_name or str(parsed.get("name") or "").strip(),
                "raw_message_preview": _message_preview_text(raw_message),
                "score": score,
                "telegram_message_date": (
                    message_date.isoformat() if message_date is not None else None
                ),
            }
        )

    matches.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["message_id"]),
        )
    )
    return matches[:per_channel_limit]


async def find_telegram_matches_by_product_name_async(
    product_name: str,
    *,
    per_channel_limit: int = 5,
    telegram_client_cls: Any | None = None,
) -> list[dict]:
    normalized_name = str(product_name or "").strip()
    if not normalized_name:
        return []
    channel_ids = _get_channel_ids()
    if not channel_ids:
        return []
    normalized_limit = max(int(per_channel_limit), 1)
    api_id_value, api_hash_value = _require_telegram_credentials()
    account_id = _current_account_id()
    client_factory = telegram_client_cls or TelegramClient
    matches: list[dict] = []
    async with create_telegram_client(
        TELEGRAM_SESSION_PATH,
        api_id_value,
        api_hash_value,
        save_entities=False,
        telegram_client_cls=client_factory,
        account_id=account_id,
    ) as client:
        await _sync_channel_titles(client, channel_ids)
        for channel_id in channel_ids:
            try:
                matches.extend(
                    await _find_telegram_name_matches_in_channel(
                        client,
                        channel_id,
                        normalized_name,
                        per_channel_limit=normalized_limit,
                    )
                )
            except Exception as exc:
                log(
                    "WARN",
                    "Не удалось выполнить поиск товара в Telegram. "
                    f"channel_id={channel_id}. error={exc}",
                )
    matches.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["message_id"]),
        )
    )
    return matches


def find_telegram_matches_by_product_name(
    product_name: str,
    *,
    per_channel_limit: int = 5,
) -> list[dict]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            find_telegram_matches_by_product_name_async(
                product_name,
                per_channel_limit=per_channel_limit,
            )
        )
    raise RuntimeError(
        "find_telegram_matches_by_product_name cannot be called when an event loop "
        "is running. Use find_telegram_matches_by_product_name_async."
    )


def inspect_shafa_product_telegram_age(
    product_name: str,
    *,
    older_than_days: Optional[int] = None,
    per_channel_limit: int = 5,
    min_match_score: float = DEFAULT_AUTO_DEACTIVATE_TELEGRAM_MATCH_SCORE,
) -> dict[str, object]:
    normalized_name = str(product_name or "").strip()
    age_days = (
        _telegram_product_max_age_days()
        if older_than_days is None
        else max(int(older_than_days), 1)
    )
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(days=age_days)
    result: dict[str, object] = {
        "product_name": normalized_name,
        "older_than_days": age_days,
        "min_match_score": float(min_match_score),
        "evaluated_at_utc": now_utc.isoformat(),
        "cutoff_utc": cutoff_utc.isoformat(),
        "matches_found": 0,
        "eligible_for_deactivation": False,
        "status": "empty_name",
        "decision_reason": "Пустое название товара Shafa.",
        "telegram_age_days": None,
        "best_match": None,
        "matches": [],
    }
    if not normalized_name:
        return result

    matches = find_telegram_matches_by_product_name(
        normalized_name,
        per_channel_limit=per_channel_limit,
    )
    result["matches"] = matches
    result["matches_found"] = len(matches)
    if not matches:
        result["status"] = "not_found"
        result["decision_reason"] = (
            "Совпадения по названию товара в Telegram не найдены."
        )
        return result

    confident_match = next(
        (
            item
            for item in matches
            if float(item.get("score") or 0.0) >= float(min_match_score)
        ),
        None,
    )
    if confident_match is None:
        result["status"] = "low_confidence"
        result["best_match"] = matches[0]
        result["decision_reason"] = (
            "Найдены только совпадения с низким score, деактивация небезопасна."
        )
        return result

    telegram_message_dt = _parse_datetime_text_utc(
        confident_match.get("telegram_message_date")
    )
    enriched_match = dict(confident_match)
    if telegram_message_dt is not None:
        enriched_match["telegram_message_date"] = telegram_message_dt.isoformat()
        enriched_match["message_age_days"] = round(
            (now_utc - telegram_message_dt).total_seconds() / 86400.0,
            1,
        )
        result["telegram_age_days"] = enriched_match["message_age_days"]
    result["best_match"] = enriched_match
    if telegram_message_dt is None:
        result["status"] = "missing_message_date"
        result["decision_reason"] = (
            "Для найденного сообщения Telegram не удалось определить дату."
        )
        return result
    if telegram_message_dt > cutoff_utc:
        result["status"] = "not_old_enough"
        result["decision_reason"] = (
            "Возраст сообщения в Telegram меньше заданного порога."
        )
        return result

    result["status"] = "eligible"
    result["eligible_for_deactivation"] = True
    result["decision_reason"] = (
        "Возраст сообщения в Telegram равен или больше порога деактивации."
    )
    return result


def _deactivate_product_backend_not_configured(product_id: str) -> None:
    from core.requests.deactivate_product import deactivate_product

    deactivate_product(product_id)


def _table_exists_simple(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns_simple(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _extract_message_id_from_raw_payload_text(raw_payload: object) -> Optional[int]:
    text = str(raw_payload or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None

    def _walk(value: object) -> Optional[int]:
        if isinstance(value, dict):
            for key in (
                "message_id",
                "messageId",
                "telegram_message_id",
                "telegramMessageId",
            ):
                raw_message_id = value.get(key)
                if raw_message_id is None or str(raw_message_id).strip() == "":
                    continue
                try:
                    return int(raw_message_id)
                except (TypeError, ValueError):
                    continue
            for nested in value.values():
                found = _walk(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = _walk(item)
                if found is not None:
                    return found
        return None

    return _walk(payload)


def _log_old_product_sql_snapshot(
    *,
    account_id: str,
    threshold_days: int,
    preview_limit: int = 10,
) -> list[dict[str, object]]:
    uploaded_count: object = "unknown"
    telegram_count: object = "unknown"
    expired_count: object = "unknown"
    uploaded_rows: list[sqlite3.Row] = []
    telegram_rows: list[sqlite3.Row] = []

    try:
        uploaded_db_path = Path(DB_PATH)
        if uploaded_db_path.exists():
            with sqlite3.connect(uploaded_db_path) as conn:
                conn.row_factory = sqlite3.Row
                if _table_exists_simple(conn, "uploaded_products"):
                    uploaded_columns = _table_columns_simple(conn, "uploaded_products")
                    created_order_expr = (
                        "COALESCE(shafa_created_at, created_at)"
                        if "shafa_created_at" in uploaded_columns
                        else "created_at"
                    )
                    row = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM uploaded_products
                        WHERE product_id IS NOT NULL AND TRIM(product_id) != ''
                          AND COALESCE(is_active, 1) = 1
                        """
                    ).fetchone()
                    uploaded_count = int(row["count"] or 0) if row else 0
                    uploaded_rows = conn.execute(
                        """
                        SELECT
                            product_id,
                            name,
                            raw_payload
                        FROM uploaded_products
                        WHERE product_id IS NOT NULL AND TRIM(product_id) != ''
                          AND COALESCE(is_active, 1) = 1
                        ORDER BY {created_order_expr} ASC, product_id ASC
                        """
                        .format(created_order_expr=created_order_expr)
                    ).fetchall()
                else:
                    uploaded_count = "no_table"
        else:
            uploaded_count = "db_missing"
    except Exception as exc:
        uploaded_count = f"error:{exc}"

    try:
        telegram_db_path = Path(TELEGRAM_PRODUCTS_DB_PATH)
        if telegram_db_path.exists():
            with sqlite3.connect(telegram_db_path) as conn:
                conn.row_factory = sqlite3.Row
                if _table_exists_simple(conn, "telegram_products"):
                    row = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM telegram_products
                        WHERE account_id = ?
                          AND status = 'created'
                          AND created = 1
                          AND created_product_id IS NOT NULL
                          AND TRIM(created_product_id) != ''
                          AND created_product_id NOT LIKE 'SKIPPED_%'
                          AND shafa_deactivated_at IS NULL
                          AND shafa_deleted_at IS NULL
                        """,
                        (account_id,),
                    ).fetchone()
                    telegram_count = int(row["count"] or 0) if row else 0

                    row = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM telegram_products
                        WHERE account_id = ?
                          AND status = 'created'
                          AND created = 1
                          AND created_product_id IS NOT NULL
                          AND TRIM(created_product_id) != ''
                          AND created_product_id NOT LIKE 'SKIPPED_%'
                          AND telegram_message_date IS NOT NULL
                          AND TRIM(telegram_message_date) != ''
                          AND shafa_deactivated_at IS NULL
                          AND shafa_deleted_at IS NULL
                          AND datetime(telegram_message_date) <= datetime('now', ?)
                        """,
                        (account_id, f"-{threshold_days} days"),
                    ).fetchone()
                    expired_count = int(row["count"] or 0) if row else 0

                    telegram_rows = conn.execute(
                        """
                        SELECT
                            channel_id,
                            created_product_id,
                            message_id,
                            telegram_message_date,
                            ROUND(julianday('now') - julianday(telegram_message_date), 1)
                                AS age_days
                        FROM telegram_products
                        WHERE account_id = ?
                          AND status = 'created'
                          AND created = 1
                          AND created_product_id IS NOT NULL
                          AND TRIM(created_product_id) != ''
                          AND created_product_id NOT LIKE 'SKIPPED_%'
                          AND telegram_message_date IS NOT NULL
                          AND TRIM(telegram_message_date) != ''
                          AND shafa_deactivated_at IS NULL
                          AND shafa_deleted_at IS NULL
                        ORDER BY datetime(telegram_message_date) ASC, message_id ASC
                        """,
                        (account_id,),
                    ).fetchall()
                else:
                    telegram_count = "no_table"
                    expired_count = "no_table"
        else:
            telegram_count = "db_missing"
            expired_count = "db_missing"
    except Exception as exc:
        telegram_count = f"error:{exc}"
        expired_count = f"error:{exc}"

    telegram_by_product_id = {
        str(row["created_product_id"]): row
        for row in telegram_rows
        if str(row["created_product_id"] or "").strip()
    }
    telegram_by_message_id = {
        int(row["message_id"]): row
        for row in telegram_rows
        if str(row["message_id"] or "").strip()
    }
    now_utc = datetime.now(timezone.utc)
    preview_items: list[dict[str, object]] = []
    expired_uploaded_count = 0
    for uploaded_row in uploaded_rows:
        product_id = str(uploaded_row["product_id"] or "").strip()
        message_id = _extract_message_id_from_raw_payload_text(uploaded_row["raw_payload"])
        telegram_row = (
            telegram_by_message_id.get(message_id)
            if message_id is not None
            else None
        )
        if telegram_row is None:
            telegram_row = telegram_by_product_id.get(product_id)
        if telegram_row is None:
            continue
        telegram_date = str(telegram_row["telegram_message_date"] or "").strip()
        telegram_dt = _parse_datetime_text_utc(telegram_date)
        if telegram_dt is None:
            continue
        age_days = round((now_utc - telegram_dt).total_seconds() / 86400.0, 1)
        if age_days >= threshold_days:
            expired_uploaded_count += 1
        preview_items.append(
            {
                "product_id": product_id,
                "name": str(uploaded_row["name"] or "").strip(),
                "channel_id": int(telegram_row["channel_id"]),
                "message_id": int(telegram_row["message_id"]),
                "telegram_date": telegram_date,
                "age_days": age_days,
            }
        )
    preview_items.sort(
        key=lambda item: (
            str(item["telegram_date"]),
            str(item["product_id"]),
        )
    )

    log(
        "INFO",
        "SQL диагностика деактивации: "
        f"account_id={account_id}. "
        f"uploaded_active={uploaded_count}. "
        f"telegram_created={telegram_count}. "
        f"telegram_older_than_{threshold_days}_days={expired_count}. "
        f"uploaded_linked_older_than_{threshold_days}_days={expired_uploaded_count}.",
    )
    if not preview_items:
        log("INFO", "SQL диагностика деактивации: preview товаров аккаунта пустой.")
        return []
    for item in preview_items[: max(int(preview_limit), 1)]:
        log(
            "INFO",
            "SQL preview товара аккаунта для деактивации: "
            f"id_товара={item['product_id']}. "
            f"name=\"{_log_value(item['name'])}\". "
            f"message_id={item['message_id']}. "
            f"дней={item['age_days']}. "
            f"telegram_date={item['telegram_date']}.",
        )
    return preview_items


def _env_flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip() in {"1", "true", "TRUE", "yes", "YES"}


def _is_backfill_history_window_complete(
    cursor: dict,
    *,
    history_window_days: int,
) -> bool:
    if not bool(cursor.get("backfill_history_limit_reached")):
        return False
    completed_window_days = cursor.get("backfill_history_window_days")
    if not isinstance(completed_window_days, int):
        return False
    return completed_window_days >= history_window_days


def _process_scanned_messages(
    messages: list,
    *,
    channel_id: int,
    account_id: str,
    stats: dict[str, int],
) -> dict[str, Optional[int] | str]:
    result = _scan_batch_result()
    for msg in messages:
        message_id = getattr(msg, "id", None)
        if not isinstance(message_id, int):
            result["error_message"] = (
                f"Сообщение без корректного id в канале {channel_id}."
            )
            break
        try:
            parsed, skip_reason = _classify_product_message(msg)
        except Exception as exc:
            result["error_message"] = _scan_error_message(channel_id, message_id, exc)
            log("ERROR", str(result["error_message"]))
            break

        stats["processed"] += 1
        if parsed is None:
            if skip_reason:
                stats[skip_reason] = stats.get(skip_reason, 0) + 1
            result["last_processed_message_id"] = message_id
            continue

        stats["parsed_ok"] += 1
        if save_telegram_product(
            channel_id,
            message_id,
            getattr(msg, "message", "") or "",
            parsed,
            account_id=account_id,
            telegram_message_date=_message_datetime_utc(msg),
        ):
            result["inserted"] = int(result["inserted"] or 0) + 1
            stats["saved"] += 1
        else:
            result["duplicates"] = int(result["duplicates"] or 0) + 1
            stats["duplicate"] += 1
        result["last_processed_message_id"] = message_id
    return result


async def _load_messages_for_scan(
    client: TelegramClient,
    channel_peer,
    *,
    last_checked_message_id: Optional[int],
    batch_size: int,
) -> list:
    if last_checked_message_id is None:
        return []

    messages: list = []
    async for msg in client.iter_messages(
        channel_peer,
        min_id=last_checked_message_id,
        limit=batch_size,
        reverse=True,
    ):
        message_id = getattr(msg, "id", None)
        if not isinstance(message_id, int) or message_id <= last_checked_message_id:
            continue
        messages.append(msg)
    return messages


async def _load_messages_for_backfill(
    client: TelegramClient,
    channel_peer,
    *,
    backfill_before_message_id: Optional[int],
    batch_size: int,
) -> tuple[list, bool]:
    if backfill_before_message_id is None or backfill_before_message_id <= 1:
        return [], False

    messages: list = []
    cutoff_utc = _telegram_backfill_cutoff_utc()
    history_limit_reached = False
    async for msg in client.iter_messages(
        channel_peer,
        max_id=backfill_before_message_id,
        limit=batch_size,
    ):
        message_id = getattr(msg, "id", None)
        if (
            not isinstance(message_id, int)
            or message_id >= backfill_before_message_id
        ):
            continue
        message_datetime_utc = _message_datetime_utc(msg)
        if message_datetime_utc is not None and message_datetime_utc < cutoff_utc:
            history_limit_reached = True
            break
        messages.append(msg)
    return messages, history_limit_reached


async def _load_latest_message_id_for_scan(
    client: TelegramClient,
    channel_peer,
) -> Optional[int]:
    async for msg in client.iter_messages(channel_peer, limit=1):
        message_id = getattr(msg, "id", None)
        if isinstance(message_id, int):
            return message_id
    return None


async def _resolve_live_scan_floor_message_id(
    client: TelegramClient,
    channel_peer,
    channel_id: int,
    *,
    account_id: str,
    last_checked_message_id: Optional[int],
) -> Optional[int]:
    if last_checked_message_id is not None:
        return int(last_checked_message_id)
    known_max_message_id = get_max_telegram_product_message_id(
        channel_id,
        account_id=account_id,
    )
    if known_max_message_id is not None:
        return int(known_max_message_id)
    return await _load_latest_message_id_for_scan(client, channel_peer)


def _resolve_backfill_floor_message_id(
    channel_id: int,
    *,
    account_id: str,
    backfill_before_message_id: Optional[int],
    live_scan_floor_message_id: Optional[int],
) -> Optional[int]:
    if backfill_before_message_id is not None:
        return int(backfill_before_message_id)
    if live_scan_floor_message_id is not None:
        return int(live_scan_floor_message_id)
    known_max_message_id = get_max_telegram_product_message_id(
        channel_id,
        account_id=account_id,
    )
    if known_max_message_id is not None:
        return int(known_max_message_id)
    return None


def _scan_error_message(
    channel_id: int,
    message_id: Optional[int],
    exc: Exception,
) -> str:
    if message_id is None:
        return (
            f"Не удалось просканировать канал {channel_id}: "
            f"{exc.__class__.__name__}: {exc}"
        )
    return (
        f"Не удалось обработать сообщение channel_id={channel_id} "
        f"message_id={message_id}: {exc.__class__.__name__}: {exc}"
    )


async def _scan_single_channel(
    client: TelegramClient,
    channel_id: int,
    *,
    account_id: str,
    batch_size: int,
) -> dict:
    stats = _new_scan_stats()
    inserted = 0
    duplicates = 0
    last_processed_message_id: Optional[int] = None
    live_scan_floor_message_id: Optional[int] = None
    backfill_before_message_id: Optional[int] = None
    backfill_last_processed_message_id: Optional[int] = None
    backfill_error_message: Optional[str] = None
    backfill_history_limit_reached = False
    backfill_attempted = False
    live_messages_fetched = 0
    backfill_messages_fetched = 0
    error_message: Optional[str] = None

    cursor = get_telegram_scan_cursor(channel_id, account_id=account_id)
    last_checked_message_id = cursor.get("last_checked_message_id")
    backfill_before_message_id = cursor.get("backfill_before_message_id")
    history_window_days = _telegram_product_max_age_days()
    mark_telegram_scan_started(channel_id, account_id=account_id)

    try:
        channel_peer = await _resolve_channel_peer(client, channel_id)
        live_scan_floor_message_id = await _resolve_live_scan_floor_message_id(
            client,
            channel_peer,
            channel_id,
            account_id=account_id,
            last_checked_message_id=last_checked_message_id,
        )
        messages = await _load_messages_for_scan(
            client,
            channel_peer,
            last_checked_message_id=live_scan_floor_message_id,
            batch_size=batch_size,
        )
        live_messages_fetched = len(messages)
        stats["fetched"] += live_messages_fetched
        live_result = _process_scanned_messages(
            messages,
            channel_id=channel_id,
            account_id=account_id,
            stats=stats,
        )
        inserted += int(live_result["inserted"] or 0)
        duplicates += int(live_result["duplicates"] or 0)
        last_processed_message_id = live_result["last_processed_message_id"]  # type: ignore[assignment]
        error_message = str(live_result["error_message"] or "") or None

        if (
            error_message is None
            and live_messages_fetched == 0
            and not _is_backfill_history_window_complete(
                cursor,
                history_window_days=history_window_days,
            )
        ):
            resolved_backfill_before = _resolve_backfill_floor_message_id(
                channel_id,
                account_id=account_id,
                backfill_before_message_id=backfill_before_message_id,
                live_scan_floor_message_id=live_scan_floor_message_id,
            )
            if resolved_backfill_before is not None and resolved_backfill_before > 1:
                backfill_attempted = True
                mark_telegram_backfill_started(channel_id, account_id=account_id)
                backfill_messages, backfill_history_limit_reached = await _load_messages_for_backfill(
                    client,
                    channel_peer,
                    backfill_before_message_id=resolved_backfill_before,
                    batch_size=batch_size,
                )
                backfill_messages_fetched = len(backfill_messages)
                stats["fetched"] += backfill_messages_fetched
                backfill_result = _process_scanned_messages(
                    backfill_messages,
                    channel_id=channel_id,
                    account_id=account_id,
                    stats=stats,
                )
                inserted += int(backfill_result["inserted"] or 0)
                duplicates += int(backfill_result["duplicates"] or 0)
                backfill_last_processed_message_id = backfill_result[
                    "last_processed_message_id"
                ]  # type: ignore[assignment]
                backfill_error_message = (
                    str(backfill_result["error_message"] or "") or None
                )
                next_backfill_before_message_id = resolved_backfill_before
                if backfill_error_message is None:
                    if backfill_history_limit_reached:
                        if backfill_last_processed_message_id is not None:
                            next_backfill_before_message_id = backfill_last_processed_message_id
                    elif backfill_last_processed_message_id is not None:
                        next_backfill_before_message_id = backfill_last_processed_message_id
                    elif backfill_messages_fetched == 0:
                        next_backfill_before_message_id = 1
                finish_telegram_backfill(
                    channel_id,
                    backfill_before_message_id=next_backfill_before_message_id,
                    account_id=account_id,
                    error_message=backfill_error_message,
                    history_limit_reached=(
                        True if backfill_error_message is None and backfill_history_limit_reached else None
                    ),
                    history_window_days=(
                        history_window_days
                        if backfill_error_message is None and backfill_history_limit_reached
                        else None
                    ),
                )
    except Exception as exc:
        error_message = _scan_error_message(channel_id, None, exc)
        log("ERROR", error_message)
    finally:
        finish_telegram_scan(
            channel_id,
            last_checked_message_id=(
                last_processed_message_id
                if last_processed_message_id is not None
                else live_scan_floor_message_id
            ),
            account_id=account_id,
            error_message=error_message,
        )

    return {
        "channel_id": channel_id,
        "inserted": inserted,
        "duplicates": duplicates,
        "live_messages_fetched": live_messages_fetched,
        "backfill_attempted": backfill_attempted,
        "backfill_messages_fetched": backfill_messages_fetched,
        "backfill_history_limit_reached": backfill_history_limit_reached,
        "backfill_last_processed_message_id": backfill_last_processed_message_id,
        "backfill_error_message": backfill_error_message,
        "last_processed_message_id": last_processed_message_id,
        "error_message": error_message,
        "stats": stats,
    }


async def scan_account_telegram_channels_async(
    batch_size: int = DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
) -> dict:
    channel_ids = _get_channel_ids()
    return await _scan_selected_telegram_channels_async(
        channel_ids,
        batch_size=batch_size,
    )


async def _scan_selected_telegram_channels_async(
    channel_ids: list[int],
    *,
    batch_size: int,
) -> dict:
    normalized_batch_size = min(
        max(int(batch_size or DEFAULT_TELEGRAM_SCAN_BATCH_SIZE), 1),
        DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
    )
    account_id = _current_account_id()
    api_id_value, api_hash_value = _require_telegram_credentials()
    inserted = 0
    duplicates = 0
    results: list[dict] = []
    if not channel_ids:
        return {
            "account_id": account_id,
            "batch_size": normalized_batch_size,
            "inserted": 0,
            "duplicates": 0,
            "channels": [],
        }
    async with create_telegram_client(
        TELEGRAM_SESSION_PATH,
        api_id_value,
        api_hash_value,
        save_entities=False,
        telegram_client_cls=TelegramClient,
    ) as client:
        for channel_id in channel_ids:
            channel_result = await _scan_single_channel(
                client,
                channel_id,
                account_id=account_id,
                batch_size=normalized_batch_size,
            )
            inserted += int(channel_result["inserted"])
            duplicates += int(channel_result["duplicates"])
            results.append(channel_result)
    return {
        "account_id": account_id,
        "batch_size": normalized_batch_size,
        "inserted": inserted,
        "duplicates": duplicates,
        "channels": results,
    }


async def scan_next_due_telegram_channel_async(
    batch_size: int = DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
) -> dict:
    channel_ids = _get_channel_ids()
    claimed_channel_id, lease_token, status = _claim_due_telegram_channel(channel_ids)
    if claimed_channel_id is None:
        return {
            "account_id": _current_account_id(),
            "batch_size": min(
                max(int(batch_size or DEFAULT_TELEGRAM_SCAN_BATCH_SIZE), 1),
                DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
            ),
            "status": status,
            "channel_id": None,
            "inserted": 0,
            "duplicates": 0,
            "channels": [],
        }

    try:
        result = await _scan_selected_telegram_channels_async(
            [claimed_channel_id],
            batch_size=batch_size,
        )
    except Exception:
        _finish_due_telegram_channel(claimed_channel_id, lease_token, success=False)
        raise

    _finish_due_telegram_channel(claimed_channel_id, lease_token, success=True)
    result["status"] = "scanned"
    result["channel_id"] = claimed_channel_id
    return result


def scan_account_telegram_channels(
    batch_size: int = DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
) -> dict:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(scan_account_telegram_channels_async(batch_size=batch_size))
    raise RuntimeError(
        "scan_account_telegram_channels cannot be called when an event loop is running. "
        "Use scan_account_telegram_channels_async."
    )


def scan_next_due_telegram_channel(
    batch_size: int = DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
) -> dict:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(scan_next_due_telegram_channel_async(batch_size=batch_size))
    raise RuntimeError(
        "scan_next_due_telegram_channel cannot be called when an event loop is running. "
        "Use scan_next_due_telegram_channel_async."
    )


async def _collect_group_messages(
    client: TelegramClient,
    channel_peer,
    message_id: int,
    grouped_id: int,
) -> list:
    min_id = max(1, message_id - 50)
    max_id = message_id + 50
    messages: list = []
    async for msg in client.iter_messages(channel_peer, min_id=min_id, max_id=max_id):
        if msg.grouped_id == grouped_id and _is_photo_message(msg):
            messages.append(msg)
    return messages


async def _collect_discussion_photos(
    client: TelegramClient,
    channel_peer,
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
    discussion_chat_id: Optional[int] = None
    discussion_peer = None
    root = None
    last_exc: Optional[Exception] = None
    for candidate_id in candidate_ids:
        try:
            candidate_result = await client(
                GetDiscussionMessageRequest(peer=channel_peer, msg_id=candidate_id)
            )
        except RPCError as exc:
            last_exc = exc
            continue
        if not candidate_result or not candidate_result.messages:
            continue
        chats = list(getattr(candidate_result, "chats", None) or [])
        candidate_discussion_chat_id: Optional[int] = None
        for msg in candidate_result.messages:
            chat_id = getattr(msg, "chat_id", None)
            if chat_id and chat_id != channel_id:
                candidate_discussion_chat_id = chat_id
                break
        if candidate_discussion_chat_id is None:
            for chat in chats:
                chat_id = get_peer_id(chat)
                if chat_id != channel_id:
                    candidate_discussion_chat_id = chat_id
                    discussion_peer = chat
                    break
        elif discussion_peer is None:
            discussion_peer = _chat_entity_from_result(
                chats,
                candidate_discussion_chat_id,
            )
        if not candidate_discussion_chat_id:
            result = candidate_result
            continue
        candidate_root = next(
            (
                msg
                for msg in candidate_result.messages
                if getattr(msg, "chat_id", None) == candidate_discussion_chat_id
            ),
            None,
        )
        if not candidate_root:
            result = candidate_result
            continue
        result = candidate_result
        discussion_chat_id = candidate_discussion_chat_id
        root = candidate_root
        break
    if not result or not result.messages or not discussion_chat_id or not root:
        if last_exc:
            preview = ", ".join(str(value) for value in candidate_ids[:5])
            suffix = "..." if len(candidate_ids) > 5 else ""
            log(
                "WARN",
                "Не удалось получить обсуждение для сообщения: "
                f"channel_id={channel_id} \n"
                + f"message_ids=[{preview}{suffix}]\n"
                + f"error={last_exc}.",
            )
        return []
    if discussion_peer is None:
        discussion_peer = _chat_entity_from_result(
            list(getattr(result, "chats", None) or []),
            discussion_chat_id,
        )
    if discussion_peer is None:
        log(
            "WARN",
            "Не удалось восстановить peer для чата обсуждения: "
            f"channel_id={channel_id} discussion_chat_id={discussion_chat_id}.",
        )
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
                discussion_peer,
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
        async for reply in client.iter_messages(discussion_peer, reply_to=root_id):
            await add_reply(reply)
    except RPCError as exc:
        if verbose_photo_logs_enabled():
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
            discussion_peer, limit=fallback_limit
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
            discussion_peer,
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
    message_ids: Optional[list[int]] = None,
) -> int:
    api_id_value, api_hash_value = _require_telegram_credentials()
    async with create_telegram_client(
        TELEGRAM_SESSION_PATH,
        api_id_value,
        api_hash_value,
        save_entities=False,
        telegram_client_cls=TelegramClient,
    ) as client:
        await _sync_channel_titles(client, _get_channel_ids())
        channel_peer = await _resolve_channel_peer(client, channel_id)
        verbose_photo_logs = verbose_photo_logs_enabled()
        if verbose_photo_logs:
            log(
                "INFO",
                "Скачиваю фото из Telegram: \n"
                + f"channel_id={channel_id}\n"
                + f"message_id={message_id}.",
            )        
        source_message_ids = [message_id]
        if message_ids:
            for candidate_id in message_ids:
                if candidate_id and candidate_id not in source_message_ids:
                    source_message_ids.append(candidate_id)
        messages: list = []
        resolved_source_message_ids: list[int] = []
        for candidate_id in source_message_ids:
            message = await client.get_messages(channel_peer, ids=candidate_id)
            if not message:
                continue
            if message.id not in resolved_source_message_ids:
                resolved_source_message_ids.append(message.id)
            if not _is_photo_message(message):
                continue
            messages.append(message)
        if not messages:
            return 0
        expanded_messages: list = []
        grouped_seen: set[int] = set()
        for message in messages:
            if message.grouped_id:
                if message.grouped_id in grouped_seen:
                    continue
                grouped_seen.add(message.grouped_id)
                grouped = await _collect_group_messages(
                    client,
                    channel_peer,
                    message.id,
                    message.grouped_id,
                )
                if grouped:
                    expanded_messages.extend(grouped)
                    continue
            expanded_messages.append(message)
        messages = expanded_messages or messages
        discussion_message_ids = list(resolved_source_message_ids)
        for msg in sorted(messages, key=lambda item: item.id):
            if msg.id not in discussion_message_ids:
                discussion_message_ids.append(msg.id)
        extra = await _collect_discussion_photos(
            client,
            channel_peer,
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
        for msg in messages:
            chat_id = getattr(msg, "chat_id", channel_id)
            key = (int(chat_id), msg.id)
            if key in seen:
                continue
            seen.add(key)
            size_bytes = _get_message_media_size_bytes(msg)
            queue.append((msg, chat_id, size_bytes))
        if max_photos > 0 and len(queue) > max_photos:
            if verbose_photo_logs:
                log("INFO", f"Ограничение на фото: {max_photos}.")
            queue = queue[:max_photos]
        if not queue:
            log("WARN", "Нет подходящих фото для скачивания.")
            return 0
        failed_downloads = 0
        skipped_total_limit = 0
        total_downloaded_bytes = 0
        max_mb = MAX_UPLOAD_BYTES / (1024 * 1024)
        with ProgressBar(
            total=len(queue),
            label="Скачивание фото",
            enabled=not verbose_photo_logs,
        ) as progress:
            for idx, (msg, chat_id, size_bytes) in enumerate(queue, start=1):
                if verbose_photo_logs:
                    size_label = _format_size_mb(size_bytes)
                    log(
                        "INFO",
                        f"Скачивание фото {idx}/{len(queue)}: "
                        f"message_id={msg.id} chat_id={chat_id} size={size_label}.",
                    )
                result = await client.download_media(msg, file=str(target_dir))
                if result:
                    file_size_bytes: Optional[int] = None
                    try:
                        file_size_bytes = Path(result).stat().st_size
                    except (OSError, TypeError, ValueError):
                        file_size_bytes = None
                    if (
                        file_size_bytes is not None
                        and total_downloaded_bytes + file_size_bytes > MAX_UPLOAD_BYTES
                    ):
                        skipped_total_limit += 1
                        try:
                            Path(result).unlink(missing_ok=True)
                        except OSError:
                            pass
                        if verbose_photo_logs:
                            current_mb = total_downloaded_bytes / (1024 * 1024)
                            next_mb = file_size_bytes / (1024 * 1024)
                            log(
                                "WARN",
                                "Пропускаю фото из Telegram по общему лимиту: "
                                f"message_id={msg.id} chat_id={chat_id} "
                                f"текущее={current_mb:.2f} MB "
                                f"+ фото={next_mb:.2f} MB > {max_mb:.2f} MB.",
                            )
                    else:
                        if file_size_bytes is not None:
                            total_downloaded_bytes += file_size_bytes
                        downloaded += 1
                        if verbose_photo_logs:
                            total_mb = total_downloaded_bytes / (1024 * 1024)
                            log(
                                "OK",
                                "Скачано фото "
                                f"{idx}/{len(queue)}: message_id={msg.id}. "
                                f"Суммарный размер: {total_mb:.2f} MB.",
                            )
                else:
                    failed_downloads += 1
                    if verbose_photo_logs:
                        log(
                            "WARN",
                            f"Не удалось скачать фото {idx}/{len(queue)}: "
                            f"message_id={msg.id}.",
                        )
                if not verbose_photo_logs:
                    progress.advance()
        if failed_downloads and not verbose_photo_logs:
            log("WARN", f"Не удалось скачать фото: {failed_downloads}/{len(queue)}.")
        if skipped_total_limit:
            total_mb = total_downloaded_bytes / (1024 * 1024)
            log(
                "INFO",
                "Пропущено по общему лимиту размера: "
                f"{skipped_total_limit}. "
                f"Итоговый размер товара: {total_mb:.2f} MB / {max_mb:.2f} MB.",
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


def _collect_nested_message_ids(value) -> list[int]:
    if value is None:
        return []
    if isinstance(value, dict):
        result: list[int] = []
        direct_id = _parse_int(value.get("message_id"))
        if direct_id is None:
            direct_id = _parse_int(value.get("id"))
        if direct_id is not None:
            result.append(direct_id)
        for key in (
            "message_ids",
            "photo_message_ids",
            "comment_messages",
            "comments",
            "comment_message_ids",
        ):
            nested = value.get(key)
            if nested is None:
                continue
            result.extend(_collect_nested_message_ids(nested))
        return result
    if isinstance(value, (list, tuple, set)):
        result: list[int] = []
        for item in value:
            result.extend(_collect_nested_message_ids(item))
        return result
    parsed = _parse_int(value)
    return [parsed] if parsed is not None else []


def get_product_photo_message_ids(product_data: Optional[dict]) -> list[int]:
    if not isinstance(product_data, dict):
        return []
    parsed_data = product_data.get("parsed_data")
    message_ids: list[int] = []
    for source in (
        product_data.get("message_id"),
        product_data.get("photo_message_ids"),
        product_data.get("message_ids"),
        product_data.get("comment_message_ids"),
        product_data.get("comment_messages"),
        product_data.get("comments"),
        parsed_data,
    ):
        message_ids.extend(_collect_nested_message_ids(source))
    deduped: list[int] = []
    seen_ids: set[int] = set()
    for message_id in message_ids:
        if message_id in seen_ids:
            continue
        deduped.append(message_id)
        seen_ids.add(message_id)
    return deduped


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


def _extract_numeric_sizes(value: object) -> list[float]:
    sizes: list[float] = []

    def add_size(numeric: Optional[float]) -> None:
        if numeric is None or not (15 <= numeric <= 60):
            return
        if numeric not in sizes:
            sizes.append(numeric)

    if value is None:
        return sizes
    if isinstance(value, (int, float)):
        add_size(float(value))
        return sizes

    text = str(value).strip()
    if not text:
        return sizes

    normalized = text.replace(",", ".")
    without_length = re.sub(
        r"\b\d{1,3}(?:\.\d+)?\s*(?:см|cm)\b",
        "",
        normalized,
        flags=re.IGNORECASE,
    )

    for match in re.finditer(r"\b(\d{2})\s*[-–]\s*(\d{2})\b", without_length):
        start = int(match.group(1))
        end = int(match.group(2))
        if not (15 <= start <= 60 and 15 <= end <= 60):
            continue
        if end < start or end - start > 20:
            continue
        for current in range(start, end + 1):
            add_size(float(current))

    for token in re.findall(r"(?<!\d)\d{2,3}(?:\.\d+)?(?!\d)", without_length):
        add_size(_to_number(token))

    return sizes


def _size_name_candidates(value: object) -> list[str]:
    text = str(value).strip()
    candidates: list[str] = []

    def add_candidate(candidate: str) -> None:
        item = candidate.strip()
        if item and item not in candidates:
            candidates.append(item)

    add_candidate(text)
    add_candidate(text.replace(",", "."))
    add_candidate(text.replace(".", ","))
    normalized_text = normalize_size_text(text)
    if normalized_text:
        add_candidate(normalized_text)

    for numeric in _extract_numeric_sizes(text):
        normalized = f"{numeric:g}"
        add_candidate(normalized)
        add_candidate(normalized.replace(".", ","))
        if numeric.is_integer():
            add_candidate(str(int(numeric)))

    return candidates


def _expand_size_values(value: object, even_range_step: bool = False) -> list[str]:
    if value is None:
        return []
    if isinstance(value, int):
        return [str(value)]
    if isinstance(value, float):
        normalized = f"{value:g}"
        return [normalized]

    text = str(value).strip()
    if not text:
        return []

    if even_range_step:
        normalized_text = text.replace(",", ".")
        without_length = re.sub(
            r"\b\d{1,3}(?:\.\d+)?\s*(?:см|cm)\b",
            "",
            normalized_text,
            flags=re.IGNORECASE,
        )
        range_match = re.fullmatch(r"\s*(\d{2})\s*[-–]\s*(\d{2})(?:\D.*)?\s*", without_length)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if (
                15 <= start <= 60
                and 15 <= end <= 60
                and end >= start
                and end - start <= 20
                and (end - start) >= 2
                and start % 2 == end % 2
            ):
                return [str(value) for value in range(start, end + 1, 2)]

    expanded: list[str] = []
    for token in _extract_size_tokens_from_line(text):
        normalized = _normalize_size_token(token)
        if normalized and normalized not in expanded:
            expanded.append(normalized)
    if expanded:
        return expanded
    return [text]


def _should_use_even_clothing_size_ranges(
    catalog_filter_slug: Optional[str],
) -> bool:
    return bool(catalog_filter_slug)

def _resolve_catalog_slug(size: object, additional_sizes: list[object], word_for_slack: str) -> str:

    values = [size, *additional_sizes]
    numeric_sizes = [
        numeric_size
        for value in values
        for numeric_size in _extract_numeric_sizes(value)
    ]

    slug = find_slug_by_word(word_for_slack)
    if slug:
        return slug
    if numeric_sizes and all(
        WOMEN_SNEAKERS_MIN_SIZE <= numeric_size <= WOMEN_SNEAKERS_MAX_SIZE
        for numeric_size in numeric_sizes
    ):
        return WOMEN_SNEAKERS_CATEGORY
    return DEFAULT_SHOES_CATEGORY


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

def _resolve_size_id_from_category_map(
    value: Optional[object],
    catalog_slug: Optional[str],
    preferred_system: Optional[str] = None,
) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    mapped_text = SIZE_NAME_MAPPING.get(text.upper(), text)
    reverse_sizes_dict = {}
    for key, values in sizes_dict.items():
        for v in values:
            reverse_sizes_dict[v] = key
    main_slug = reverse_sizes_dict.get(catalog_slug or "", catalog_slug)
    if not main_slug:
        return None
    size_id = _select_size_mapping_id(
        mapped_text,
        catalog_slug=main_slug,
        preferred_system=preferred_system,
    )
    if size_id is not None:
        return size_id
    return get_size_id_by_name(mapped_text, catalog_slug=main_slug)


def _size_mapping_debug_enabled() -> bool:
    return os.getenv("SHAFA_DEBUG_SIZE_MAPPING", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _preferred_match_priority(preferred_system: Optional[str]) -> dict[str, int]:
    if preferred_system == SIZE_SYSTEM_INTERNATIONAL:
        return {
            SIZE_SYSTEM_INTERNATIONAL: 0,
            SIZE_SYSTEM_UA: 1,
            SIZE_SYSTEM_EU: 2,
        }
    if preferred_system == SIZE_SYSTEM_UA:
        return {
            SIZE_SYSTEM_UA: 0,
            SIZE_SYSTEM_INTERNATIONAL: 1,
            SIZE_SYSTEM_EU: 2,
        }
    return {
        SIZE_SYSTEM_EU: 0,
        SIZE_SYSTEM_INTERNATIONAL: 1,
        SIZE_SYSTEM_UA: 2,
    }


def _default_target_size_system(
    normalized_value: Optional[str],
    candidates: list[dict],
) -> Optional[str]:
    if not normalized_value or not candidates:
        return None
    if re.search(r"[A-Z]", normalized_value) or normalized_value in {"ONE SIZE", "ІНШИЙ"}:
        return SIZE_SYSTEM_INTERNATIONAL
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized_value):
        if any(candidate["matched_system"] == SIZE_SYSTEM_EU for candidate in candidates):
            return SIZE_SYSTEM_EU
        if any(
            candidate["matched_system"] == SIZE_SYSTEM_INTERNATIONAL
            for candidate in candidates
        ):
            return SIZE_SYSTEM_INTERNATIONAL
        if any(candidate["matched_system"] == SIZE_SYSTEM_UA for candidate in candidates):
            return SIZE_SYSTEM_UA
    return candidates[0]["matched_system"]


def _select_size_mapping_id(
    value: object,
    catalog_slug: Optional[str],
    preferred_system: Optional[str] = None,
) -> Optional[int]:
    candidates = find_size_mapping_candidates(value, catalog_slug=catalog_slug)
    if not candidates:
        return None
    normalized_value = normalize_size_text(value)
    target_system = preferred_system or _default_target_size_system(
        normalized_value,
        candidates,
    )
    if target_system is None:
        return None
    priority = _preferred_match_priority(target_system)
    ranked = sorted(
        candidates,
        key=lambda item: (
            priority.get(item["matched_system"], 99),
            0 if item["row"].get(f"id_v5_{target_system}") is not None else 1,
            0 if item["row"].get("id_v3") is not None else 1,
            item["matched_id"],
        ),
    )
    row = ranked[0]["row"]
    resolved_id = row.get(f"id_v5_{target_system}") or ranked[0]["matched_id"]
    try:
        return int(resolved_id)
    except (TypeError, ValueError):
        return None


def _detect_preferred_size_system(
    value: Optional[object],
    catalog_slug: Optional[str],
) -> Optional[str]:
    normalized_value = normalize_size_text(value)
    if not normalized_value:
        return None
    candidates = find_size_mapping_candidates(normalized_value, catalog_slug=catalog_slug)
    if not candidates:
        return None
    if re.search(r"[A-Z]", normalized_value) or normalized_value in {"ONE SIZE", "ІНШИЙ"}:
        return SIZE_SYSTEM_INTERNATIONAL
    matched_systems = {candidate["matched_system"] for candidate in candidates}
    if len(matched_systems) == 1:
        return next(iter(matched_systems))
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized_value):
        return SIZE_SYSTEM_EU
    return None


def _resolve_size_id(
    value: Optional[object],
    catalog_slug: Optional[str] = None,
    preferred_system: Optional[str] = None,
) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value if size_id_exists(value, catalog_slug=catalog_slug) else None

    text = str(value).strip()
    for candidate in _size_name_candidates(text):
        mapped_size_id = _select_size_mapping_id(
            candidate,
            catalog_slug=catalog_slug,
            preferred_system=preferred_system,
        )
        if mapped_size_id is not None:
            return mapped_size_id
        size_id = get_size_id_by_name(candidate, catalog_slug=catalog_slug)
        if size_id is not None:
            return size_id

    mapped_size_id = _resolve_size_id_from_category_map(
        text,
        catalog_slug,
        preferred_system=preferred_system,
    )
    if mapped_size_id is not None:
        return mapped_size_id

    parsed = _parse_int(text)
    if parsed is None:
        return None
    return parsed if size_id_exists(parsed, catalog_slug=catalog_slug) else None


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


def _parse_additional_sizes(
    values: list[str],
    catalog_slug: Optional[str] = None,
    preferred_system: Optional[str] = None,
) -> list[int]:
    sizes: list[int] = []
    for value in values:
        if preferred_system is None:
            size = _resolve_size_id(
                value,
                catalog_slug=catalog_slug,
            )
        else:
            size = _resolve_size_id(
                value,
                catalog_slug=catalog_slug,
                preferred_system=preferred_system,
            )
        if size is not None and size not in sizes:
            sizes.append(size)
    return sizes


def _preview_list(values: list[str], limit: int = 5) -> str:
    normalized = [str(value).strip() for value in values if str(value).strip()]
    if not normalized:
        return ""

    preview = ", ".join(normalized[:limit])
    if len(normalized) > limit:
        return f"{preview}…"
    return preview


def _format_size_resolution_summary(
    *,
    catalog_slug: str,
    raw_size: str | None,
    raw_additional_sizes: list[str],
    preferred_size_system: str | None,
    resolved_size: int | None,
    resolved_additional_sizes: list[int],
) -> str:
    parts: list[str] = []
    normalized_raw_size = str(raw_size or "").strip()
    additional_sizes_preview = _preview_list(raw_additional_sizes)

    if normalized_raw_size:
        parts.append(f"Размер: {normalized_raw_size}.")
    if additional_sizes_preview:
        parts.append(f"Доп. размеры: {additional_sizes_preview}.")
    if catalog_slug:
        parts.append(f"Каталог: {catalog_slug}.")
    if preferred_size_system:
        parts.append(f"Система: {preferred_size_system.upper()}.")
    if resolved_size is not None:
        if resolved_additional_sizes:
            parts.append(
                f"Размер сопоставлен, доп. размеров: {len(resolved_additional_sizes)}."
            )
        else:
            parts.append("Размер сопоставлен.")
    else:
        parts.append("Размер не сопоставлен автоматически.")

    return " ".join(parts)


def _build_product_raw_data(parsed: dict, slug: str | None = None) -> dict:
    additional_size_values = parsed.get("additional_sizes", [])
    if not isinstance(additional_size_values, list):
        additional_size_values = []
    word_for_slack = parsed.get("word_for_slack", "")
    size_value = parsed.get("size")
    catalog_slug = _resolve_catalog_slug(
        size_value,
        additional_size_values,
        word_for_slack=word_for_slack,
    )
    slug = find_slug_by_word(word_for_slack)
    use_even_clothing_size_ranges = _should_use_even_clothing_size_ranges(slug)

    description = DEFAULT_DESCRIPTION
    if slug:
        description = parsed.get("description") or DEFAULT_DESCRIPTION

    expanded_size_values: list[str] = []
    for raw_value in [size_value, *additional_size_values]:
        for expanded in _expand_size_values(
            raw_value,
            even_range_step=use_even_clothing_size_ranges,
        ):
            if expanded not in expanded_size_values:
                expanded_size_values.append(expanded)

    resolved_size = None
    resolved_additional_sizes: list[int] = []
    preferred_size_system = None
    if expanded_size_values:
        preferred_size_system = _detect_preferred_size_system(
            expanded_size_values[0],
            catalog_slug,
        )
        if preferred_size_system is None:
            resolved_size = _resolve_size_id(
                expanded_size_values[0],
                catalog_slug=catalog_slug,
            )
        else:
            resolved_size = _resolve_size_id(
                expanded_size_values[0],
                catalog_slug=catalog_slug,
                preferred_system=preferred_size_system,
            )
        if resolved_size is not None:
            if preferred_size_system is None:
                resolved_additional_sizes = _parse_additional_sizes(
                    expanded_size_values[1:],
                    catalog_slug=catalog_slug,
                )
            else:
                resolved_additional_sizes = _parse_additional_sizes(
                    expanded_size_values[1:],
                    catalog_slug=catalog_slug,
                    preferred_system=preferred_size_system,
                )
            resolved_additional_sizes = [
                size_id
                for size_id in resolved_additional_sizes
                if size_id != resolved_size
            ]

    normalized_name = _canonicalize_name_brand(
        parsed.get("name", ""),
        parsed.get("brand"),
    )

    product_raw_data: dict = {
        "word_for_slack": parsed.get("word_for_slack", ""),
        "name": normalized_name,
        "description": description,
        "category": catalog_slug,
        "brand": (
            _resolve_brand_id(parsed.get("brand"))
            if catalog_supports_brand(catalog_slug)
            else None
        ),
        "size": resolved_size
        if resolved_size is not None
        else (
            _resolve_size_id(parsed.get("size"), catalog_slug=catalog_slug)
            if preferred_size_system is None
            else _resolve_size_id(
                parsed.get("size"),
                catalog_slug=catalog_slug,
                preferred_system=preferred_size_system,
            )
        ),
        "price": _parse_price(parsed.get("price")),
        "slug": slug,
    }
    product_raw_data["colors"] = _normalize_colors(parsed.get("color"))
    additional_sizes = (
        resolved_additional_sizes
        if resolved_size is not None
        else (
            _parse_additional_sizes(
                additional_size_values,
                catalog_slug=catalog_slug,
            )
            if preferred_size_system is None
            else _parse_additional_sizes(
                additional_size_values,
                catalog_slug=catalog_slug,
                preferred_system=preferred_size_system,
            )
        )
    )
    if additional_sizes:
        product_raw_data["additional_sizes"] = additional_sizes
    if size_value or additional_size_values:
        log(
            "INFO",
            _format_size_resolution_summary(
                catalog_slug=catalog_slug,
                raw_size=size_value,
                raw_additional_sizes=additional_size_values,
                preferred_size_system=preferred_size_system,
                resolved_size=product_raw_data.get("size"),
                resolved_additional_sizes=additional_sizes,
            ),
        )
    if _size_mapping_debug_enabled():
        log(
            "INFO",
            "Разрешение размеров: "
            + json.dumps(
                {
                    "catalog": catalog_slug,
                    "raw_size": size_value,
                    "raw_additional_sizes": additional_size_values,
                    "expanded_sizes": expanded_size_values,
                    "preferred_size_system": preferred_size_system,
                    "resolved_size": product_raw_data.get("size"),
                    "resolved_additional_sizes": additional_sizes,
                    "size_api_version": "v3_create_with_v5_size_ids",
                },
                ensure_ascii=False,
            ),
        )
    return product_raw_data


def build_product_raw_data(parsed: dict) -> dict:
    return _build_product_raw_data(parsed)


def rebuild_product_data_from_source(product_data: dict) -> tuple[dict, dict]:
    parsed_data = product_data.get("parsed_data")
    if not isinstance(parsed_data, dict):
        parsed_data = {}
    raw_message = str(product_data.get("raw_message") or "").strip()
    if raw_message:
        parsed_data = parse_message(raw_message)
    return parsed_data, _build_product_raw_data(parsed_data)


def _pick_next_product_for_upload() -> Optional[dict]:
    while True:
        rows = [
            row
            for channel_id in _get_channel_ids()
            for row in [get_next_uncreated_telegram_product(channel_id)]
            if row
        ]
        if not rows:
            return None
        row = max(rows, key=lambda item: item["created_at"])
        parsed_from_db = json.loads(row["parsed_data"]) if row["parsed_data"] else {}
        raw_message = row["raw_message"] or ""

        parsed = parse_message(raw_message) if raw_message else parsed_from_db
        if not is_mode_allowed_parsed(parsed):
            log(
                "INFO",
                f"Пропускаю сообщение channel_id={row['channel_id']} "
                + f"message_id={row['message_id']}: не подходит для режима {get_runtime_mode()}.",
            )
            mark_telegram_product_created(
                row["channel_id"],
                row["message_id"],
                created_product_id="SKIPPED_BY_MODE",
            )
            continue
        if not parsed.get("name") or not parsed.get("price") or not parsed.get("size"):
            log(
                "WARN",
                f"Пропускаю сообщение channel_id={row['channel_id']} "
                + f"message_id={row['message_id']}: нет названия/цены/размера.",
            )
            mark_telegram_product_created(
                row["channel_id"],
                row["message_id"],
                created_product_id="SKIPPED_MISSING_DATA",
            )
            continue
        return {
            "channel_id": row["channel_id"],
            "message_id": row["message_id"],
            "raw_message": raw_message,
            "parsed_data": parsed,
            "product_raw_data": _build_product_raw_data(parsed),
        }


async def get_next_product_for_upload_async(
    message_amount: int = 200,
    first_fetch_check: bool | None = None,
    scan_before_pick: bool = True,
) -> Optional[dict]:
    product = _pick_next_product_for_upload()
    if product is not None or not scan_before_pick:
        return product

    fetch_status, lease_token = _claim_shared_telegram_fetch()
    if fetch_status == "acquired":
        fetch_completed = False
        try:
            if first_fetch_check:
                log("INFO", "Запускаю первичную загрузку товаров из Telegram...")
                inserted = await first_fetch()
                log("INFO", f"Первичная загрузка Telegram завершена. Новых товаров: {inserted}.")
            else:
                log("INFO", f"Проверяю новые сообщения в Telegram (limit={message_amount})...")
                inserted = await _fetch_messages(message_amount=message_amount)
                log("INFO", f"Проверка Telegram завершена. Новых товаров: {inserted}.")
            fetch_completed = True
        finally:
            _finish_shared_telegram_fetch(lease_token, success=fetch_completed)
    product = _pick_next_product_for_upload()
    if product is not None or fetch_status != "in_progress":
        return product
    wait_seconds = _telegram_fetch_wait_seconds()
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    return _pick_next_product_for_upload()


def get_next_product_for_upload(
    message_amount: int = 200,
    first_fetch_check: bool | None = None,
    scan_before_pick: bool = True,
) -> Optional[dict]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            get_next_product_for_upload_async(
                message_amount=message_amount,
                first_fetch_check=first_fetch_check,
                scan_before_pick=scan_before_pick,
            )
        )
    raise RuntimeError(
        "get_next_product_for_upload cannot be called when an event loop is running. "
        "Use get_next_product_for_upload_async."
    )


async def download_product_photos_async(
    message_id: int,
    target_dir: Path,
    channel_id: Optional[int] = None,
    max_photos: int = MAX_DOWNLOAD_PHOTOS,
    message_ids: Optional[list[int]] = None,
) -> int:
    resolved_channel_id = (
        channel_id if channel_id is not None else _get_channel_ids()[0]
    )
    return await _download_message_photos(
        resolved_channel_id,
        message_id,
        target_dir,
        max_photos,
        message_ids=message_ids,
    )


def download_product_photos(
    message_id: int,
    target_dir: Path,
    channel_id: Optional[int] = None,
    max_photos: int = MAX_DOWNLOAD_PHOTOS,
    message_ids: Optional[list[int]] = None,
) -> int:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            download_product_photos_async(
                message_id,
                target_dir,
                channel_id=channel_id,
                max_photos=max_photos,
                message_ids=message_ids,
            )
        )
    raise RuntimeError(
        "download_product_photos cannot be called when an event loop is running. "
        "Use download_product_photos_async."
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


def register_product_failure(
    message_id: int,
    failure_reason: str,
    channel_id: Optional[int] = None,
) -> tuple[int, bool]:
    resolved_channel_id = (
        channel_id if channel_id is not None else _get_channel_ids()[0]
    )
    attempts = increment_telegram_product_attempt(
        resolved_channel_id,
        message_id,
        failure_reason=failure_reason,
    )
    if attempts >= MAX_PRODUCT_CREATE_ATTEMPTS:
        mark_telegram_product_created(
            resolved_channel_id,
            message_id,
            created_product_id=SKIPPED_CREATE_RETRY_LIMIT,
        )
        return attempts, True
    return attempts, False


async def backfill_created_product_message_dates_async(
    *,
    limit: int = 100,
    account_id: Optional[str] = None,
    telegram_client_cls: Any | None = None,
) -> dict[str, object]:
    normalized_limit = max(int(limit), 1)
    updated_from_db = backfill_telegram_product_message_dates_from_existing_db(
        limit=normalized_limit,
        account_id=account_id,
    )
    remaining = list_created_telegram_products_missing_date(
        limit=normalized_limit,
        account_id=account_id,
    )
    result: dict[str, object] = {
        "limit": normalized_limit,
        "updated_from_db": updated_from_db,
        "updated_from_telegram": 0,
        "remaining": len(remaining),
        "failed": 0,
    }
    if not remaining:
        return result

    api_id_value, api_hash_value = _require_telegram_credentials()
    client_factory = telegram_client_cls or TelegramClient
    updated_from_telegram = 0
    failed = 0

    async with create_telegram_client(
        TELEGRAM_SESSION_PATH,
        api_id_value,
        api_hash_value,
        save_entities=False,
        telegram_client_cls=client_factory,
        account_id=account_id or _current_account_id(),
    ) as client:
        grouped_by_channel: dict[int, list[dict[str, object]]] = {}
        for item in remaining:
            grouped_by_channel.setdefault(int(item["channel_id"]), []).append(item)

        for channel_id, candidates in grouped_by_channel.items():
            try:
                channel_peer = await _resolve_channel_peer(client, channel_id)
                fetched_messages = await client.get_messages(
                    channel_peer,
                    ids=[int(item["message_id"]) for item in candidates],
                )
            except Exception as exc:
                failed += len(candidates)
                log(
                    "WARN",
                    "Не удалось добрать даты созданных товаров из Telegram. "
                    f"channel_id={channel_id}. error={exc}",
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
            for candidate in candidates:
                message_id = int(candidate["message_id"])
                message = messages_by_id.get(message_id)
                message_date = _message_datetime_utc(message) if message is not None else None
                if message_date is None:
                    failed += 1
                    continue
                if set_telegram_product_message_date(
                    channel_id,
                    message_id,
                    message_date,
                    account_id=str(candidate["account_id"]),
                ):
                    updated_from_telegram += 1

    result["updated_from_telegram"] = updated_from_telegram
    result["failed"] = failed
    result["remaining"] = len(
        list_created_telegram_products_missing_date(
            limit=normalized_limit,
            account_id=account_id,
        )
    )
    return result


def backfill_created_product_message_dates(
    *,
    limit: int = 100,
    account_id: Optional[str] = None,
    telegram_client_cls: Any | None = None,
) -> dict[str, object]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            backfill_created_product_message_dates_async(
                limit=limit,
                account_id=account_id,
                telegram_client_cls=telegram_client_cls,
            )
        )
    raise RuntimeError(
        "backfill_created_product_message_dates cannot be called when an event loop is running. "
        "Use backfill_created_product_message_dates_async."
    )


def plan_shared_old_product_deactivation(
    *,
    older_than_days: Optional[int] = None,
    limit: int = 100,
    account_id: Optional[str] = None,
    dry_run: Optional[bool] = None,
) -> dict[str, int]:
    age_days = max(
        DEFAULT_TELEGRAM_PRODUCT_MAX_AGE_DAYS
        if older_than_days is None
        else int(older_than_days),
        DEFAULT_TELEGRAM_PRODUCT_MAX_AGE_DAYS,
    )
    resolved_account_id = str(account_id or _current_account_id()).strip() or "default"
    effective_dry_run = _shared_deactivation_dry_run() if dry_run is None else dry_run
    try:
        backfill_created_product_message_dates(
            limit=max(int(limit), 1),
            account_id=account_id,
        )
    except Exception as exc:
        _safe_old_product_log(
            "WARN",
            "shared deactivation planner could not backfill Telegram dates "
            f"account_id={resolved_account_id}. error={exc}.",
        )
    reconcile_result = reconcile_shared_telegram_products(account_id=account_id)
    result = plan_shared_deactivation_tasks(
        older_than_days=age_days,
        limit=limit,
        account_id=account_id,
        dry_run=effective_dry_run,
    )
    _safe_old_product_log(
        "INFO",
        "shared deactivation planner finished "
        f"account_id={resolved_account_id}. dry_run={effective_dry_run}. "
        f"reconciled_products={reconcile_result.get('products')}. "
        f"reconciled_memberships={reconcile_result.get('memberships')}. "
        f"checked={result.get('checked')}. old={result.get('old')}. "
        f"fresh={result.get('fresh')}. date_missing={result.get('date_missing')}. "
        f"tasks={result.get('tasks')}. account_tasks={result.get('account_tasks')}.",
    )
    return result


def process_shared_deactivation_queue_once(
    *,
    account_id: Optional[str] = None,
    dry_run: Optional[bool] = None,
    deactivate_product_func=None,
    sleep_func=time.sleep,
) -> dict[str, object]:
    resolved_account_id = str(account_id or _current_account_id()).strip() or "default"
    effective_dry_run = _shared_deactivation_dry_run() if dry_run is None else dry_run
    result: dict[str, object] = {
        "account_id": resolved_account_id,
        "claimed": 0,
        "deactivated": 0,
        "failed": 0,
        "skipped": 0,
        "not_found": 0,
        "dry_run": effective_dry_run,
        "slept_seconds": 0.0,
    }
    if effective_dry_run:
        _safe_old_product_log(
            "INFO",
            "shared deactivation worker dry run; not claiming tasks "
            f"account_id={resolved_account_id}.",
        )
        return result

    claimed = claim_shared_deactivation_task_for_account(
        account_id=resolved_account_id,
        lease_seconds=DEFAULT_SHARED_DEACTIVATION_LEASE_SECONDS,
    )
    if claimed is None:
        return result

    result["claimed"] = 1
    token = str(claimed.get("processing_token") or "")
    token_prefix = token[:8]
    task_id = str(claimed["task_id"])
    product_key = str(claimed["telegram_product_key"])
    shafa_product_id = str(claimed["shafa_product_id"])
    deactivator = deactivate_product_func or _deactivate_product_backend_not_configured
    _safe_old_product_log(
        "INFO",
        "shared deactivation task claimed "
        f"account_id={resolved_account_id}. task_id={task_id}. "
        f"telegram_product_key={product_key}. "
        f"telegram_message_date={claimed.get('telegram_message_date')}. "
        f"shafa_product_id={shafa_product_id}. status=processing. "
        f"processing_token_prefix={token_prefix}.",
    )
    try:
        deactivator(shafa_product_id)
    except Exception as exc:
        if _is_shafa_product_not_found_error(exc):
            result["not_found"] = 1
            complete_not_found = skip_shared_deactivation_task_not_found_for_account(
                task_id=task_id,
                account_id=resolved_account_id,
                processing_token=token,
            )
            _safe_old_product_log(
                "WARN",
                "shared deactivation product not found treated as done "
                f"account_id={resolved_account_id}. task_id={task_id}. "
                f"telegram_product_key={product_key}. shafa_product_id={shafa_product_id}. "
                "action=product_not_found_treated_as_done. "
                "status=skipped_not_found. "
                f"db_updated={complete_not_found}. "
                f"processing_token_prefix={token_prefix}.",
            )
            result["deactivated"] = 0
            result["skipped"] = 1 if complete_not_found else 0
            result["failed"] = 0 if complete_not_found else 1
            if not complete_not_found:
                fail_shared_deactivation_task_for_account(
                    task_id=task_id,
                    account_id=resolved_account_id,
                    processing_token=token,
                    error_message=str(exc),
                    retry_delay_seconds=DEFAULT_SHARED_DEACTIVATION_RETRY_DELAY_SECONDS,
                )
            else:
                try:
                    mark_uploaded_product_inactive(
                        shafa_product_id,
                        status_title="Не знайдено",
                    )
                except Exception as mark_exc:
                    _safe_old_product_log(
                        "WARN",
                        "shared deactivation could not mark missing uploaded product inactive "
                        f"account_id={resolved_account_id}. task_id={task_id}. "
                        f"shafa_product_id={shafa_product_id}. error={mark_exc}.",
                    )
            return _sleep_after_shared_deactivation_attempt(
                result=result,
                account_id=resolved_account_id,
                sleep_func=sleep_func,
            )
        result["failed"] = 1
        fail_shared_deactivation_task_for_account(
            task_id=task_id,
            account_id=resolved_account_id,
            processing_token=token,
            error_message=str(exc),
            retry_delay_seconds=DEFAULT_SHARED_DEACTIVATION_RETRY_DELAY_SECONDS,
        )
        _safe_old_product_log(
            "ERROR",
            "shared deactivation task failed "
            f"account_id={resolved_account_id}. task_id={task_id}. "
            f"telegram_product_key={product_key}. shafa_product_id={shafa_product_id}. "
            f"status=failed. last_error={exc}. "
            f"processing_token_prefix={token_prefix}.",
        )
    else:
        result["deactivated"] = 1
        complete_shared_deactivation_task_for_account(
            task_id=task_id,
            account_id=resolved_account_id,
            processing_token=token,
        )
        try:
            mark_uploaded_product_inactive(shafa_product_id, status_title="Деактивовано")
        except Exception as exc:
            _safe_old_product_log(
                "WARN",
                "shared deactivation could not mark uploaded product inactive "
                f"account_id={resolved_account_id}. task_id={task_id}. "
                f"shafa_product_id={shafa_product_id}. error={exc}.",
            )
        _safe_old_product_log(
            "OK",
            "shared deactivation task completed "
            f"account_id={resolved_account_id}. task_id={task_id}. "
            f"telegram_product_key={product_key}. shafa_product_id={shafa_product_id}. "
            f"status=completed. processing_token_prefix={token_prefix}.",
        )

    return _sleep_after_shared_deactivation_attempt(
        result=result,
        account_id=resolved_account_id,
        sleep_func=sleep_func,
    )


def _sleep_after_shared_deactivation_attempt(
    *,
    result: dict[str, object],
    account_id: str,
    sleep_func=time.sleep,
) -> dict[str, object]:
    min_cooldown, max_cooldown = _shared_deactivation_cooldown_range_seconds()
    cooldown = (
        min_cooldown
        if min_cooldown == max_cooldown
        else random.uniform(min_cooldown, max_cooldown)
    )
    result["slept_seconds"] = round(cooldown, 3)
    if cooldown > 0:
        _safe_old_product_log(
            "INFO",
            "shared deactivation worker cooldown "
            f"account_id={account_id}. cooldown_seconds={round(cooldown, 3)}.",
        )
        sleep_func(cooldown)
    return result


def _deactivate_old_telegram_products_impl(
    *,
    older_than_days: Optional[int] = None,
    limit: Optional[int] = None,
    sleep_seconds: Optional[float] = None,
    dry_run: bool = False,
    account_id: Optional[str] = None,
    deactivate_product_func=None,
) -> dict[str, object]:
    started_at = time.perf_counter()
    age_days = (
        _telegram_product_max_age_days()
        if older_than_days is None
        else max(int(older_than_days), 1)
    )
    if limit is None:
        batch_limit: Optional[int] = _old_product_deactivate_batch_size()
    else:
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError):
            parsed_limit = _old_product_deactivate_batch_size()
        batch_limit = None if parsed_limit <= 0 else max(parsed_limit, 1)
    deactivate_only = _env_flag_enabled("SHAFA_DEACTIVATE_ONLY")
    if deactivate_only:
        batch_limit = 1
    delay_seconds = (
        _old_product_deactivate_sleep_seconds()
        if sleep_seconds is None
        else min(max(float(sleep_seconds), 0.0), 60.0)
    )
    resolved_account_id = str(account_id or _current_account_id()).strip() or "default"
    account_label = _old_product_cleanup_account_label(resolved_account_id)
    result: dict[str, object] = {
        "older_than_days": age_days,
        "limit": "all" if batch_limit is None else batch_limit,
        "dry_run": dry_run,
        "sleep_seconds": delay_seconds,
        "checked": 0,
        "found": 0,
        "active": 0,
        "skipped": 0,
        "not_found": 0,
        "deactivated": 0,
        "failed": 0,
        "candidates": [],
        "execution_time_seconds": 0.0,
    }

    def _finish_result() -> dict[str, object]:
        result["execution_time_seconds"] = round(time.perf_counter() - started_at, 3)
        _safe_old_product_log(
            "INFO",
            "cleanup cycle end "
            f"account={account_label}. account_id={resolved_account_id}. "
            f"total_checked_products={result['checked']}. "
            f"total_deactivated_products={result['deactivated']}. "
            f"execution_time={result['execution_time_seconds']}s.",
        )
        return result

    _safe_old_product_log(
        "INFO",
        "cleanup cycle start "
        f"account={account_label}. account_id={resolved_account_id}. "
        f"threshold_days={age_days}. limit={result['limit']}. dry_run={dry_run}.",
    )
    _safe_old_product_log(
        "INFO",
        "cleanup runtime context "
        f"account={account_label}. account_id={resolved_account_id}. "
        f"env_account_id={os.getenv('SHAFA_ACCOUNT_ID', '')}. "
        f"db_path={os.getenv('SHAFA_DB_PATH', str(Path(DB_PATH)))}. "
        f"telegram_db_path={os.getenv('SHAFA_SHARED_TELEGRAM_DB_PATH', str(Path(TELEGRAM_PRODUCTS_DB_PATH)))}. "
        f"deactivate_only={deactivate_only}.",
    )
    env_account_id = str(os.getenv("SHAFA_ACCOUNT_ID") or "").strip()
    if env_account_id and env_account_id != resolved_account_id:
        _safe_old_product_log(
            "WARN",
            "cleanup account context mismatch "
            f"resolved_account_id={resolved_account_id}. "
            f"env_account_id={env_account_id}. "
            "Using explicit resolved_account_id for shared Telegram queries.",
        )
    sql_snapshot_items = _log_old_product_sql_snapshot(
        account_id=resolved_account_id,
        threshold_days=age_days,
        preview_limit=1 if deactivate_only else 10,
    )
    if deactivate_only:
        log(
            "INFO",
            "Режим только деактивации: пропускаю Telegram backfill дат, "
            "использую даты из локальной базы.",
        )
    else:
        try:
            backfill_limit_base = (
                _old_product_deactivate_batch_size()
                if batch_limit is None
                else max(int(batch_limit), 1)
            )
            backfill_created_product_message_dates(
                limit=backfill_limit_base * 5,
                account_id=account_id,
            )
            queued_count = enqueue_expired_telegram_products_for_deactivation(
                older_than_days=age_days,
                limit=backfill_limit_base * 5,
                account_id=account_id,
            )
            if queued_count:
                _safe_old_product_log(
                    "INFO",
                    "Поставлены в очередь деактивации старые Telegram-товары. "
                    f"account={account_label}. account_id={resolved_account_id}. "
                    f"queued={queued_count}.",
                )
        except Exception as exc:
            _safe_old_product_log(
                "WARN",
                "Не удалось обновить даты созданных товаров перед деактивацией. "
                f"account={account_label}. account_id={resolved_account_id}. error={exc}",
            )

    if deactivate_only:
        uploaded_products = []
        telegram_products = []
        deactivation_queue_products = []
    else:
        try:
            uploaded_products = list_uploaded_products_for_age_check()
            telegram_products = list_created_telegram_products_for_age_check(
                account_id=account_id
            )
            queue_limit = (
                max(len(telegram_products), _old_product_deactivate_batch_size(), 1)
                if batch_limit is None
                else max(int(batch_limit), 1)
            )
            deactivation_queue_products = list_telegram_product_deactivation_queue(
                account_id=account_id,
                limit=queue_limit,
            )
            _safe_old_product_log(
                "INFO",
                "Деактивация: загружены источники кандидатов. "
                f"account={account_label}. account_id={resolved_account_id}. "
                f"uploaded_products={len(uploaded_products)}. "
                f"telegram_products={len(telegram_products)}. "
                f"deactivation_queue={len(deactivation_queue_products)}.",
            )
        except Exception as exc:
            result["failed"] = 1
            _safe_old_product_log(
                "ERROR",
                f'{account_label} Product="unknown" message_id=unknown '
                'telegram_found=false telegram_channel="unknown" '
                "message_date=unknown age=unknown operation=deactivate action=ERROR "
                f'reason="database unavailable: {_log_value(exc)}"',
            )
            return _finish_result()

    telegram_by_product_id = {
        str(item["created_product_id"]): item for item in telegram_products
    }
    telegram_by_message_id: dict[int, list[dict]] = {}
    for item in telegram_products:
        telegram_by_message_id.setdefault(int(item["message_id"]), []).append(item)
    uploaded_by_product_id = {
        str(item["product_id"]): item for item in uploaded_products
    }
    uploaded_by_message_id: dict[int, dict] = {}
    for item in uploaded_products:
        uploaded_message_id = _old_product_int(item.get("message_id"))
        if uploaded_message_id is not None:
            uploaded_by_message_id[uploaded_message_id] = item
    cutoff_utc = datetime.now(timezone.utc) - timedelta(days=age_days)
    if deactivate_only:
        source_products = []
        for item in sql_snapshot_items:
            if float(item.get("age_days") or 0.0) < float(age_days):
                continue
            source_products.append(
                {
                    "product_id": item["product_id"],
                    "name": item["name"],
                    "message_id": item["message_id"],
                    "_deactivate_linked_telegram_product": {
                        "account_id": resolved_account_id,
                        "channel_id": item["channel_id"],
                        "message_id": item["message_id"],
                        "created_product_id": item["product_id"],
                        "product_name": item["name"],
                        "telegram_message_date": item["telegram_date"],
                    },
                    "_deactivate_telegram_message_date": item["telegram_date"],
                }
            )
        source_label = "uploaded_products(sql_preview_expired_by_telegram_message_date)"
    else:
        if deactivation_queue_products:
            source_products = deactivation_queue_products
            source_label = "telegram_products(deactivation_queue)"
        else:
            source_products = uploaded_products if uploaded_products else telegram_products
            source_label = (
                "uploaded_products(account_db)"
                if uploaded_products
                else "telegram_products(account_db_fallback)"
            )
    checked_products = (
        list(source_products)
        if batch_limit is None
        else _next_old_product_age_check_batch(
            source_products,
            limit=batch_limit,
            account_id=resolved_account_id,
            source_label=source_label,
        )
    )
    result["checked"] = len(checked_products)
    candidates: list[dict[str, object]] = []
    _safe_old_product_log(
        "INFO",
        "Проверяю созданные товары из базы аккаунта на срок деактивации. "
        f"account_id={resolved_account_id}. source={source_label}. "
        f"threshold_days={age_days}. checked_products={len(checked_products)}. "
        f"total_products={len(source_products)}. "
        f"dry_run={dry_run}.",
    )
    log(
        "INFO",
        "Деактивация: выбраны товары для проверки. "
        f"source={source_label}. всего_товаров={len(source_products)}. "
        f"будет_проверено={len(checked_products)}. threshold_days={age_days}.",
    )
    if not checked_products:
        log(
            "INFO",
            "Деактивация: нет товаров для проверки. "
            f"uploaded_products={len(uploaded_products)}. "
            f"telegram_products={len(telegram_products)}. "
            f"deactivation_queue={len(deactivation_queue_products)}.",
        )
    for checked_product in checked_products:
        tracking_allowed = True
        lookup_method = "telegram_product"
        lookup_reason: Optional[str] = None
        if source_label.startswith("uploaded_products"):
            product_id = str(checked_product["product_id"])
            candidate_name = (
                str(checked_product.get("name") or "").strip() or "нет названия"
            )
            explicit_message_id = _old_product_int(checked_product.get("message_id"))
            linked_product = checked_product.get("_deactivate_linked_telegram_product")
            if linked_product is not None:
                lookup_method = "prelinked_telegram_age"
            if linked_product is None:
                linked_product = _select_telegram_product_by_message_id(
                    explicit_message_id,
                    candidate_name,
                    telegram_by_message_id,
                )
                if linked_product is not None:
                    lookup_method = "message_id"
            if linked_product is None:
                linked_product = telegram_by_product_id.get(product_id)
                if linked_product is not None:
                    lookup_method = "created_product_id"
            if linked_product is None:
                linked_product, ambiguous_title = _select_telegram_product_by_title(
                    candidate_name,
                    telegram_products,
                )
                if linked_product is not None:
                    lookup_method = "title"
                    tracking_allowed = (
                        str(linked_product.get("created_product_id") or "").strip()
                        == product_id
                    )
                elif ambiguous_title:
                    lookup_reason = "ambiguous_title_match"
            candidate_account_id = resolved_account_id
            channel_id = (
                int(linked_product["channel_id"]) if linked_product is not None else None
            )
            message_id = (
                int(linked_product["message_id"]) if linked_product is not None else None
            )
            if message_id is None:
                message_id = explicit_message_id
            telegram_message_date = (
                str(linked_product.get("telegram_message_date") or "").strip() or "-"
                if linked_product is not None
                else "-"
            )
            telegram_message_dt = (
                _parse_datetime_text_utc(linked_product.get("telegram_message_date"))
                if linked_product is not None
                else None
            )
        else:
            candidate_name = (
                str(checked_product.get("product_name") or "").strip() or "нет названия"
            )
            product_id = str(checked_product["created_product_id"])
            channel_id = int(checked_product["channel_id"])
            message_id = int(checked_product["message_id"])
            candidate_account_id = str(checked_product["account_id"])
            uploaded_link = uploaded_by_message_id.get(message_id)
            if uploaded_link is None:
                uploaded_link = uploaded_by_product_id.get(product_id)
            if uploaded_link is not None:
                product_id = str(uploaded_link["product_id"])
                candidate_name = (
                    str(uploaded_link.get("name") or "").strip() or candidate_name
                )
                lookup_method = "uploaded_product_link"
            telegram_message_date = (
                str(checked_product.get("telegram_message_date") or "").strip() or "-"
            )
            telegram_message_dt = _parse_datetime_text_utc(
                checked_product.get("telegram_message_date")
            )
        now_utc = datetime.now(timezone.utc)
        product_age = (
            _format_age_duration(now_utc - telegram_message_dt)
            if telegram_message_dt is not None
            else "unknown"
        )
        telegram_age_days = (
            round(
                (now_utc - telegram_message_dt).total_seconds() / 86400.0,
                1,
            )
            if telegram_message_dt is not None
            else None
        )
        telegram_age_days_int = (
            int((now_utc - telegram_message_dt).total_seconds() // 86400)
            if telegram_message_dt is not None
            else None
        )
        if source_label.startswith("uploaded_products") and channel_id is None:
            decision = "missing_telegram_product_link"
            action = "NOT_FOUND"
            result["not_found"] = int(result["not_found"]) + 1
            log_level = "WARN"
            lookup_reason = lookup_reason or "not_found_in_telegram_products"
        elif telegram_message_dt is None:
            decision = "missing_message_date"
            action = "SKIPPED"
            result["skipped"] = int(result["skipped"]) + 1
            log_level = "WARN"
            lookup_reason = lookup_reason or "missing_message_date"
        else:
            decision = (
                "eligible_for_deactivation"
                if telegram_message_dt <= cutoff_utc
                else "not_old_enough"
            )
            action = (
                "DELETE_REQUIRED"
                if decision == "eligible_for_deactivation"
                else "ACTIVE"
            )
            if action == "ACTIVE":
                result["active"] = int(result["active"]) + 1
            log_level = "INFO"
            lookup_reason = lookup_reason or lookup_method
        _safe_old_product_log(
            "INFO",
            "Проверяю созданный товар из базы аккаунта. "
            f"account_id={candidate_account_id}. "
            f"source={source_label}. "
            "telegram_source=telegram_products(shared_account_db). "
            f"name={candidate_name}. product_id={product_id}. "
            f"channel_id={channel_id if channel_id is not None else 'unknown'}. "
            f"message_id={message_id if message_id is not None else 'unknown'}. "
            f"telegram_found={str(channel_id is not None).lower()}. "
            f"checked_at_utc={now_utc.isoformat()}. "
            f"telegram_message_date={telegram_message_date}. "
            f"product_age={product_age}. "
            f"telegram_age_days={telegram_age_days if telegram_age_days is not None else 'unknown'}. "
            f"threshold_days={age_days}. decision={decision}. "
            f"action={action}. lookup={lookup_reason}.",
        )
        log(
            "INFO",
            "Проверен товар для деактивации: "
            f"id_товара={product_id}. "
            f"name=\"{_log_value(candidate_name)}\". "
            f"дней={telegram_age_days if telegram_age_days is not None else 'unknown'}. "
            f"threshold_days={age_days}. action={action}. reason={lookup_reason}.",
        )
        _log_old_product_check(
            level=log_level,
            account_label=account_label,
            product_name=candidate_name,
            product_id=product_id,
            message_id=message_id,
            telegram_found=channel_id is not None,
            channel_id=channel_id,
            message_date=telegram_message_date if telegram_message_date != "-" else None,
            age_days=telegram_age_days_int,
            action=action,
            reason=lookup_reason,
        )
        if decision == "eligible_for_deactivation":
            candidates.append(
                {
                    "account_id": candidate_account_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "created_product_id": product_id,
                    "product_name": candidate_name,
                    "telegram_message_date": telegram_message_date,
                    "tracking_allowed": tracking_allowed,
                }
            )

    if batch_limit is not None:
        candidates = candidates[:batch_limit]
    result["found"] = len(candidates)
    result["candidates"] = candidates
    for candidate in candidates:
        log(
            "INFO",
            "Кандидат на немедленную деактивацию: "
            f"account_id={candidate.get('account_id')}. "
            f"id_товара={candidate.get('created_product_id')}. "
            f"message_id={candidate.get('message_id')}. "
            f"telegram_date={candidate.get('telegram_message_date')}.",
        )
    if dry_run or not candidates:
        if not candidates:
            log(
                "INFO",
                "Деактивация: после проверки товара нет кандидата для запроса Shafa. "
                f"checked={result['checked']}. active={result['active']}. "
                f"skipped={result['skipped']}. not_found={result['not_found']}.",
            )
        return _finish_result()

    leased_candidates: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_account_id = str(candidate["account_id"])
        channel_id = int(candidate["channel_id"])
        message_id = int(candidate["message_id"])
        if not bool(candidate.get("tracking_allowed", True)):
            leased_candidates.append(candidate)
            continue
        try:
            enqueue_telegram_product_deactivation(
                channel_id,
                message_id,
                account_id=candidate_account_id,
            )
            claimed = claim_telegram_product_deactivation(
                account_id=candidate_account_id,
                channel_id=channel_id,
                message_id=message_id,
            )
        except Exception as exc:
            result["failed"] = int(result["failed"]) + 1
            _safe_old_product_log(
                "ERROR",
                "Не удалось получить lease очереди деактивации старого товара. "
                f"account_id={candidate_account_id}. "
                f"product_id={candidate.get('created_product_id')}. "
                f"channel_id={channel_id}. message_id={message_id}. error={exc}",
            )
            continue
        if claimed is None:
            _safe_old_product_log(
                "INFO",
                "Пропускаю кандидата деактивации: товар уже обрабатывается другим процессом. "
                f"account_id={candidate_account_id}. "
                f"product_id={candidate.get('created_product_id')}. "
                f"channel_id={channel_id}. message_id={message_id}.",
            )
            continue
        candidate["deactivation_processing_token"] = claimed.get(
            "deactivation_processing_token"
        )
        leased_candidates.append(candidate)
    candidates = leased_candidates
    result["found"] = len(candidates)
    if not candidates:
        return _finish_result()

    deactivator = deactivate_product_func or _deactivate_product_backend_not_configured
    deactivated = 0
    failed = int(result["failed"])
    for index, candidate in enumerate(candidates, start=1):
        candidate_name = str(candidate.get("product_name") or "").strip() or "нет названия"
        product_id = str(candidate["created_product_id"])
        channel_id = int(candidate["channel_id"])
        message_id = int(candidate["message_id"])
        candidate_account_id = str(candidate["account_id"])
        deactivation_processing_token = str(
            candidate.get("deactivation_processing_token") or ""
        ).strip()
        telegram_message_dt = _parse_datetime_text_utc(candidate.get("telegram_message_date"))
        telegram_age_days = (
            round(
                (datetime.now(timezone.utc) - telegram_message_dt).total_seconds()
                / 86400.0,
                1,
            )
            if telegram_message_dt is not None
            else None
        )
        telegram_age_days_int = (
            int(telegram_age_days) if telegram_age_days is not None else None
        )
        try:
            log(
                "INFO",
                "Отправляю запрос деактивации Shafa: "
                f"account_id={candidate_account_id}. "
                f"id_товара={product_id}. "
                f"message_id={message_id}. "
                f"дней={telegram_age_days if telegram_age_days is not None else 'unknown'}.",
            )
            deactivator(product_id)
        except Exception as exc:
            failed += 1
            attempts: object = "not_recorded"
            if bool(candidate.get("tracking_allowed", True)):
                try:
                    if deactivation_processing_token:
                        finish_telegram_product_deactivation(
                            channel_id,
                            message_id,
                            deactivation_processing_token,
                            success=False,
                            error_message=str(exc),
                            account_id=candidate_account_id,
                        )
                        attempts = "queued"
                    else:
                        attempts = record_telegram_product_shafa_deactivate_failure(
                            channel_id,
                            message_id,
                            str(exc),
                            account_id=candidate_account_id,
                        )
                except Exception as tracking_exc:
                    attempts = "tracking_error"
                    _safe_old_product_log(
                        "WARN",
                        "Не удалось записать ошибку деактивации старого товара. "
                        f"account_id={candidate_account_id}. product_id={product_id}. "
                        f"channel_id={channel_id}. message_id={message_id}. "
                        f"error={tracking_exc}",
                    )
            _safe_old_product_log(
                "ERROR",
                "Не удалось деактивировать старый товар Shafa. "
                f"name={candidate_name}. product_id={product_id}. "
                f"channel_id={channel_id}. message_id={message_id}. "
                f"telegram_age_days={telegram_age_days if telegram_age_days is not None else 'unknown'}. "
                f"Попытка деактивации: {attempts}. Ошибка: {exc}",
            )
            _log_old_product_check(
                level="ERROR",
                account_label=account_label,
                product_name=candidate_name,
                product_id=product_id,
                message_id=message_id,
                telegram_found=True,
                channel_id=channel_id,
                message_date=candidate.get("telegram_message_date"),
                age_days=telegram_age_days_int,
                action="ERROR",
                reason=str(exc),
            )
        else:
            deactivated += 1
            try:
                mark_uploaded_product_inactive(product_id, status_title="Деактивовано")
            except Exception as tracking_exc:
                _safe_old_product_log(
                    "WARN",
                    "Не удалось отметить товар аккаунта как неактивный. "
                    f"account_id={candidate_account_id}. product_id={product_id}. "
                    f"error={tracking_exc}",
                )
            if (
                bool(candidate.get("tracking_allowed", True))
                and channel_id is not None
                and message_id is not None
            ):
                try:
                    if deactivation_processing_token:
                        finish_telegram_product_deactivation(
                            channel_id,
                            message_id,
                            deactivation_processing_token,
                            success=True,
                            account_id=candidate_account_id,
                        )
                    else:
                        mark_telegram_product_deactivated_on_shafa(
                            channel_id,
                            message_id,
                            account_id=candidate_account_id,
                        )
                except Exception as tracking_exc:
                    _safe_old_product_log(
                        "WARN",
                        "Не удалось отметить товар Telegram как деактивированный. "
                        f"account_id={candidate_account_id}. product_id={product_id}. "
                        f"channel_id={channel_id}. message_id={message_id}. "
                        f"error={tracking_exc}",
                    )
            _safe_old_product_log(
                "OK",
                "Деактивирован старый товар Shafa. "
                f"name={candidate_name}. product_id={product_id}. "
                f"channel_id={channel_id}. message_id={message_id}. "
                f"telegram_age_days={telegram_age_days if telegram_age_days is not None else 'unknown'}.",
            )
            _log_old_product_check(
                level="INFO",
                account_label=account_label,
                product_name=candidate_name,
                product_id=product_id,
                message_id=message_id,
                telegram_found=True,
                channel_id=channel_id,
                message_date=candidate.get("telegram_message_date"),
                age_days=telegram_age_days_int,
                action="DELETED",
                reason="deactivated",
            )
        if index < len(candidates) and delay_seconds > 0:
            time.sleep(delay_seconds)

    result["deactivated"] = deactivated
    result["failed"] = failed
    return _finish_result()


def deactivate_old_telegram_products(
    *,
    older_than_days: Optional[int] = None,
    limit: Optional[int] = None,
    sleep_seconds: Optional[float] = None,
    dry_run: bool = False,
    account_id: Optional[str] = None,
    deactivate_product_func=None,
) -> dict[str, object]:
    log("INFO", "Деактивация ждёт очередь выполнения.")
    enter_product_pipeline()
    try:
        log("INFO", "Деактивация вошла в очередь выполнения.")
        return _deactivate_old_telegram_products_impl(
            older_than_days=older_than_days,
            limit=limit,
            sleep_seconds=sleep_seconds,
            dry_run=dry_run,
            account_id=account_id,
            deactivate_product_func=deactivate_product_func,
        )
    finally:
        exit_product_pipeline()
        log("INFO", "Деактивация освободила очередь выполнения.")


def delete_old_telegram_products(
    *,
    older_than_days: Optional[int] = None,
    limit: Optional[int] = None,
    sleep_seconds: Optional[float] = None,
    dry_run: bool = False,
    account_id: Optional[str] = None,
    delete_product_func=None,
) -> dict[str, object]:
    return deactivate_old_telegram_products(
        older_than_days=older_than_days,
        limit=limit,
        sleep_seconds=sleep_seconds,
        dry_run=dry_run,
        account_id=account_id,
        deactivate_product_func=delete_product_func,
    )


if __name__ == "__main__":
    product = get_next_product_for_upload(message_amount=200, first_fetch_check=True)
    print(product)
