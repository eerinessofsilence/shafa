from dataclasses import dataclass, field

DEMISEASON_CHARACTERISTIC_ID = 10273
HANDMADE_CHARACTERISTIC_ID = 10324
ABSTRACTION_PRINT_CHARACTERISTIC_ID = 2375
_SHOES_CATEGORIES = frozenset(
    {
        "obuv/krossovki",
        "zhenskaya-obuv/krossovki",
    }
)


def _is_clothing_category(category: object) -> bool:
    normalized = str(category or "").strip()
    return bool(normalized) and normalized not in _SHOES_CATEGORIES


def _has_brand_value(brand: object) -> bool:
    if brand is None:
        return False
    if isinstance(brand, str):
        return bool(brand.strip())
    return True


def _required_characteristic_ids(category: object, brand: object) -> tuple[int, ...]:
    required = [DEMISEASON_CHARACTERISTIC_ID]
    if str(category or "").strip() in _SHOES_CATEGORIES:
        required.append(ABSTRACTION_PRINT_CHARACTERISTIC_ID)
    if _is_clothing_category(category) and not _has_brand_value(brand):
        required.append(HANDMADE_CHARACTERISTIC_ID)
    return tuple(required)


def _merge_required_characteristics(
    characteristics: list[int],
    *,
    category: object,
    brand: object,
) -> list[int]:
    required_characteristic_ids = _required_characteristic_ids(category, brand)
    allow_handmade = HANDMADE_CHARACTERISTIC_ID in required_characteristic_ids
    filtered_characteristics = list(characteristics or [])
    if not allow_handmade:
        filtered_characteristics = [
            value
            for value in filtered_characteristics
            if value != HANDMADE_CHARACTERISTIC_ID
        ]

    merged: list[int] = []
    seen: set[int] = set()
    for value in [*filtered_characteristics, *required_characteristic_ids]:
        if value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


@dataclass
class Product:
    name: str
    description: str
    category: str
    brand: int
    size: int
    price: int
    word_for_slack: str = ""
    slug: str = ""

    translation_enabled: bool = True
    condition: str = "NEW"
    amount: int = 1
    selling_condition: str = "SALE"

    additional_sizes: list[int] = field(default_factory=list)
    characteristics: list[int] = field(default_factory=list)
    colors: list[str] = field(default_factory=lambda: ["WHITE"])
    keywords: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.characteristics = _merge_required_characteristics(
            list(self.characteristics or []),
            category=self.category,
            brand=self.brand,
        )
