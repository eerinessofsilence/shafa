import json
import re
from pathlib import Path
from typing import Optional

from controller.data_controller import is_valid_product_name
from core.no_playwright import (
    _base_headers,
    _get_csrftoken_from_cookies,
    _is_allowed_cookie_domain,
    _load_storage_state_cookies,
    _load_shafa_cookies,
    _request_json,
)
from data.const import API_URL, DB_PATH, ORIGIN_URL, STORAGE_STATE_PATH
from data.db import (
    list_active_uploaded_product_payloads,
    load_cookies,
    mark_uploaded_products_deactivated,
)
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_shafa_cookies_for_account(
    *,
    storage_state_path: Optional[Path],
    db_path: Path,
) -> list[dict]:
    filtered: list[dict] = []
    if storage_state_path is not None:
        cookies = _load_storage_state_cookies(storage_state_path)
        filtered = [
            cookie
            for cookie in cookies
            if _is_allowed_cookie_domain(cookie.get("domain", ""), ORIGIN_URL)
        ]
    if not filtered:
        cookies = load_cookies(ORIGIN_URL, db_path=db_path)
        filtered = [
            cookie
            for cookie in cookies
            if _is_allowed_cookie_domain(cookie.get("domain", ""), ORIGIN_URL)
        ]
    return filtered


def _discover_shafa_account_contexts() -> list[dict]:
    root_dir = _repo_root()
    contexts: list[dict] = []
    seen: set[tuple[str, str]] = set()

    candidates = [
        {
            "name": "default",
            "storage_state_path": STORAGE_STATE_PATH if STORAGE_STATE_PATH.exists() else None,
            "db_path": DB_PATH,
        }
    ]
    accounts_dir = root_dir / "accounts"
    if accounts_dir.exists():
        for account_dir in sorted(path for path in accounts_dir.iterdir() if path.is_dir()):
            auth_path = account_dir / "auth.json"
            db_path = account_dir / "shafa.sqlite3"
            candidates.append(
                {
                    "name": account_dir.name,
                    "storage_state_path": auth_path if auth_path.exists() else None,
                    "db_path": db_path,
                }
            )

    for candidate in candidates:
        storage_state_path = candidate["storage_state_path"]
        db_path = Path(candidate["db_path"])
        if storage_state_path is None and not db_path.exists():
            continue
        key = (
            str(storage_state_path.resolve()) if storage_state_path is not None else "",
            str(db_path.resolve()),
        )
        if key in seen:
            continue
        seen.add(key)
        contexts.append(
            {
                "name": candidate["name"],
                "storage_state_path": storage_state_path,
                "db_path": db_path,
            }
        )
    return contexts


def _deactivate_products_with_cookies(product_ids: list[int], cookies: list[dict]) -> dict:
    if not product_ids:
        raise ValueError("product_ids is required")
    if not cookies:
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


def _extract_uploaded_product_name(row: dict) -> str:
    raw_payload = row.get("raw_payload")
    if raw_payload:
        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            name = str(payload.get("name") or "").strip()
            if name:
                return name
    return str(row.get("name") or "").strip()


def find_invalid_uploaded_products(
    limit: Optional[int] = None,
    *,
    db_path: Path = DB_PATH,
) -> list[dict]:
    invalid_products: list[dict] = []
    for row in list_active_uploaded_product_payloads(limit=limit, db_path=db_path):
        product_id_raw = str(row.get("product_id") or "").strip()
        if not product_id_raw:
            continue
        product_name = _extract_uploaded_product_name(row)
        if is_valid_product_name(product_name):
            continue
        product_id = parse_product_ids(product_id_raw)
        if not product_id:
            continue
        invalid_products.append(
            {
                "product_id": product_id[0],
                "name": product_name,
                "created_at": row.get("created_at"),
            }
        )
    return invalid_products


def _deactivate_invalid_uploaded_products_for_account(
    *,
    account_name: str,
    storage_state_path: Optional[Path],
    db_path: Path,
    limit: Optional[int] = None,
) -> dict:
    checked_rows = list_active_uploaded_product_payloads(limit=limit, db_path=db_path)
    invalid_products = find_invalid_uploaded_products(limit=limit, db_path=db_path)
    if not invalid_products:
        return {
            "account": account_name,
            "checked": len(checked_rows),
            "invalid": [],
            "deactivated": [],
            "errors": [],
        }

    cookies = _load_shafa_cookies_for_account(
        storage_state_path=storage_state_path,
        db_path=db_path,
    )
    if not cookies:
        return {
            "account": account_name,
            "checked": len(checked_rows),
            "invalid": invalid_products,
            "deactivated": [],
            "errors": [
                {
                    "product_id": None,
                    "name": "",
                    "reason": "missing_cookies",
                }
            ],
        }

    deactivated_ids: list[int] = []
    errors: list[dict] = []
    for item in invalid_products:
        product_id = item["product_id"]
        result = _deactivate_products_with_cookies([product_id], cookies)
        if not result:
            errors.append(
                {
                    "product_id": product_id,
                    "name": item.get("name") or "",
                    "reason": "empty_response",
                }
            )
            continue
        result_errors = result.get("errors") or []
        if result_errors:
            errors.append(
                {
                    "product_id": product_id,
                    "name": item.get("name") or "",
                    "reason": result_errors,
                }
            )
            continue
        if result.get("isSuccess"):
            mark_uploaded_products_deactivated([product_id], db_path=db_path)
            deactivated_ids.append(product_id)
            continue
        errors.append(
            {
                "product_id": product_id,
                "name": item.get("name") or "",
                "reason": "deactivation_failed",
            }
        )

    return {
        "account": account_name,
        "checked": len(checked_rows),
        "invalid": invalid_products,
        "deactivated": deactivated_ids,
        "errors": errors,
    }


def deactivate_invalid_uploaded_products(limit: Optional[int] = None) -> dict:
    account_results: list[dict] = []
    all_invalid: list[dict] = []
    all_deactivated: list[dict] = []
    all_errors: list[dict] = []
    total_checked = 0

    for context in _discover_shafa_account_contexts():
        result = _deactivate_invalid_uploaded_products_for_account(
            account_name=context["name"],
            storage_state_path=context["storage_state_path"],
            db_path=context["db_path"],
            limit=limit,
        )
        account_results.append(result)
        total_checked += int(result.get("checked") or 0)
        for item in result.get("invalid") or []:
            all_invalid.append({"account": context["name"], **item})
        for product_id in result.get("deactivated") or []:
            all_deactivated.append({"account": context["name"], "product_id": product_id})
        for item in result.get("errors") or []:
            all_errors.append({"account": context["name"], **item})

    return {
        "checked": total_checked,
        "accounts": account_results,
        "invalid": all_invalid,
        "deactivated": all_deactivated,
        "errors": all_errors,
    }


def main() -> None:
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
