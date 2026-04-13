import json
import re

from playwright.sync_api import BrowserContext

from core.core import base_headers, read_response_json
from data.const import (
    API_URL,
    CREATE_PRODUCT_MUTATION,
    DEFAULT_MARKUP,
    LOG_CREATE_PRODUCT_REQUEST,
)
from models.product import Product
from utils.logging import log


def build_create_product_payload(
    photo_ids: list[str],
    product_raw_data: dict,
    markup: int,
) -> dict:
    product = Product(**product_raw_data)
    count = max(product.amount, len(product.additional_sizes) + 1)
    variables: dict = {
        "nameUk": product.name,
        "descriptionUk": product.description,
        "isUkToRuTranslationEnabled": product.translation_enabled,
        "catalog": product.category,
        "condition": product.condition,
        "brand": product.brand,
        "colors": product.colors,
        "size": product.size,
        "additionalSizes": product.additional_sizes,
        "characteristics": product.characteristics,
        "count": count,
        "sellingCondition": product.selling_condition,
        "price": product.price + markup,
        "keyWords": product.keywords,
        "photosStr": photo_ids,
    }

    return {
        "operationName": "WEB_CreateProduct",
        "variables": variables,
        "query": CREATE_PRODUCT_MUTATION,
    }


def _extract_invalid_color_enums(errors: list[dict]) -> list[str]:
    if not errors:
        return []
    patterns = [
        re.compile(r"Value '([^']+)' does not exist in 'ColorEnum'"),
        re.compile(r"got invalid value '([^']+)' at 'colors\\[\\d+\\]'"),
    ]
    invalid: list[str] = []
    seen: set[str] = set()
    for err in errors:
        message = str(err.get("message") or "")
        for pattern in patterns:
            for match in pattern.findall(message):
                if match not in seen:
                    seen.add(match)
                    invalid.append(match)
    return invalid


def _log_create_product_payload(payload: dict) -> None:
    if not LOG_CREATE_PRODUCT_REQUEST:
        return
    payload_preview = {
        "operationName": payload.get("operationName"),
        "variables": payload.get("variables"),
    }
    log(
        "INFO",
        "Запрос создания товара: "
        + json.dumps(payload_preview, ensure_ascii=False),
    )


def create_product(
    ctx: BrowserContext,
    csrftoken: str,
    photo_ids: list[str],
    product_raw_data: dict,
    markup: int = DEFAULT_MARKUP,
) -> dict:
    payload = build_create_product_payload(photo_ids, product_raw_data, markup)
    _log_create_product_payload(payload)
    resp = ctx.request.post(
        API_URL,
        headers={
            **base_headers(csrftoken),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
    )

    data = read_response_json(resp)
    errors = data.get("errors") or []
    if errors:
        invalid_colors = _extract_invalid_color_enums(errors)
        if invalid_colors:
            colors = list(product_raw_data.get("colors") or [])
            cleaned = [color for color in colors if color not in invalid_colors]
            if not cleaned:
                cleaned = ["WHITE"]
            if cleaned != colors:
                retry_raw = dict(product_raw_data)
                retry_raw["colors"] = cleaned
                retry_payload = build_create_product_payload(
                    photo_ids,
                    retry_raw,
                    markup,
                )
                _log_create_product_payload(retry_payload)
                resp = ctx.request.post(
                    API_URL,
                    headers={
                        **base_headers(csrftoken),
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(retry_payload),
                )
                data = read_response_json(resp)
                errors = data.get("errors") or []
        if errors:
            raise RuntimeError(f"GraphQL errors: {errors}")

    return data.get("data", {}).get("createProduct") or {}
