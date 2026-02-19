import json

from playwright.sync_api import BrowserContext

from core.core import base_headers, read_response_json
from data.const import API_BATCH_URL
from data.db import save_brands


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

    brands = block.get("brands") or []
    save_brands(brands)
    return brands
