import json

from playwright.sync_api import BrowserContext

from core.core import base_headers, read_response_json
from data.const import API_BATCH_URL
from data.db import save_brands


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


def get_brands(
    ctx: BrowserContext,
    csrftoken: str,
    catalog_slug: str = "obuv/krossovki",
) -> list[dict]:
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
            "variables": {"catalogSlug": catalog_slug},
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
