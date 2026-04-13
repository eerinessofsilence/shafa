import json

from playwright.sync_api import BrowserContext

from core.core import base_headers, read_response_json
from data.const import API_V5_URL
from data.db import save_sizes


def get_sizes(
    ctx: BrowserContext,
    csrftoken: str,
    catalog_slug: str = "obuv/krossovki",
) -> list[dict]:
    query = (
        "query WEB_ProductFormSizeGroup($catalogSlug: String!) {\n"
        "  catalog(slug: $catalogSlug) {\n"
        "    id\n"
        "    sizeGroup {\n"
        "      id\n"
        "      name\n"
        "      __typename\n"
        "    }\n"
        "    productFormSizeTitle\n"
        "    productFormSizeSubtitle\n"
        "    sizeGroups {\n"
        "      id\n"
        "      name\n"
        "      sizes {\n"
        "        id\n"
        "        name\n"
        "        primarySizeName\n"
        "        secondarySizeName\n"
        "        __typename\n"
        "      }\n"
        "      __typename\n"
        "    }\n"
        "    __typename\n"
        "  }\n"
        "}"
    )
    payload = {
        "operationName": "WEB_ProductFormSizeGroup",
        "variables": {"catalogSlug": catalog_slug},
        "query": query,
    }

    resp = ctx.request.post(
        API_V5_URL,
        headers={
            **base_headers(csrftoken),
            "Accept": "*/*",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
    )

    data = read_response_json(resp)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    catalog = data.get("data", {}).get("catalog") or {}
    size_groups = catalog.get("sizeGroups") or []
    sizes: list[dict] = []
    seen_ids: set[int] = set()
    for size_group in size_groups:
        group_sizes = size_group.get("sizes") or []
        for size_item in group_sizes:
            size_id = size_item.get("id")
            primary_size_name = size_item.get("primarySizeName") or size_item.get("name")
            if size_id is None or not primary_size_name:
                continue
            try:
                size_id_int = int(size_id)
            except (TypeError, ValueError):
                continue
            if size_id_int in seen_ids:
                continue
            seen_ids.add(size_id_int)
            sizes.append(
                {
                    "id": size_id_int,
                    "primarySizeName": str(primary_size_name),
                    "secondarySizeName": size_item.get("secondarySizeName"),
                    "__typename": size_item.get("__typename") or "SizeType",
                }
            )
    save_sizes(sizes, catalog_slug=catalog_slug)
    return sizes
