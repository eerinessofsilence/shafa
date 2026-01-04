import json
from data.const import BASE_PRODUCT_VARIABLES, CREATE_PRODUCT_MUTATION, API_URL
from playwright.sync_api import BrowserContext
from core.core import base_headers, read_response_json

def build_create_product_payload(photo_id: str) -> dict:
    variables = dict(BASE_PRODUCT_VARIABLES)
    variables["photosStr"] = [photo_id]

    return {
        "operationName": "WEB_CreateProduct",
        "variables": variables,
        "query": CREATE_PRODUCT_MUTATION,
    }


def create_product(ctx: BrowserContext, csrftoken: str, photo_id: str) -> dict:
    payload = build_create_product_payload(photo_id)
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
