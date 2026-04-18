from __future__ import annotations

import re
from typing import Optional

SIZE_SYSTEM_INTERNATIONAL = "international"
SIZE_SYSTEM_EU = "eu"
SIZE_SYSTEM_UA = "ua"
SIZE_SYSTEMS = (
    SIZE_SYSTEM_INTERNATIONAL,
    SIZE_SYSTEM_EU,
    SIZE_SYSTEM_UA,
)

_ALPHA_SIZE_RE = re.compile(
    r"^(?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|XXXXL|OS|ONE SIZE)$"
)
_NUMERIC_SIZE_RE = re.compile(r"^\d+(?:[.,]\d+)?$")
_NUMERIC_RANGE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)$")
_CYRILLIC_SIZE_TRANSLATION = str.maketrans(
    {
        "Х": "X",
        "х": "x",
    }
)


def normalize_size_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.translate(_CYRILLIC_SIZE_TRANSLATION)
    text = text.replace("–", "-").replace("—", "-")
    upper = text.upper()
    if upper in {"O/S", "OS"}:
        return "ONE SIZE"
    if upper in {"OTHER", "ДРУГОЙ", "ІНШИЙ"}:
        return "ІНШИЙ"
    if _ALPHA_SIZE_RE.fullmatch(upper):
        return upper
    range_match = _NUMERIC_RANGE_RE.fullmatch(text)
    if range_match:
        left = _normalize_numeric_part(range_match.group(1))
        right = _normalize_numeric_part(range_match.group(2))
        return f"{left}-{right}" if left and right else None
    if _NUMERIC_SIZE_RE.fullmatch(text):
        return _normalize_numeric_part(text)
    return upper if re.search(r"[A-Z]", upper) else text


def parse_v3_secondary_size_name(value: object) -> tuple[Optional[str], Optional[str]]:
    if value is None:
        return None, None
    parts = [
        normalized
        for raw_part in str(value).split("/")
        for normalized in [normalize_size_text(raw_part)]
        if normalized
    ]
    international = None
    ua = None
    for part in parts:
        if _looks_alpha_like(part) and international is None:
            international = part
            continue
        if _looks_numeric_like(part):
            ua = part
    return international, ua


def detect_v5_group_system(group_name: object) -> Optional[str]:
    if group_name is None:
        return None
    lower = str(group_name).strip().casefold()
    if not lower:
        return None
    if "міжнарод" in lower or "international" in lower:
        return SIZE_SYSTEM_INTERNATIONAL
    if "європ" in lower or "europe" in lower:
        return SIZE_SYSTEM_EU
    if "укра" in lower or "ukrain" in lower:
        return SIZE_SYSTEM_UA
    return None


def flatten_v5_size_groups(size_groups: list[dict]) -> list[dict]:
    sizes: list[dict] = []
    for size_group in size_groups:
        system = detect_v5_group_system(size_group.get("name"))
        for size_item in size_group.get("sizes") or []:
            size_id = size_item.get("id")
            primary_name = normalize_size_text(
                size_item.get("primarySizeName") or size_item.get("name")
            )
            if size_id is None or not primary_name:
                continue
            try:
                size_id_int = int(size_id)
            except (TypeError, ValueError):
                continue
            sizes.append(
                {
                    "id": size_id_int,
                    "primarySizeName": primary_name,
                    "secondarySizeName": None,
                    "sizeSystem": system,
                    "__typename": size_item.get("__typename") or "SizeType",
                }
            )
    return sizes


