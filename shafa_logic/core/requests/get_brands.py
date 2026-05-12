import json

try:
    from playwright.sync_api import BrowserContext
except ModuleNotFoundError:  # pragma: no cover - optional at import time for tests
    BrowserContext = object

from core.core import base_headers, read_response_json
from data.const import API_BATCH_URL
from data.db import save_brands

DEFAULT_BRANDS_CATALOG_SLUG = "obuv/krossovki"
CLOTHING_BRANDS_CATALOG_SLUG = "sport-otdyh/sportivnyye-kostyumy"


def _merge_brand_groups(block: dict) -> list[dict]:
    merged: list[dict] = []
    seen_ids: set[int] = set()
    for key in ("topBrands", "brands"):
        for brand in block.get(key) or []:
            brand_id = brand.get("id")
            if brand_id is None or brand_id in seen_ids:
                continue
            seen_ids.add(brand_id)
            merged.append(brand)
    return merged


def resolve_brand_catalog_slug(catalog_slug: str | None) -> str:
    normalized = str(catalog_slug or "").strip()
    if not normalized:
        return DEFAULT_BRANDS_CATALOG_SLUG
    if "/" in normalized and normalized not in {
        DEFAULT_BRANDS_CATALOG_SLUG,
        "zhenskaya-obuv/krossovki",
    }:
        return CLOTHING_BRANDS_CATALOG_SLUG
    return normalized


def get_brands(
    ctx: BrowserContext,
    csrftoken: str,
    catalog_slug: str = DEFAULT_BRANDS_CATALOG_SLUG,
) -> list[dict]:
    resolved_catalog_slug = resolve_brand_catalog_slug(catalog_slug)
    query = (
        "query WEB_ProductFormTopBrands($catalogSlug: String) {\n"
        "  filterTopBrands(catalogSlug: $catalogSlug) {\n"
        "    topBrands {\n"
        "      id\n"
        "      name\n"
        "      isUkrainian\n"
        "      __typename\n"
        "    }\n"
        "    brands {\n"
        "      id\n"
        "      name\n"
        "      isUkrainian\n"
        "      __typename\n"
        "    }\n"
        "    __typename\n"
        "  }\n"
        "}"
    )

    payload = [
        {
            "operationName": "WEB_ProductFormTopBrands",
            "variables": {"catalogSlug": resolved_catalog_slug},
            "query": query,
        }
    ]

    resp = ctx.request.post(
        API_BATCH_URL,
        headers={
            **base_headers(csrftoken),
            "Accept": "*/*",
            "Content-Type": "application/json",
            "batch": "true",
        },
        data=json.dumps(payload),
    )

    data = read_response_json(resp)
    if isinstance(data, list):
        data = data[0] if data else {}

    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    block = data.get("data", {}).get("filterTopBrands") or {}

    brands = _merge_brand_groups(block)
    save_brands(brands)
    return brands


def get_clothing_brands(
    ctx: BrowserContext,
    csrftoken: str,
) -> list[dict]:
    return get_brands(
        ctx,
        csrftoken,
        catalog_slug=CLOTHING_BRANDS_CATALOG_SLUG,
    )
