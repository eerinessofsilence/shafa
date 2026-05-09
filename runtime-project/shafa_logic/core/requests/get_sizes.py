import json
import os

try:
    from playwright.sync_api import BrowserContext
except ModuleNotFoundError:  # pragma: no cover - optional at import time for tests
    BrowserContext = object

from core.core import base_headers, read_response_json
from data.const import API_BATCH_URL, API_V5_URL
from data.db import save_size_mappings, save_sizes
from data.size_mapping import build_size_mappings, flatten_v5_size_groups
from utils.logging import log


def _size_debug_enabled() -> bool:
    return os.getenv("SHAFA_DEBUG_SIZE_MAPPING", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _fetch_v3_sizes(
    ctx: BrowserContext,
    csrftoken: str,
    catalog_slug: str,
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
    return data.get("data", {}).get("filterSize") or []


def _fetch_v5_size_groups(
    ctx: BrowserContext,
    csrftoken: str,
    catalog_slug: str,
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
    return catalog.get("sizeGroups") or []


def get_sizes(
    ctx: BrowserContext,
    csrftoken: str,
    catalog_slug: str = "obuv/krossovki",
) -> list[dict]:
    v5_size_groups = _fetch_v5_size_groups(ctx, csrftoken, catalog_slug)
    sizes = flatten_v5_size_groups(v5_size_groups)
    try:
        v3_sizes = _fetch_v3_sizes(ctx, csrftoken, catalog_slug)
    except Exception as exc:
        v3_sizes = []
        if _size_debug_enabled():
            log(
                "WARN",
                f"Не удалось загрузить V3 размеры для {catalog_slug}: {exc}",
            )
    mappings = build_size_mappings(v3_sizes, v5_size_groups)
    save_sizes(sizes, catalog_slug=catalog_slug, replace_catalog=True)
    save_size_mappings(mappings, catalog_slug=catalog_slug)
    if _size_debug_enabled():
        log(
            "INFO",
            "Нормализованы размеры: "
            + json.dumps(
                {
                    "catalog": catalog_slug,
                    "v5_size_count": len(sizes),
                    "v3_size_count": len(v3_sizes),
                    "mapping_count": len(mappings),
                    "mapping_preview": mappings[:3],
                },
                ensure_ascii=False,
            ),
        )
    return sizes
