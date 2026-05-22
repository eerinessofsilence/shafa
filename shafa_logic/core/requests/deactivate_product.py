import json

from core.no_playwright import (
    _base_headers,
    _get_csrftoken_from_cookies,
    _load_shafa_cookies,
    _request_json,
)
from data.const import API_URL

DEACTIVATE_PRODUCTS_MUTATION = """
mutation deactivateProducts(
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
      }
    }
  }
}
"""


def _summarize_deactivate_errors(errors: list[dict]) -> str:
    parts: list[str] = []
    for err in errors:
        field = str(err.get("field") or "").strip() or "__all__"
        messages = err.get("messages") or []
        codes = [
            str(message.get("code") or "").strip()
            for message in messages
            if str(message.get("code") or "").strip()
        ]
        if codes:
            parts.append(f"{field}: {','.join(dict.fromkeys(codes))}")
        else:
            parts.append(field)
    return " / ".join(parts) if parts else "unknown"


def deactivate_product(product_id: str) -> None:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        raise ValueError("product_id is required")
    try:
        product_id_int = int(normalized_product_id)
    except ValueError as exc:
        raise ValueError("product_id must be an integer") from exc

    cookies = _load_shafa_cookies()
    if not cookies:
        raise RuntimeError("No saved cookies. Log in via main.py first.")

    csrftoken = _get_csrftoken_from_cookies(cookies)
    if not csrftoken:
        raise RuntimeError("csrftoken not found in cookies")

    payload = {
        "operationName": "deactivateProducts",
        "variables": {
            "includeIds": [product_id_int],
            "excludeIds": None,
            "allProducts": False,
        },
        "query": DEACTIVATE_PRODUCTS_MUTATION,
    }
    headers = {
        **_base_headers(csrftoken),
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Referer": "https://shafa.ua/uk/my/clothes",
    }

    data = _request_json(
        API_URL,
        json.dumps(payload).encode("utf-8"),
        headers,
        cookies,
    )
    top_level_errors = data.get("errors") or []
    if top_level_errors:
        messages = [
            str(error.get("message") or "").strip()
            for error in top_level_errors
            if str(error.get("message") or "").strip()
        ]
        raise RuntimeError(" / ".join(messages) if messages else str(top_level_errors))

    result = data.get("data", {}).get("deactivateProducts") or {}
    if not result.get("isSuccess"):
        errors = result.get("errors") or []
        if errors:
            raise RuntimeError(_summarize_deactivate_errors(errors))
        raise RuntimeError("Product deactivation failed")