def build_size_mappings(v3_sizes: list[dict], v5_size_groups: list[dict]) -> list[dict]:
    v5_sizes = flatten_v5_size_groups(v5_size_groups)
    v5_by_system: dict[str, dict[str, int]] = {system: {} for system in SIZE_SYSTEMS}
    special_rows: dict[str, dict] = {}
    for size in v5_sizes:
        system = size.get("sizeSystem")
        label = normalize_size_text(size.get("primarySizeName"))
        if system not in SIZE_SYSTEMS or not label:
            continue
        v5_by_system[system][label] = int(size["id"])
        if label in {"ONE SIZE", "ІНШИЙ"}:
            row = special_rows.setdefault(
                label,
                {
                    "id_v3": None,
                    SIZE_SYSTEM_INTERNATIONAL: None,
                    SIZE_SYSTEM_EU: None,
                    SIZE_SYSTEM_UA: None,
                    "id_v5_international": None,
                    "id_v5_eu": None,
                    "id_v5_ua": None,
                },
            )
            row[system] = label
            row[f"id_v5_{system}"] = int(size["id"])

    used_v5_ids: set[int] = set()
    rows: list[dict] = []
    seen_keys: set[tuple[Optional[str], Optional[str], Optional[str]]] = set()

    def add_row(row: dict) -> None:
        key = (
            row.get(SIZE_SYSTEM_INTERNATIONAL),
            row.get(SIZE_SYSTEM_EU),
            row.get(SIZE_SYSTEM_UA),
        )
        if key in seen_keys:
            return
        seen_keys.add(key)
        for system in SIZE_SYSTEMS:
            size_id = row.get(f"id_v5_{system}")
            if size_id is not None:
                used_v5_ids.add(int(size_id))
        rows.append(row)

    for v3_size in v3_sizes:
        size_id = v3_size.get("id")
        try:
            size_id_int = int(size_id)
        except (TypeError, ValueError):
            size_id_int = None
        eu = normalize_size_text(v3_size.get("primarySizeName"))
        international, ua = parse_v3_secondary_size_name(v3_size.get("secondarySizeName"))
        row = {
            "id_v3": size_id_int,
            SIZE_SYSTEM_INTERNATIONAL: international,
            SIZE_SYSTEM_EU: eu,
            SIZE_SYSTEM_UA: ua,
            "id_v5_international": _lookup_v5_id(
                v5_by_system[SIZE_SYSTEM_INTERNATIONAL], international
            ),
            "id_v5_eu": _lookup_v5_id(v5_by_system[SIZE_SYSTEM_EU], eu),
            "id_v5_ua": _lookup_v5_id(v5_by_system[SIZE_SYSTEM_UA], ua),
        }
        add_row(row)

    for label, row in special_rows.items():
        if any(row.get(f"id_v5_{system}") is not None for system in SIZE_SYSTEMS):
            add_row(row)

    for system in SIZE_SYSTEMS:
        for label, size_id in v5_by_system[system].items():
            if size_id in used_v5_ids:
                continue
            add_row(
                {
                    "id_v3": None,
                    SIZE_SYSTEM_INTERNATIONAL: label
                    if system == SIZE_SYSTEM_INTERNATIONAL
                    else None,
                    SIZE_SYSTEM_EU: label if system == SIZE_SYSTEM_EU else None,
                    SIZE_SYSTEM_UA: label if system == SIZE_SYSTEM_UA else None,
                    "id_v5_international": size_id
                    if system == SIZE_SYSTEM_INTERNATIONAL
                    else None,
                    "id_v5_eu": size_id if system == SIZE_SYSTEM_EU else None,
                    "id_v5_ua": size_id if system == SIZE_SYSTEM_UA else None,
                }
            )

    return rows


def _normalize_numeric_part(value: str) -> Optional[str]:
    text = value.strip().replace(",", ".")
    if not text:
        return None
    if not _NUMERIC_SIZE_RE.fullmatch(text):
        return None
    number = float(text)
    return f"{number:g}"


def _looks_alpha_like(value: str) -> bool:
    normalized = normalize_size_text(value)
    if not normalized:
        return False
    return bool(re.search(r"[A-Z]", normalized)) or normalized in {"ONE SIZE", "ІНШИЙ"}


def _looks_numeric_like(value: str) -> bool:
    normalized = normalize_size_text(value)
    if not normalized:
        return False
    return bool(_NUMERIC_SIZE_RE.fullmatch(normalized))


def _lookup_v5_id(mapping: dict[str, int], label: Optional[str]) -> Optional[int]:
    if not label:
        return None
    return mapping.get(label)
