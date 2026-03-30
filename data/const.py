import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover - runtime dependency
    raise RuntimeError(
        "python-dotenv is required to load .env. "
        "Install it with: pip install python-dotenv"
    ) from exc

_ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=_ROOT_DIR / ".env", override=False)

CREATE_PRODUCT_MUTATION = """
mutation WEB_CreateProduct(
  $photosStr: [String],
  $nameUk: String,
  $nameRu: String,
  $descriptionUk: String,
  $descriptionRu: String,
  $isUkToRuTranslationEnabled: Boolean,
  $videoOverview: String,
  $catalog: String!,
  $condition: ConditionEnum!,
  $brand: Int,
  $userBrand: Int,
  $colors: [ColorEnum]!,
  $characteristics: [Int!],
  $size: Int,
  $additionalSizes: [Int],
  $count: Int,
  $sellingCondition: SellingConditionEnum!,
  $price: Int,
  $priceVariants: [CreatePriceVariantType!],
  $keyWords: [String],
  $gtin: String
) {
  createProduct(
    photosStr: $photosStr
    nameUk: $nameUk
    nameRu: $nameRu
    descriptionUk: $descriptionUk
    descriptionRu: $descriptionRu
    isUkToRuTranslationEnabled: $isUkToRuTranslationEnabled
    videoOverview: $videoOverview
    catalog: $catalog
    condition: $condition
    brand: $brand
    userBrand: $userBrand
    colors: $colors
    characteristics: $characteristics
    size: $size
    additionalSizes: $additionalSizes
    count: $count
    sellingCondition: $sellingCondition
    price: $price
    priceVariants: $priceVariants
    keyWords: $keyWords
    gtin: $gtin
  ) {
    createdProduct { id __typename }
    errors { field messages { code message __typename } __typename }
    __typename
  }
}
"""

UPLOAD_PHOTO_MUTATION = """
mutation UploadPhoto($file: String!) {
  uploadPhoto(uploadFile: $file) {
    idStr
    thumbnailUrl
    originalUrl
    errors { field messages { code message } }
  }
}
"""


def _get_env_int(name: str) -> Optional[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _get_env_str(name: str) -> Optional[str]:
    value = os.getenv(name, "").strip()
    return value or None


TELEGRAM_API_ID = _get_env_int("SHAFA_TELEGRAM_API_ID")
TELEGRAM_API_HASH = _get_env_str("SHAFA_TELEGRAM_API_HASH")
TELEGRAM_CHANNELS: list[tuple[int, str, str]] = [
    (-1001984470450, "2MOOD | Синя 1492", "main"),
    (-1001276463844, "👑zazhigalka👑", "main"),
    (-1001557491045, "ROZALINA синя 1530", "main"),
    (-1002850204025, "REMEZ - РИНКОВА 4935", "main"),
    (-1001568988278, "👑Valeri Butik👑1548Жіночий та чоловічий одяг", "main"),
    (-1001160944182, "INNA Риночна 1541", "main"),
    (-1001849992155, "Fashionista_drop", "main"),
]
TELEGRAM_CHANNEL_IDS = [channel_id for channel_id, _, _ in TELEGRAM_CHANNELS]

API_URL = "https://shafa.ua/api/v3/graphiql"
API_BATCH_URL = "https://shafa.ua/api/v3/graphiql-batch"
API_V5_URL = "https://shafa.ua/api/v5/graphql"
API_V4_URL = "https://shafa.ua/api/v4/graphql"
ORIGIN_URL = "https://shafa.ua"
REFERER_URL = "https://shafa.ua/uk/new"
APP_PLATFORM = "web"
APP_VERSION = "v2025.12.31.3"
DEFAULT_MARKUP = 400
DEFAULT_MARKUP_FOR_CLOTHES = 500
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ORDINARY_CLOTHES_SIZES = [834, 835]
DEFAULT_SEASON = 10273

MEDIA_DIR_PATH = "media"
STORAGE_STATE_PATH = Path("auth.json")
HEADLESS = True
DB_PATH = Path("data/shafa.sqlite3")

BRAND_NAME_TO_ID: dict[str, int] = {}

COLOR_NAME_TO_ENUM: dict[str, str] = {
    "black": "BLACK",
    "white": "WHITE",
    "gray": "GRAY",
    "grey": "GRAY",
    "brown": "BROWN",
    "orange": "ORANGE",
    "red": "RED",
    "blue": "BLUE",
    "green": "GREEN",
    "pink": "PINK",
    "purple": "PURPLE",
    "beige": "BEIGE",
    "cream": "WHITE",
    "navy": "NAVY",
    "tan": "TAN",
    "silver": "SILVER",
    "gold": "GOLD",
    "yellow": "YELLOW",
    "olive": "OLIVE",
    "khaki": "KHAKI",
}
