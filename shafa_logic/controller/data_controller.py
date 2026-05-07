import asyncio
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

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
    DEFAULT_MESSAGE_PARSE_LIMIT,
    MAX_PRODUCT_CREATE_ATTEMPTS,
    MAX_UPLOAD_BYTES,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SESSION_PATH,
)
from data.db import (
    claim_next_telegram_product_for_creation,
    claim_telegram_fetch,
    find_size_mapping_candidates,
    finish_telegram_backfill,
    finish_telegram_fetch,
    get_brand_id_by_name,
    get_max_telegram_product_message_id,
    get_size_id_by_name,
    get_telegram_scan_cursor,
    increment_telegram_product_attempt,
    list_brand_names,
    load_telegram_channels,
    mark_telegram_backfill_started,
    mark_telegram_scan_started,
    mark_telegram_product_created,
    finish_telegram_scan,
    save_telegram_channels,
    save_telegram_product,
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

APP_MODE_ENV = "SHAFA_APP_MODE"
MODE_CLOTHES = "clothes"
MODE_SNEAKERS = "sneakers"
DEFAULT_TELEGRAM_FETCH_COOLDOWN_SECONDS = 90
DEFAULT_TELEGRAM_FETCH_LEASE_SECONDS = 180
DEFAULT_TELEGRAM_FETCH_WAIT_SECONDS = 3.0
DEFAULT_TELEGRAM_SCAN_BATCH_SIZE = 150

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
_CLOTHES_KEYWORD_PATTERNS: Optional[list[re.Pattern]] = None
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


def _is_garbage_name_line(line: str) -> bool:
    text = line.strip()
    if not text:
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
    return _contains_any(name.casefold(), _FORBIDDEN_NAME_HINTS)


def _is_valid_selected_name(name: str) -> bool:
    text = name.strip()
    if not text:
        return False
    if _is_garbage_name_line(text):
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


_COMPOUND_CLOTHES_NAME_TOKENS = tuple(
    sorted(
        {
            _normalize_token(token)
            for token in _CLOTHES_NAME_HINTS
            if _normalize_token(token) and " " not in token and "-" not in token
        },
        key=len,
        reverse=True,
    )
)


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
    if len(line) < 3 or len(line) > 120:
        return False
    if re.match(r"(?i)^(?:анонс(?:уємо)?|анонсуємо|новинк\w*|new)\b", line.strip()):
        return False
    lower = line.casefold()
    if (
        _contains_any(lower, _NON_NAME_HINTS)
        or _contains_any(lower, _NAME_EXCLUDE_HINTS)
        or _contains_any(lower, _FORBIDDEN_NAME_HINTS)
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
    if len(candidate.split()) >= 2 or any(ch.isdigit() for ch in candidate):
        return True
    if _find_best_brand_in_text(candidate):
        return True
    return bool(word_for_slack) and candidate.casefold() == word_for_slack.casefold()


def extract_name(lines: list[str]) -> tuple[str, str]:
    shirt_name = _extract_shirt_name(lines)
    if shirt_name:
        return shirt_name, _extract_word_for_slack(lines, shirt_name)

    article_name = _extract_article_name(lines)
    if article_name:
        return article_name, _extract_word_for_slack(lines, article_name)

    word_for_slack = _extract_word_for_slack(lines)

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


def _load_clothes_keyword_patterns() -> list[re.Pattern]:
    global _CLOTHES_KEYWORD_PATTERNS
    if _CLOTHES_KEYWORD_PATTERNS is not None:
        return _CLOTHES_KEYWORD_PATTERNS
    keywords = sorted(
        {
            keyword.strip()
            for keyword in _CLOTHES_NAME_HINTS
            if str(keyword).strip()
        },
        key=len,
        reverse=True,
    )
    _CLOTHES_KEYWORD_PATTERNS = [
        re.compile(rf"(?i)(?<!\w){re.escape(keyword)}(?!\w)")
        for keyword in keywords
    ]
    return _CLOTHES_KEYWORD_PATTERNS


def _has_clothes_keyword_in_text(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in _load_clothes_keyword_patterns())


def _trim_masked_brand_token(raw_token: str) -> tuple[str, int]:
    strip_chars = ".,;:()[]{}<>\"'"
    leading = len(raw_token) - len(raw_token.lstrip(strip_chars))
    return raw_token.strip(strip_chars), leading


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
    visible_count = sum(ch.isalnum() for ch in token)
    wildcard_count = len(token) - visible_count
    if visible_count < 2 or wildcard_count == 0 or wildcard_count > 2:
        return False
    if not any(ch.isalpha() for ch in token):
        return False
    return True


def _matches_masked_brand_token(masked_token: str, candidate: str) -> bool:
    if len(masked_token) != len(candidate):
        return False
    for masked_char, candidate_char in zip(masked_token, candidate):
        if masked_char.isalnum() and masked_char != candidate_char:
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


def _find_best_brand_in_text(text: str) -> str:
    if not text:
        return ""
    candidates = [
        candidate
        for candidate in (
            _find_exact_brand_match_in_text(text),
            _find_masked_brand_match_in_text(text),
        )
        if candidate is not None
    ]
    if not candidates:
        return ""
    return min(candidates)[3]


def is_valid_product_name(name: object) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    if _find_best_brand_in_text(text):
        return True
    return _has_clothes_keyword_in_text(text)


def is_valid_product(parsed: dict) -> bool:
    return is_valid_product_name(parsed.get("name"))


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


def _split_compound_clothes_token(token: str) -> str:
    normalized_token = _normalize_token(token)
    if not normalized_token or "-" in token or len(normalized_token) < 6:
        return token
    for left in _COMPOUND_CLOTHES_NAME_TOKENS:
        if not normalized_token.startswith(left):
            continue
        right = normalized_token[len(left) :]
        if not right or right not in _COMPOUND_CLOTHES_NAME_TOKENS:
            continue
        split_at = len(left)
        if split_at <= 0 or split_at >= len(token):
            continue
        return f"{token[:split_at]}-{token[split_at:]}"
    return token


def _normalize_clothes_product_name(name: object) -> str:
    text = str(name or "")
    if not text:
        return text
    parts: list[str] = []
    last_end = 0
    for token_match in re.finditer(r"[^\s]+", text):
        parts.append(text[last_end : token_match.start()])
        parts.append(_split_compound_clothes_token(token_match.group(0)))
        last_end = token_match.end()
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
    for token in name.split():
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
    brand = extract_brand(lines, name)
    size, additional_sizes = extract_sizes(
        lines,
        even_range_step=_should_use_even_clothing_size_ranges(slug),
    )
    color = extract_colors(lines, name)
    price = extract_price(lines)
    confidence = _calculate_confidence(name, price, size, brand, color)



    return {
        "description": description,
        "name": name,
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
    return catalog_slug in {DEFAULT_SHOES_CATEGORY, WOMEN_SNEAKERS_CATEGORY}


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
) -> list:
    if backfill_before_message_id is None or backfill_before_message_id <= 1:
        return []

    messages: list = []
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
        messages.append(msg)
    return messages


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


def _scan_error_message(channel_id: int, message_id: Optional[int], exc: Exception) -> str:
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
    backfill_attempted = False
    live_messages_fetched = 0
    backfill_messages_fetched = 0
    error_message: Optional[str] = None

    cursor = get_telegram_scan_cursor(channel_id, account_id=account_id)
    last_checked_message_id = cursor.get("last_checked_message_id")
    backfill_before_message_id = cursor.get("backfill_before_message_id")
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

        if error_message is None and live_messages_fetched == 0:
            resolved_backfill_before = _resolve_backfill_floor_message_id(
                channel_id,
                account_id=account_id,
                backfill_before_message_id=backfill_before_message_id,
                live_scan_floor_message_id=live_scan_floor_message_id,
            )
            if resolved_backfill_before is not None and resolved_backfill_before > 1:
                backfill_attempted = True
                mark_telegram_backfill_started(channel_id, account_id=account_id)
                backfill_messages = await _load_messages_for_backfill(
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
                    if backfill_last_processed_message_id is not None:
                        next_backfill_before_message_id = backfill_last_processed_message_id
                    elif backfill_messages_fetched == 0:
                        next_backfill_before_message_id = 1
                finish_telegram_backfill(
                    channel_id,
                    backfill_before_message_id=next_backfill_before_message_id,
                    account_id=account_id,
                    error_message=backfill_error_message,
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
        "backfill_last_processed_message_id": backfill_last_processed_message_id,
        "backfill_error_message": backfill_error_message,
        "last_processed_message_id": last_processed_message_id,
        "error_message": error_message,
        "stats": stats,
    }


async def scan_account_telegram_channels_async(
    batch_size: int = DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
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
    async with create_telegram_client(
        TELEGRAM_SESSION_PATH,
        api_id_value,
        api_hash_value,
        save_entities=False,
        telegram_client_cls=TelegramClient,
    ) as client:
        channel_ids = _get_channel_ids()
        await _sync_channel_titles(client, channel_ids)
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
        for candidate_id in source_message_ids:
            message = await client.get_messages(channel_peer, ids=candidate_id)
            if not message or not _is_photo_message(message):
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
        discussion_message_ids = [message_id]
        for msg in sorted(messages, key=lambda item: item.id):
            if msg.id != message_id:
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
    if catalog_slug in CLOTHES_SLUGS:
        normalized_name = _normalize_clothes_product_name(normalized_name)

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


def _pick_next_product_for_upload() -> Optional[dict]:
    account_id = _current_account_id()
    while True:
        row = claim_next_telegram_product_for_creation(account_id=account_id)
        if not row:
            return None
        parsed_from_db = json.loads(row["parsed_data"]) if row["parsed_data"] else {}
        raw_message = row["raw_message"] or ""
        try:
            parsed = parse_message(raw_message) if raw_message else parsed_from_db
        except Exception as exc:
            log(
                "WARN",
                f"Пропускаю сообщение channel_id={row['channel_id']} "
                + f"message_id={row['message_id']}: не удалось распарсить ({exc}).",
            )
            mark_telegram_product_created(
                row["channel_id"],
                row["message_id"],
                created_product_id="SKIPPED_PARSE_ERROR",
                account_id=account_id,
            )
            continue
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
                account_id=account_id,
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
                account_id=account_id,
            )
            continue
        if not is_valid_product(parsed):
            log(
                "WARN",
                f"Пропускаю сообщение channel_id={row['channel_id']} "
                + f"message_id={row['message_id']}: невалидное название товара.",
            )
            mark_telegram_product_created(
                row["channel_id"],
                row["message_id"],
                created_product_id="SKIPPED_INVALID_NAME",
                account_id=account_id,
            )
            continue
        return {
            "channel_id": row["channel_id"],
            "message_id": row["message_id"],
            "parsed_data": parsed,
            "product_raw_data": _build_product_raw_data(parsed),
        }


async def get_next_product_for_upload_async(
    message_amount: int = 200,
    first_fetch_check: bool | None = None,
    scan_before_pick: bool = True,
) -> Optional[dict]:
    del message_amount, first_fetch_check, scan_before_pick
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
    account_id = _current_account_id()
    resolved_channel_id = (
        channel_id if channel_id is not None else _get_channel_ids()[0]
    )
    mark_telegram_product_created(
        resolved_channel_id,
        message_id,
        created_product_id,
        account_id=account_id,
    )


def register_product_failure(
    message_id: int,
    failure_reason: str,
    channel_id: Optional[int] = None,
) -> tuple[int, bool]:
    account_id = _current_account_id()
    resolved_channel_id = (
        channel_id if channel_id is not None else _get_channel_ids()[0]
    )
    attempts = increment_telegram_product_attempt(
        resolved_channel_id,
        message_id,
        failure_reason=failure_reason,
        account_id=account_id,
    )
    if attempts >= MAX_PRODUCT_CREATE_ATTEMPTS:
        mark_telegram_product_created(
            resolved_channel_id,
            message_id,
            created_product_id=SKIPPED_CREATE_RETRY_LIMIT,
            account_id=account_id,
        )
        return attempts, True
    return attempts, False


if __name__ == "__main__":
    product = get_next_product_for_upload(message_amount=200, first_fetch_check=True)
    print(product)
