import json

from playwright.sync_api import BrowserContext

from core.core import base_headers, read_response_json
from data.const import API_BATCH_URL
from data.db import save_sizes


def get_sizes(
    ctx: BrowserContext,
    csrftoken: str,
    catalog_slug: str = "obuv/krossovki",
) -> list[dict]:
    query = (
        "query WEB_ProductFormSizes($catalogSlug: String!) {\n"
        "  filterSize(catalogSlug: $catalogSlug) {\n"
        "    id\n"
        "    primarySizeName\n"
        "    secondarySizeName\n"
        "    __typename\n"
        "  }\n"
        "}"
    )
    payload = [
        {
            "operationName": "WEB_ProductFormSizes",
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

    sizes = data.get("data", {}).get("filterSize") or []
    save_sizes(sizes, catalog_slug=catalog_slug)
    return sizes
