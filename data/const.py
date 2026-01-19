from pathlib import Path

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

TELEGRAM_API_ID = 39423515
TELEGRAM_API_HASH = "0417175f011283bfd6bd76e4925a4136"
TELEGRAM_CHANNELS: list[tuple[int, str, str]] = [
    (-1001184429834, "GENERATION DROP / OPT 🌊", "main"),
    (-1001252296189, "", "extra_photos"),
    (-1001801709326, "", "extra_photos"),
]
TELEGRAM_CHANNEL_IDS = [channel_id for channel_id, _, _ in TELEGRAM_CHANNELS]

API_URL = "https://shafa.ua/api/v3/graphiql"
API_BATCH_URL = "https://shafa.ua/api/v3/graphiql-batch"
ORIGIN_URL = "https://shafa.ua"
REFERER_URL = "https://shafa.ua/uk/new"
APP_PLATFORM = "web"
APP_VERSION = "v2025.12.31.3"
DEFAULT_MARKUP = 400
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

MEDIA_DIR_PATH = "media"
STORAGE_STATE_PATH = Path("auth.json")
HEADLESS = False
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
