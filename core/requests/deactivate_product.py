import json
import re

from core.no_playwright import (
    _base_headers,
    _get_csrftoken_from_cookies,
    _load_shafa_cookies,
    _request_json,
)
from data.const import API_URL
from utils.logging import log

DEACTIVATE_PRODUCTS_MUTATION = """
mutation WEB_deactivateProducts(
  $includeIds: [Int]
  $excludeIds: [Int]
  $allProducts: Boolean
) {
  deactivateProducts(
    includeIds: $includeIds
    excludeIds: $excludeIds
    allProducts: $allProducts
  ) {
    isSuccess
    errors {
      field
      messages {
        code
        __typename
      }
      __typename
    }
    __typename
  }
}
"""


def parse_product_ids(value: str) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for token in re.findall(r"\d+", value):
        product_id = int(token)
        if product_id not in seen:
            seen.add(product_id)
            ids.append(product_id)
    return ids


def deactivate_products(product_ids: list[int]) -> dict:
    if not product_ids:
        raise ValueError("product_ids is required")
    cookies = _load_shafa_cookies()
    if not cookies:
        log("ERROR", "No saved cookies. Log in via main.py first.")
        return {}
    csrftoken = _get_csrftoken_from_cookies(cookies)
    if not csrftoken:
        raise RuntimeError("csrftoken not found in cookies")
    payload = {
        "operationName": "WEB_deactivateProducts",
        "variables": {
            "includeIds": product_ids,
            "excludeIds": None,
            "allProducts": None,
        },
        "query": DEACTIVATE_PRODUCTS_MUTATION,
    }
    headers = {
        **_base_headers(csrftoken),
        "Accept": "*/*",
        "Content-Type": "application/json",
    }
    data = _request_json(
        API_URL,
        json.dumps(payload).encode("utf-8"),
        headers,
        cookies,
    )
    errors = data.get("errors") or []
    if errors:
        log("ERROR", f"GraphQL errors: {errors}")
        return {"errors": errors}
    return data.get("data", {}).get("deactivateProducts") or {}


def main() -> None:
    from data.db import mark_uploaded_products_deactivated

    raw = input("Product id(s) to deactivate: ").strip()
    if not raw or raw.lower() in {"q", "quit"}:
        return
    product_ids = parse_product_ids(raw)
    if not product_ids:
        print("No valid product ids provided.")
        return
    result = deactivate_products(product_ids)
    if not result:
        return
    errors = result.get("errors") or []
    if errors:
        print(f"Deactivation errors: {errors}")
        return
    if result.get("isSuccess"):
        mark_uploaded_products_deactivated(product_ids)
        print(f"Deactivated {len(product_ids)} product(s).")
        return
    print("Deactivation failed.")


if __name__ == "__main__":
    main()
