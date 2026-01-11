from dataclasses import dataclass, field


@dataclass
class Product:
    name: str
    description: str
    category: str
    brand: int
    size: int
    price: int

    translation_enabled: bool = True
    condition: str = "NEW"
    amount: int = 1
    selling_condition: str = "SALE"

    additional_sizes: list[int] = field(default_factory=list)
    characteristics: list[int] = field(default_factory=list)
    colors: list[str] = field(default_factory=lambda: ["WHITE"])
    keywords: list[str] = field(default_factory=list)
