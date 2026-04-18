import json

try:
    from playwright.sync_api import BrowserContext
except ModuleNotFoundError:  # pragma: no cover - optional at import time for tests
    BrowserContext = object

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
    normalized_sizes: list[dict] = []
    seen_ids: set[int] = set()
    for size_item in sizes:
        size_id = size_item.get("id")
        primary_size_name = size_item.get("primarySizeName")
        if size_id is None or not primary_size_name:
            continue
        try:
            size_id_int = int(size_id)
        except (TypeError, ValueError):
            continue
        if size_id_int in seen_ids:
            continue
        seen_ids.add(size_id_int)
        normalized_sizes.append(
            {
                "id": size_id_int,
                "primarySizeName": str(primary_size_name),
                "secondarySizeName": size_item.get("secondarySizeName"),
                "__typename": size_item.get("__typename") or "SizeType",
            }
        )

    save_sizes(normalized_sizes, catalog_slug=catalog_slug)
    return normalized_sizes
