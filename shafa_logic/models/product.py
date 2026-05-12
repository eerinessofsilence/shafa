from dataclasses import dataclass, field

DEMISEASON_CHARACTERISTIC_ID = 10273
HANDMADE_CHARACTERISTIC_ID = 10324
REQUIRED_CHARACTERISTIC_IDS = (
    DEMISEASON_CHARACTERISTIC_ID,
    HANDMADE_CHARACTERISTIC_ID,
)


def _merge_required_characteristics(characteristics: list[int]) -> list[int]:
    merged: list[int] = []
    seen: set[int] = set()
    for value in [*characteristics, *REQUIRED_CHARACTERISTIC_IDS]:
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
            list(self.characteristics or [])
        )
