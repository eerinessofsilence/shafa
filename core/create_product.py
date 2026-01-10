import json
from models.product import Product
from playwright.sync_api import BrowserContext
from core.core import base_headers, read_response_json
from data.const import CREATE_PRODUCT_MUTATION, API_URL

def build_create_product_payload(photo_ids: list[str], product_raw_data: dict, markup: int) -> dict:
    product = Product(**product_raw_data)
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
        "count": product.amount if product.amount >= len(product.additional_sizes) + 1 else len(product.additional_sizes) + 1,
        "sellingCondition": product.selling_condition,
        "price": product.price + markup,
        "keyWords": product.keywords,
        "photosStr": photo_ids
    }

    return {
        "operationName": "WEB_CreateProduct",
        "variables": variables,
        "query": CREATE_PRODUCT_MUTATION,
    }


def create_product(ctx: BrowserContext, csrftoken: str, photo_ids: list[str], product_raw_data: dict, markup: int = 400) -> dict:
    payload = build_create_product_payload(photo_ids, product_raw_data, markup)
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
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    return data.get("data", {}).get("createProduct") or {}
